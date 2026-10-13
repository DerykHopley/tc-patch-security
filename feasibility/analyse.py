"""Summarise the downloaded data for the two corpus options: general and LLM-specific.

Run: uv run --no-project --with pyyaml python -I feasibility/analyse.py
Writes feasibility/data/summary.json and prints a readable summary.
"""

import json
import re
from collections import Counter
from pathlib import Path

import yaml

DATA = Path(__file__).resolve().parent / "data"
CHUNK = 600  # characters, same limit as the prototype's chunker

CWE_RE = re.compile(r"CWE-\d+")
AML_RE = re.compile(r"AML\.T\d{4}(?:\.\d{3})?")
CVE_RE = re.compile(r"CVE-\d{4}-\d{4,}")


def chunks(text: str) -> int:
    """Split on headings, then cut each section into CHUNK-sized pieces."""
    sections = [s.strip() for s in re.split(r"\n(?=#{1,4} )", text) if s.strip()]
    return sum(max(1, -(-len(s) // CHUNK)) for s in sections)


def md_stats(folder: Path) -> dict:
    pages = {}
    for f in sorted(folder.glob("*.md")):
        t = f.read_text(encoding="utf-8")
        mapped = t.split("List of Mapped CWEs")[-1] if "List of Mapped CWEs" in t else ""
        pages[f.stem] = {
            "words": len(t.split()),
            "chunks": chunks(t),
            "headings": [h.strip("# .").split("![")[0].strip() for h in re.findall(r"^#{2,3} .*", t, re.M)],
            "mapped_cwes": sorted(set(CWE_RE.findall(mapped)), key=lambda c: int(c[4:])),
            "atlas_ids": sorted(set(AML_RE.findall(t))),
            "cves": sorted(set(CVE_RE.findall(t))),
        }
    return pages


def owasp_map(pages: dict) -> dict[str, str]:
    """CWE -> category code (A01..A10)."""
    out = {}
    for name, p in pages.items():
        for c in p["mapped_cwes"]:
            out.setdefault(c, name[:3])
    return out


def mapped_share(rows: list[dict], cwe_map: dict) -> dict:
    with_cwe = [r for r in rows if r["cwes"]]
    cats = Counter()
    hit = 0
    for r in with_cwe:
        found = {cwe_map[c] for c in r["cwes"] if c in cwe_map}
        hit += bool(found)
        cats.update(found)
    return {"rows": len(rows), "with_cwe": len(with_cwe), "mapped_to_owasp": hit,
            "by_category": dict(sorted(cats.items()))}


def main() -> None:
    s: dict = {}

    # ---------- OWASP Top 10 (general) ----------
    o25, o21 = md_stats(DATA / "owasp/2025/en"), md_stats(DATA / "owasp/2021/en")
    o25de = md_stats(DATA / "owasp/2025/de")
    m25, m21 = owasp_map(o25), owasp_map(o21)
    s["owasp"] = {
        "2025": {k: {x: v[x] for x in ("words", "chunks")} | {"cwes": len(v["mapped_cwes"])} for k, v in o25.items()},
        "2025_total_words": sum(p["words"] for p in o25.values()),
        "2025_chunks": sum(p["chunks"] for p in o25.values()),
        "2021_chunks": sum(p["chunks"] for p in o21.values()),
        "2025_de_chunks": sum(p["chunks"] for p in o25de.values()),
        "headings_2025_example": o25["A05_2025-Injection"]["headings"],
        "unique_cwes_2025": len(m25), "unique_cwes_2021": len(m21),
        "cwes_in_both": len(set(m25) & set(m21)),
        "cwes_in_more_than_one_category_2025": sum(
            1 for c in m25 if sum(c in p["mapped_cwes"] for p in o25.values()) > 1),
    }

    # ---------- KEV ----------
    kev = json.loads((DATA / "kev.json").read_text())
    vulns = kev["vulnerabilities"]
    kev_rows = [{"id": v["cveID"], "cwes": v.get("cwes", []), "date": v["dateAdded"]} for v in vulns]
    kev_ids = {v["cveID"] for v in vulns}
    s["kev"] = {
        "version": kev.get("catalogVersion"), "released": kev.get("dateReleased"),
        "count": len(vulns), "fields": sorted(vulns[0].keys()),
        "first_added": min(v["dateAdded"] for v in vulns), "last_added": max(v["dateAdded"] for v in vulns),
        "added_by_year": dict(sorted(Counter(v["dateAdded"][:4] for v in vulns).items())),
        "ransomware_known": Counter(v.get("knownRansomwareCampaignUse") for v in vulns),
        "top_vendors": Counter(v["vendorProject"] for v in vulns).most_common(8),
        "avg_desc_chars": round(sum(len(v["shortDescription"]) for v in vulns) / len(vulns)),
        "owasp_2025": mapped_share(kev_rows, m25),
    }
    # Demo question: exploited injection flaws added this year
    a05 = set(o25["A05_2025-Injection"]["mapped_cwes"])
    year = s["kev"]["last_added"][:4]
    demo = [v for v in vulns if v["dateAdded"].startswith(year) and a05 & set(v.get("cwes", []))]
    s["kev"]["demo_injection_this_year"] = {"year": year, "count": len(demo),
                                            "examples": [(v["cveID"], v["vendorProject"], v["product"]) for v in demo[:5]]}

    # ---------- NVD recent sample (general) ----------
    recent_path = DATA / "nvd_recent90.json"
    if recent_path.exists():
        rec = json.loads(recent_path.read_text())
        s["nvd_recent90"] = {
            "count": len(rec),
            "status": Counter(r["status"] for r in rec).most_common(6),
            "with_score": sum(r["score"] is not None for r in rec),
            "severity": Counter(r["severity"] for r in rec),
            "avg_desc_chars": round(sum(len(r["description"]) for r in rec) / max(1, len(rec))),
            "with_product": sum(bool(r["vendor_products"]) for r in rec),
            "in_kev": sum(r["id"] in kev_ids for r in rec),
            "owasp_2025": mapped_share(rec, m25),
            "top_cwes": Counter(c for r in rec for c in r["cwes"]).most_common(10),
        }

    # ---------- OWASP LLM Top 10 ----------
    llm, llmde = md_stats(DATA / "owasp_llm/en"), md_stats(DATA / "owasp_llm/de")
    s["owasp_llm"] = {
        "pages": {k: {x: v[x] for x in ("words", "chunks")} | {"atlas_ids": len(v["atlas_ids"]), "cwes": v["mapped_cwes"] or sorted(set(CWE_RE.findall((DATA / f"owasp_llm/en/{k}.md").read_text())))} for k, v in llm.items()},
        "total_words": sum(p["words"] for p in llm.values()),
        "chunks": sum(p["chunks"] for p in llm.values()),
        "de_chunks": sum(p["chunks"] for p in llmde.values()),
        "headings_example": llm["LLM01_PromptInjection"]["headings"],
        "atlas_ids_total": len({i for p in llm.values() for i in p["atlas_ids"]}),
    }

    # ---------- MITRE ATLAS ----------
    atlas = yaml.safe_load((DATA / "ATLAS.yaml").read_text())
    m = atlas["matrices"][0]
    techs, mits, cases = m["techniques"], m["mitigations"], atlas["case-studies"]
    tech_ids = {t["id"] for t in techs}
    atlas_text = sum(len(str(t.get("description", ""))) for t in techs + mits + m["tactics"]) + \
        sum(len(str(c.get("summary", ""))) + sum(len(str(p.get("description", ""))) for p in c.get("procedure", [])) for c in cases)
    linked = {i for p in llm.values() for i in p["atlas_ids"]}
    s["atlas"] = {
        "version": atlas["version"], "tactics": len(m["tactics"]), "techniques": len(techs),
        "subtechniques": sum("." in t["id"].split("T")[-1] for t in techs),
        "mitigations": len(mits), "case_studies": len(cases),
        "maturity": Counter(t.get("maturity") for t in techs),
        "with_attack_ref": sum(bool(t.get("ATT&CK-reference")) for t in techs),
        "case_years": dict(sorted(Counter(str(c.get("incident-date"))[:4] for c in cases).items())),
        "case_types": Counter(c.get("case-study-type") for c in cases),
        "text_chars": atlas_text, "est_chunks": -(-atlas_text // CHUNK) + len(techs) + len(mits) + len(cases),
        "llm_top10_ids_found_in_atlas": f"{len(linked & tech_ids)}/{len(linked)}",
        "cves_mentioned_in_atlas": len(set(CVE_RE.findall((DATA / "ATLAS.yaml").read_text()))),
    }

    # ---------- NVD AI software ----------
    ai_path = DATA / "nvd_ai.json"
    if ai_path.exists():
        ai = json.loads(ai_path.read_text())
        rows = ai["cves"]
        # Generic keywords catch noise; report the strict subset without them too.
        generic = {"llm", "large language model", "prompt injection", "h2o", "onnx", "keras"}
        strict = [r for r in rows if set(r["keywords"]) - generic]
        s["nvd_ai"] = {
            "hits_per_keyword": ai["hits"], "unique": len(rows), "unique_without_generic_keywords": len(strict),
            "by_year": dict(sorted(Counter(r["published"][:4] for r in rows).items())),
            "severity": Counter(r["severity"] for r in rows),
            "with_cwe": sum(bool(r["cwes"]) for r in rows),
            "in_kev": sorted(r["id"] for r in rows if r["id"] in kev_ids),
            "owasp_2025": mapped_share(rows, m25),
            "top_cwes": Counter(c for r in rows for c in r["cwes"]).most_common(10),
            "top_products": Counter(p for r in rows for p in r["vendor_products"]).most_common(15),
            "avg_desc_chars": round(sum(len(r["description"]) for r in rows) / max(1, len(rows))),
            "prompt_injection_examples": [(r["id"], r["description"][:140]) for r in rows if "prompt injection" in r["keywords"]][:4],
        }

    out = json.dumps(s, indent=1, default=str)
    (DATA / "summary.json").write_text(out)
    print(out)


if __name__ == "__main__":
    main()

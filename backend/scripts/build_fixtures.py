"""Build the snapshot (fixtures/) from the raw downloads in snapshot_raw/. Moved from proto.

Run from backend/:  uv run python -m scripts.build_fixtures
Offline: reads snapshot_raw/ only. The NVD, KEV, OWASP and ATLAS files there are the ones
feasibility/fetch.py downloaded on 2026-10-13.
"""
import json
import re
import shutil
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "snapshot_raw"
OUT = HERE.parent / "fixtures"
AS_OF = "2026-10-13"

LLM_REPO = "https://github.com/OWASP/www-project-top-10-for-large-language-model-applications/blob/main/2_0_vulns"
WEB_REPO = "https://github.com/OWASP/Top10/blob/master/2025/docs/en"

# product id -> (display name, aliases matched in CPE product names and descriptions)
PRODUCTS = {
    "langflow": ("Langflow", ["langflow"]),
    "open-webui": ("Open WebUI", ["open webui", "open-webui", "open_webui", "openwebui"]),
    "flowise": ("Flowise", ["flowise"]),
    "vllm": ("vLLM", ["vllm"]),
    "langchain": ("LangChain", ["langchain", "langchainjs"]),
    "dify": ("Dify", ["dify"]),
    "gradio": ("Gradio", ["gradio"]),
    "ollama": ("Ollama", ["ollama"]),
    "llama.cpp": ("llama.cpp", ["llama.cpp", "llama_cpp"]),
    "litellm": ("LiteLLM", ["litellm"]),
    "anything-llm": ("AnythingLLM", ["anything-llm", "anythingllm"]),
    "llamaindex": ("LlamaIndex", ["llama_index", "llamaindex", "llama-index"]),
}

LINK_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)(\{[^}]*\})?")  # images, with mkdocs attributes


def clean_md(text: str) -> str:
    return LINK_RE.sub("", text).strip() + "\n"


def owasp(raw: Path, out: Path) -> dict:
    """Copy the 20 pages, renamed to their code, and build the CWE -> category map."""
    cwe_map, names, llm_atlas = {}, {}, {}
    for kind, folder, repo in (("owasp_llm", raw / "owasp_llm/en", LLM_REPO),
                               ("owasp_web", raw / "owasp/2025/en", WEB_REPO)):
        dest = out / kind
        shutil.rmtree(dest, ignore_errors=True)
        dest.mkdir(parents=True)
        for f in sorted(folder.glob("*.md")):
            code = f.stem.split("_")[0]  # LLM01, A05
            text = clean_md(f.read_text(encoding="utf-8"))
            title = re.search(r"^#+ (.+)$", text, re.M).group(1).strip()
            names[code] = {"title": title, "url": f"{repo}/{f.name}", "kind": kind}
            (dest / f"{code}.md").write_text(text, encoding="utf-8")
            if kind == "owasp_web":
                mapped = text.split("List of Mapped CWEs")[-1]
                for cwe in re.findall(r"CWE-\d+", mapped):
                    cwe_map.setdefault(cwe, code)
            else:
                llm_atlas[code] = sorted(set(re.findall(r"AML\.T\d{4}(?:\.\d{3})?", text)))
    (out / "owasp.json").write_text(json.dumps(
        {"categories": names, "cwe_to_web": dict(sorted(cwe_map.items(), key=lambda kv: int(kv[0][4:]))),
         "llm_to_atlas": llm_atlas}, indent=1))
    return {"pages": len(names), "mapped_cwes": len(cwe_map)}


def atlas(raw: Path, out: Path) -> dict:
    d = yaml.safe_load((raw / "ATLAS.yaml").read_text())
    m = d["matrices"][0]
    tactics = {t["id"]: t["name"] for t in m["tactics"]}
    techs = {t["id"]: t for t in m["techniques"]}
    result = {
        "version": d["version"],
        "tactics": [{"id": k, "name": v} for k, v in tactics.items()],
        "techniques": [],
        "mitigations": [],
        "case_studies": [],
    }
    for t in m["techniques"]:
        parent = t["id"].rsplit(".", 1)[0] if t["id"].count(".") == 2 else None
        tac = t.get("tactics") or (techs.get(parent, {}).get("tactics") if parent else []) or []
        result["techniques"].append({
            "id": t["id"], "name": t["name"], "parent": parent, "description": t["description"].strip(),
            "tactics": [tactics.get(x, x) for x in tac], "maturity": t.get("maturity"),
            "modified": str(t.get("modified_date")), "url": f"https://atlas.mitre.org/techniques/{t['id']}",
        })
    for mi in m["mitigations"]:
        result["mitigations"].append({
            "id": mi["id"], "name": mi["name"], "description": mi["description"].strip(),
            "techniques": [x["id"] for x in mi.get("techniques", [])],
            "modified": str(mi.get("modified_date")), "url": f"https://atlas.mitre.org/mitigations/{mi['id']}",
        })
    for c in d["case-studies"]:
        result["case_studies"].append({
            "id": c["id"], "name": c["name"], "summary": str(c.get("summary", "")).strip(),
            "date": str(c.get("incident-date")), "type": c.get("case-study-type"), "target": c.get("target"),
            "techniques": sorted({p["technique"] for p in c.get("procedure", []) if p.get("technique")}),
            "url": f"https://atlas.mitre.org/studies/{c['id']}",
        })
    (out / "atlas.json").write_text(json.dumps(result, indent=1))
    return {k: len(v) for k, v in result.items() if isinstance(v, list)} | {"version": d["version"]}


def match_product(row: dict) -> tuple[str | None, str | None]:
    """CPE product name first; else the product named earliest in the description."""
    for cpe in row["vendor_products"]:
        name = cpe.split(":", 1)[1].lower()
        for pid, (_, aliases) in PRODUCTS.items():
            if name in aliases or name.replace("_", "-") in aliases:
                return pid, "cpe"
    desc = row["description"].lower()
    best = None
    for pid, (_, aliases) in PRODUCTS.items():
        for a in aliases:
            m = re.search(rf"(?<![\w-]){re.escape(a)}(?![\w-])", desc)
            if m and (best is None or m.start() < best[1]):
                best = (pid, m.start())
    return (best[0], "text") if best else (None, None)


def cves(raw: Path, out: Path, cwe_map: dict) -> dict:
    nvd = json.loads((raw / "nvd_ai.json").read_text())["cves"]
    kev = {v["cveID"]: v for v in json.loads((raw / "kev.json").read_text())["vulnerabilities"]}
    rows, kev_rows = [], []
    for r in nvd:
        if r["status"] == "Rejected":
            continue
        pid, how = match_product(r)
        if not pid:
            continue
        cats = sorted({cwe_map[c] for c in r["cwes"] if c in cwe_map})
        rows.append({
            "id": r["id"], "published": r["published"][:10], "product": pid, "product_source": how,
            "severity": r["severity"], "cvss": r["score"], "cwes": r["cwes"], "owasp": cats[0] if cats else None,
            "description": " ".join(r["description"].split()), "kev": r["id"] in kev,
            "url": f"https://nvd.nist.gov/vuln/detail/{r['id']}",
        })
        if r["id"] in kev:
            v = kev[r["id"]]
            kev_rows.append({k: v.get(k) for k in ("cveID", "vulnerabilityName", "dateAdded", "dueDate",
                                                   "knownRansomwareCampaignUse", "requiredAction")})
    rows.sort(key=lambda r: (r["published"], r["id"]), reverse=True)
    (out / "cves.json").write_text(json.dumps(
        {"products": {k: v[0] for k, v in PRODUCTS.items()}, "cves": rows}, indent=1))
    (out / "kev.json").write_text(json.dumps(kev_rows, indent=1))
    return {"cves": len(rows), "kev": len(kev_rows), "by_product": dict(Counter(r["product"] for r in rows)),
            "product_source": dict(Counter(r["product_source"] for r in rows))}


def build(raw: Path = RAW, out: Path = OUT) -> dict:
    out.mkdir(exist_ok=True)
    o = owasp(raw, out)
    a = atlas(raw, out)
    cwe_map = json.loads((out / "owasp.json").read_text())["cwe_to_web"]
    c = cves(raw, out, cwe_map)
    kev_meta = json.loads((raw / "kev.json").read_text())
    manifest = {
        "as_of": AS_OF,
        "note": "A frozen snapshot of public data, built by scripts/build_fixtures.py.",
        "sources": [
            {"name": "OWASP Top 10 for LLM Applications 2025", "licence": "CC BY-SA 4.0",
             "url": "https://github.com/OWASP/www-project-top-10-for-large-language-model-applications",
             "retrieved": AS_OF, "count": 10},
            {"name": "OWASP Top 10 2025", "licence": "CC BY-SA 4.0", "url": "https://github.com/OWASP/Top10",
             "retrieved": AS_OF, "count": 10, "mapped_cwes": o["mapped_cwes"]},
            {"name": f"MITRE ATLAS {a['version']}", "licence": "Apache 2.0",
             "url": "https://github.com/mitre-atlas/atlas-data", "retrieved": AS_OF,
             "count": a["techniques"] + a["mitigations"] + a["case_studies"]},
            {"name": "NVD CVE API 2.0", "licence": "Public (US government)",
             "url": "https://nvd.nist.gov/developers/vulnerabilities", "retrieved": AS_OF, "count": c["cves"]},
            {"name": f"CISA KEV {kev_meta.get('catalogVersion')}", "licence": "Public (US government)",
             "url": "https://www.cisa.gov/known-exploited-vulnerabilities-catalog", "retrieved": AS_OF,
             "count": c["kev"]},
        ],
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1))
    return {"owasp": o, "atlas": a, "cves": c}


def main() -> None:
    print(json.dumps(build(), indent=1))


if __name__ == "__main__":
    main()

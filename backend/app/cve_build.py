"""The shared build code: raw NVD, KEV, OSV and EPSS data in, the snapshot's CVE data out.

One home for product matching, the CWE -> OWASP join, KEV joining, OSV parsing and EPSS
attaching. The snapshot script (scripts/build_fixtures.py, scripts/snapshot_additions.py) calls it,
and so will the live refresh, so live and snapshot data never disagree on the same CVE.
Pure functions, no network, no files. Facts relied on are in docs/SOURCE-CHECKS.md (OSV.dev, EPSS).
"""
import re

# product id -> (display name, aliases matched in CPE product names and descriptions)
PRODUCTS: dict[str, tuple[str, list[str]]] = {
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

# Which packages carry each product's versions in OSV. Fixed data, checked 2026-10-14 (SOURCE-CHECKS.md).
# coverage: "package" = OSV has fixed versions by package; "commits" = git commit ranges only; "none".
PACKAGES: dict[str, dict] = {
    "langflow": {"coverage": "package", "packages": [("PyPI", "langflow")]},
    "open-webui": {"coverage": "package", "packages": [("PyPI", "open-webui")]},
    "flowise": {"coverage": "package", "packages": [("npm", "flowise"), ("npm", "flowise-components")]},
    "vllm": {"coverage": "package", "packages": [("PyPI", "vllm")]},
    "langchain": {"coverage": "package",
                  "packages": [("PyPI", "langchain"), ("PyPI", "langchain-core"), ("PyPI", "langchain-community")]},
    "gradio": {"coverage": "package", "packages": [("PyPI", "gradio")]},
    "litellm": {"coverage": "package", "packages": [("PyPI", "litellm")]},
    "ollama": {"coverage": "package", "packages": [("Go", "github.com/ollama/ollama")]},
    "llamaindex": {"coverage": "package", "packages": [("PyPI", "llama-index"), ("PyPI", "llama-index-core")]},
    "llama.cpp": {"coverage": "commits", "packages": []},
    "dify": {"coverage": "none", "packages": []},
    "anything-llm": {"coverage": "none", "packages": []},
}

KEV_FIELDS = ("cveID", "vulnerabilityName", "dateAdded", "dueDate", "knownRansomwareCampaignUse", "requiredAction")


# --- NVD: product, OWASP, KEV ----------------------------------------------------------------

def match_product(row: dict) -> tuple[str | None, str | None]:
    """CPE product name first ("cpe"); else the product named earliest in the description ("text")."""
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


def owasp_category(cwes: list[str], cwe_to_web: dict[str, str]) -> str | None:
    """The OWASP Top 10 2025 category for a CVE's CWEs: the lowest code when several map."""
    cats = sorted({cwe_to_web[c] for c in cwes if c in cwe_to_web})
    return cats[0] if cats else None


def cve_record(row: dict, cwe_to_web: dict[str, str], kev_ids: set[str]) -> dict | None:
    """One NVD row -> the snapshot's CVE record. None when it's rejected or names no tracked product."""
    if row["status"] == "Rejected":
        return None
    pid, how = match_product(row)
    if not pid:
        return None
    return {
        "id": row["id"], "published": row["published"][:10], "product": pid, "product_source": how,
        "severity": row["severity"], "cvss": row["score"], "cwes": row["cwes"],
        "owasp": owasp_category(row["cwes"], cwe_to_web),
        "description": " ".join(row["description"].split()), "kev": row["id"] in kev_ids,
        "url": f"https://nvd.nist.gov/vuln/detail/{row['id']}",
    }


def build_cves(nvd_rows: list[dict], cwe_to_web: dict[str, str], kev_catalogue: dict) -> tuple[list[dict], list[dict]]:
    """NVD rows and the KEV catalogue -> (CVE records newest first, their KEV entries in NVD order)."""
    kev = {v["cveID"]: v for v in kev_catalogue["vulnerabilities"]}
    rows, kev_rows = [], []
    for r in nvd_rows:
        rec = cve_record(r, cwe_to_web, set(kev))
        if rec is None:
            continue
        rows.append(rec)
        if rec["kev"]:
            kev_rows.append({k: kev[rec["id"]].get(k) for k in KEV_FIELDS})
    rows.sort(key=lambda r: (r["published"], r["id"]), reverse=True)
    return rows, kev_rows


# --- OSV: versions by package -----------------------------------------------------------------

def package_key(ecosystem: str, name: str) -> str:
    return f"{ecosystem}/{name}"


def _owner(key: str) -> str | None:
    for pid, p in PACKAGES.items():
        if key in (package_key(*pk) for pk in p["packages"]):
            return pid
    return None


def _ranges(affected: dict) -> list[dict]:
    """OSV's event list -> plain ranges. Git commit ranges are skipped: they carry no versions."""
    out = []
    for r in affected.get("ranges", []):
        if r.get("type") == "GIT":
            continue
        current = None
        for e in r.get("events", []):
            if "introduced" in e:
                current = {"introduced": e["introduced"], "fixed": None, "last_affected": None}
                out.append(current)
            elif current and ("fixed" in e or "last_affected" in e):
                current["fixed"] = e.get("fixed")
                current["last_affected"] = e.get("last_affected")
                current = None
    return out


def _rank(record: dict) -> tuple:
    return (not record["id"].startswith("GHSA-"), record["id"])  # GHSA first, then a stable order


def osv_versions(raw: dict[str, list[dict]], snapshot_ids: set[str], as_of: str) -> dict:
    """Per CVE and package: affected ranges and fixed versions.

    `raw` holds OSV's records per queried package ("PyPI/langflow"). PyPI advisories come twice
    (GHSA and PYSEC): records are de-duplicated by CVE alias and the GHSA one is kept. Records
    published after `as_of`, withdrawn ones and ones without a CVE id are left out.
    """
    best: dict[tuple[str, str], dict] = {}  # (cve, package key) -> record
    outside, n_records = set(), 0
    for key, records in raw.items():
        for r in records:
            n_records += 1
            if r.get("withdrawn") or r.get("published", "")[:10] > as_of:
                continue
            for cve in (a for a in r.get("aliases", []) + [r["id"]] if a.startswith("CVE-")):
                if cve not in snapshot_ids:
                    outside.add(cve)
                    continue
                if (cve, key) not in best or _rank(r) < _rank(best[(cve, key)]):
                    best[(cve, key)] = r
    cves: dict[str, list[dict]] = {}
    for (cve, key), r in sorted(best.items()):
        ecosystem, name = key.split("/", 1)
        ranges = [rg for a in r["affected"]
                  if (a["package"]["ecosystem"], a["package"]["name"]) == (ecosystem, name) for rg in _ranges(a)]
        cves.setdefault(cve, []).append({
            "product": _owner(key), "ecosystem": ecosystem, "package": name, "advisory": r["id"],
            "ranges": ranges, "fixed": [rg["fixed"] for rg in ranges if rg["fixed"]],
        })
    return {"cves": cves, "counts": {"records": n_records, "cves": len(cves), "not_in_snapshot": len(outside)}}


def product_check(cve_rows: list[dict], osv_cves: dict[str, list[dict]]) -> dict:
    """Cross-check each CVE whose product came from description text against OSV's packages.

    confirmed: OSV lists it under one of that product's packages. conflicting: only under another
    product's. unknown: OSV has no package record for it (OSV isn't a full CVE list). The app shows
    every text-matched CVE that isn't confirmed as a "possible match".
    """
    checked = {}
    for row in cve_rows:
        if row["product_source"] != "text":
            continue
        products = sorted({e["product"] for e in osv_cves.get(row["id"], [])})
        result = "confirmed" if row["product"] in products else "conflicting" if products else "unknown"
        checked[row["id"]] = {"result": result, "osv_products": products}
    counts = {"text_matched": len(checked)}
    counts |= {r: sum(c["result"] == r for c in checked.values()) for r in ("confirmed", "conflicting", "unknown")}
    return {"counts": counts, "cves": checked}


# --- EPSS ----------------------------------------------------------------------------------------

def epss_scores(raw: dict, cve_ids: list[str]) -> dict:
    """EPSS score (chance of exploitation in the next 30 days) and percentile per CVE, as of `raw['date']`."""
    wanted = set(cve_ids)
    scores = {r["cve"]: {"score": float(r["epss"]), "percentile": float(r["percentile"]), "date": r["date"]}
              for r in sorted(raw["rows"], key=lambda r: r["cve"]) if r["cve"] in wanted}
    return {"date": raw["date"], "scores": scores,
            "counts": {"scored": len(scores), "missing": len(wanted) - len(scores)}}

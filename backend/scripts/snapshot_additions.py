"""Snapshot additions (spec A): OSV versions, EPSS scores and the product-match check.

Two steps, so the build stays offline:
- fetch (network, run by hand): `fetch_osv` and `fetch_epss` save the raw replies to snapshot_raw/.
- build (offline, tested): `osv_versions`, `epss_scores` and `product_check` turn those raw files into
  fixtures/osv.json, epss.json and product_check.json.

Facts relied on are in docs/SOURCE-CHECKS.md (OSV.dev, EPSS).
"""
import json
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path

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

OSV_QUERY = "https://api.osv.dev/v1/query"
EPSS_API = "https://api.first.org/data/v1/epss"
EPSS_MAX_CVE_CHARS = 2000  # the API's limit on the comma-separated cve= list


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
    published after the snapshot date, withdrawn ones and ones without a CVE id are left out.
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


def epss_scores(raw: dict, cve_ids: list[str]) -> dict:
    """EPSS score (chance of exploitation in the next 30 days) and percentile per CVE, as of `raw['date']`."""
    wanted = set(cve_ids)
    scores = {r["cve"]: {"score": float(r["epss"]), "percentile": float(r["percentile"]), "date": r["date"]}
              for r in sorted(raw["rows"], key=lambda r: r["cve"]) if r["cve"] in wanted}
    return {"date": raw["date"], "scores": scores,
            "counts": {"scored": len(scores), "missing": len(wanted) - len(scores)}}


# --- Fetch (network). `get_json` / `post_json` are passed in, so tests use fakes. -----------------

def _trim(record: dict) -> dict:
    """Keep what the build reads. The `versions` lists can run to hundreds of entries per package."""
    out = {k: record[k] for k in ("id", "aliases", "published", "modified", "withdrawn") if k in record}
    out.setdefault("aliases", [])
    out["affected"] = [{"package": {"ecosystem": a["package"]["ecosystem"], "name": a["package"]["name"]},
                        "ranges": a.get("ranges", [])} for a in record.get("affected", []) if "package" in a]
    return out


def fetch_osv(post_json: Callable[[str, dict], dict], packages: dict = PACKAGES,
              sleep: Callable[[float], None] = time.sleep) -> dict[str, list[dict]]:
    """Every OSV record per package, queried by package (not by CVE id: those carry commit ranges only)."""
    raw = {}
    for p in packages.values():
        for ecosystem, name in p["packages"]:
            records, body = [], {"package": {"ecosystem": ecosystem, "name": name}}
            while True:
                reply = post_json(OSV_QUERY, body)
                records += [_trim(v) for v in reply.get("vulns", [])]
                if not reply.get("next_page_token"):
                    break
                body = {**body, "page_token": reply["next_page_token"]}
                sleep(0.2)
            raw[package_key(ecosystem, name)] = records
            sleep(0.2)
    return raw


def fetch_epss(get_json: Callable[[str], dict], cve_ids: list[str], date: str,
               sleep: Callable[[float], None] = time.sleep) -> dict:
    """EPSS for every CVE as of `date`, in as few calls as the API's 2,000-character cve= limit allows."""
    batches, batch = [], []
    for cve in cve_ids:
        if batch and len(",".join(batch + [cve])) > EPSS_MAX_CVE_CHARS:
            batches.append(batch)
            batch = []
        batch.append(cve)
    if batch:
        batches.append(batch)
    rows = []
    for b in batches:
        query = urllib.parse.urlencode({"date": date, "limit": len(b)})
        rows += get_json(f"{EPSS_API}?{query}&cve={','.join(b)}").get("data", [])
        sleep(0.5)
    return {"date": date, "rows": rows}


def build_additions(raw_dir: Path, out: Path, cve_rows: list[dict], as_of: str) -> dict:
    """Offline: snapshot_raw/osv.json and epss.json -> fixtures/osv.json, epss.json, product_check.json.

    Returns the numbers the manifest records.
    """
    raw_osv = json.loads((raw_dir / "osv.json").read_text())
    raw_epss = json.loads((raw_dir / "epss.json").read_text())
    ids = [r["id"] for r in cve_rows]
    osv = osv_versions(raw_osv["packages"], set(ids), as_of)
    epss = epss_scores(raw_epss, ids)
    check = product_check(cve_rows, osv["cves"])
    products = {pid: {"coverage": p["coverage"],
                      "packages": [{"ecosystem": e, "name": n} for e, n in p["packages"]]}
                for pid, p in PACKAGES.items()}
    _write(out / "osv.json", {"as_of": as_of, "retrieved": raw_osv["retrieved"], "products": products,
                              "counts": osv["counts"], "cves": osv["cves"]})
    _write(out / "epss.json", {"date": epss["date"], "retrieved": raw_epss.get("retrieved"),
                               "counts": epss["counts"], "scores": epss["scores"]})
    _write(out / "product_check.json", check)
    return {"osv": {"retrieved": raw_osv["retrieved"], "cves": osv["counts"]["cves"]},
            "epss": {"retrieved": raw_epss.get("retrieved"), "date": epss["date"], **epss["counts"]},
            "product_check": check["counts"]}


def _write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=1) + "\n")


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

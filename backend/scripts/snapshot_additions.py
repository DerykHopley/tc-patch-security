"""Snapshot additions (spec A): OSV versions, EPSS scores and the product-match check.

Two steps, so the build stays offline:
- fetch (network, run by hand): `fetch_osv` and `fetch_epss` save the raw replies to snapshot_raw/.
- build (offline, tested): `build_additions` turns those raw files into fixtures/osv.json, epss.json
  and product_check.json, with the shared build code in app/cve_build.py (also used by the live refresh).

Facts relied on are in docs/SOURCE-CHECKS.md (OSV.dev, EPSS).
"""
import json
import time
import urllib.parse
from collections.abc import Callable
from pathlib import Path

from app.cve_build import PACKAGES, epss_scores, osv_versions, package_key, product_check

OSV_QUERY = "https://api.osv.dev/v1/query"
EPSS_API = "https://api.first.org/data/v1/epss"
EPSS_MAX_CVE_CHARS = 2000  # the API's limit on the comma-separated cve= list


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

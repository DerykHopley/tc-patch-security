"""Snapshot additions (spec A): OSV versions, EPSS scores and the product-match check.

Two steps, so the build stays offline:
- fetch (network, run by hand): `build_fixtures.py --fetch` saves the raw replies to snapshot_raw/, through the real
  Feeds adapter (`app.feeds.HttpFeeds`, B03), the same one the live refresh uses.
- build (offline, tested): `build_additions` turns those raw files into fixtures/osv.json, epss.json
  and product_check.json, with the shared build code in app/cve_build.py (also used by the live refresh).

Facts relied on are in docs/SOURCE-CHECKS.md (OSV.dev, EPSS).
"""
import json
from pathlib import Path

from app.cve_build import PACKAGES, epss_scores, osv_versions, product_check

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

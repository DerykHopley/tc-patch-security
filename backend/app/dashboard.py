"""Numbers for the dashboard tiles and charts, and the CVE table. Moved from proto (its D1, D2)."""
import datetime as dt
from collections import Counter

from app.knowledge import SEVERITY_ORDER

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def _row(cve: dict, status: str, k) -> dict:
    kev = k.cves.kev.get(cve["id"])
    cat = k.category(cve["owasp"])
    return {
        "id": cve["id"], "product": cve["product"], "product_name": k.products[cve["product"]],
        "severity": cve["severity"], "cvss": cve["cvss"], "published": cve["published"],
        "owasp": cve["owasp"], "owasp_title": cat["title"] if cat else None,
        "kev": bool(kev), "kev_due": kev["dueDate"] if kev else None,
        "status": status, "summary": cve["description"][:220], "url": cve["url"],
    }


def _sort_key(r: dict):
    # KEV first, then CVSS highest first, then newest (D2)
    return (not r["kev"], -(r["cvss"] or 0), _neg_date(r["published"]))


def _neg_date(iso: str) -> int:
    return -dt.date.fromisoformat(iso).toordinal()


def watched_rows(k, data: dict) -> list[dict]:
    from app.state import State

    watch = set(data["watchlist"])
    return [_row(c, State.status_of(c, data), k) for c in k.cves.all() if c["product"] in watch]


def list_cves(k, data: dict, product=None, severity_min=None, status="open", limit=50, offset=0) -> dict:
    rows = watched_rows(k, data)
    if product:
        rows = [r for r in rows if r["product"] == product]
    if severity_min:
        rows = [r for r in rows if SEVERITY_ORDER.get(r["severity"] or "", 0) >= SEVERITY_ORDER[severity_min]]
    if status != "all":
        rows = [r for r in rows if r["status"] == status]
    rows.sort(key=_sort_key)
    return {"total": len(rows), "rows": rows[offset:offset + limit]}


def _months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end[:7]:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def summary(k, data: dict, as_of: str) -> dict:
    rows = watched_rows(k, data)
    open_rows = [r for r in rows if r["status"] == "open"]
    since = (dt.date.fromisoformat(as_of) - dt.timedelta(days=30)).isoformat()
    kev_open = sorted((r for r in open_rows if r["kev"]), key=lambda r: r["kev_due"] or "9999")

    by_product = []
    for pid in data["watchlist"]:
        counts = Counter(r["severity"] or "NONE" for r in open_rows if r["product"] == pid)
        by_product.append({"product": pid, "name": k.products[pid], "total": sum(counts.values()),
                           **{s: counts.get(s, 0) for s in SEVERITIES}})

    month_counts = Counter(r["published"][:7] for r in rows if r["published"] <= as_of)
    per_month = [{"month": m, "count": month_counts.get(m, 0)} for m in _months("2024-01", as_of)]

    owasp_counts = Counter(r["owasp"] for r in open_rows if r["owasp"])
    by_owasp = [{"code": c, "title": k.category(c)["title"], "count": n} for c, n in sorted(owasp_counts.items())]
    unmapped = sum(1 for r in open_rows if not r["owasp"])

    incidents = sorted((c for c in k.atlas["case_studies"] if c["type"] == "incident"),
                       key=lambda c: c["date"], reverse=True)[:5]

    return {
        "as_of": as_of,
        "watchlist": data["watchlist"],
        "products": [{"id": p, "name": n} for p, n in k.products.items()],
        "kpis": {
            "open": len(open_rows),
            "critical": sum(r["severity"] == "CRITICAL" for r in open_rows),
            "kev": len(kev_open),
            "kev_next_due": {"cve": kev_open[0]["id"], "due": kev_open[0]["kev_due"]} if kev_open else None,
            "new_30d": sum(since < r["published"] <= as_of for r in rows),
        },
        "by_product": by_product,
        "per_month": per_month,
        "by_owasp": by_owasp,
        "owasp_unmapped": unmapped,
        "latest_incidents": [{"id": c["id"], "name": c["name"], "date": c["date"], "url": c["url"],
                              "summary": c["summary"][:240]} for c in incidents],
        "freshness": k.manifest["sources"],
    }

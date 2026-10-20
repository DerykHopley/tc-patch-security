"""Numbers for the dashboard tiles and charts. Moved from proto (its D1). The rows come from app.watched."""
import datetime as dt
from collections import Counter

from app import cve_filters
from app.cve_build import owasp_categories
from app.watched import WatchedCves

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def _months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end[:7]:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def applied_filter(k, watched: WatchedCves, value: str | None) -> list[str]:
    """The dashboard's product filter (A15b): `a,b` from the URL, as watched product ids in watchlist order.
    Unknown or unwatched products are ignored, so a stale link still opens; none left means every watched product."""
    wanted = {cve_filters.product(v, k.resolve_product) for v in (value or "").split(",") if v.strip()}
    return [p for p in watched.watchlist if p in wanted]


def summary(k, watched: WatchedCves, products: list[str] | None = None) -> dict:
    """Tiles, charts and side panels. `products`: the dashboard's filter (applied_filter); empty = every watched."""
    as_of, watchlist = watched.as_of, watched.watchlist
    every = watched.rows(status="all")
    rows = [r for r in every if r["product"] in products] if products else every
    open_rows = [r for r in rows if r["open"]]
    since = (dt.date.fromisoformat(as_of) - dt.timedelta(days=30)).isoformat()
    first_new_day = (dt.date.fromisoformat(as_of) - dt.timedelta(days=29)).isoformat()
    kev_open = sorted((r for r in open_rows if r["kev"]), key=lambda r: r["due_date"])  # your due date (A16)

    by_product = []
    for pid in products or watchlist:
        counts = Counter(r["severity"] or "NONE" for r in open_rows if r["product"] == pid)
        by_product.append({"product": pid, "name": k.products[pid], "total": sum(counts.values()),
                           **{s: counts.get(s, 0) for s in SEVERITIES}})

    month_counts = Counter(r["published"][:7] for r in rows if r["published"] <= as_of)
    per_month = [{"month": m, "count": month_counts.get(m, 0)} for m in _months("2024-01", as_of)]

    # B43 (#25): a CVE counts under every web category its CWEs map to, so the bars can add up to more than the open
    # CVEs. The row's single `owasp` (the lowest code) stays for the CVE table.
    cats = {r["id"]: owasp_categories(k.cves.get(r["id"])["cwes"], k.owasp["cwe_to_web"]) for r in open_rows}
    owasp_counts = Counter(c for found in cats.values() for c in found)
    by_owasp = [{"code": c, "title": k.category(c)["title"], "count": n} for c, n in sorted(owasp_counts.items())]
    unmapped = sum(1 for found in cats.values() if not found)

    incidents = sorted((c for c in k.atlas["case_studies"] if c["type"] == "incident"),
                       key=lambda c: c["date"], reverse=True)[:5]

    return {
        "as_of": as_of,
        "watchlist": watchlist,
        "filter": products or [],
        # One per watched product, whatever the filter: the filter's chips show which have open KEV CVEs
        "watched": [{"product": p, "name": k.products[p],
                     "open": sum(r["open"] and r["product"] == p for r in every),
                     "kev": sum(r["open"] and r["kev"] and r["product"] == p for r in every)}
                    for p in watchlist],
        "products": [{"id": p, "name": n} for p, n in k.products.items()],
        "kpis": {
            "open": len(open_rows),
            "critical": sum(r["severity"] == "CRITICAL" for r in open_rows),
            "kev": len(kev_open),
            "kev_next_due": {"cve": kev_open[0]["id"], "due": kev_open[0]["due_date"],
                             "overdue": kev_open[0]["overdue"], "no_fix": kev_open[0]["no_fix"]} if kev_open else None,
            "kev_overdue": sum(r["overdue"] for r in kev_open),
            "overdue": sum(r["overdue"] for r in open_rows),  # a fix exists and the due date has passed (A16b)
            "no_fix": sum(r["no_fix"] for r in open_rows),
            "review_due": sum(r["review_due"] for r in open_rows),
            "accepted": sum(r["status"] == "accepted" and not r["review_due"] for r in rows),
            "new_30d": sum(since < r["published"] <= as_of for r in rows),
            "new_since": first_new_day,  # the first of those 30 days: the tile's link filters on it
            # B43: new and not seen yet (B40), any status, for "See the N new CVEs →" (/cves?status=all&new=1)
            "new_unseen": sum(r["new"] for r in rows),
        },
        "by_product": by_product,
        "per_month": per_month,
        "by_owasp": by_owasp,
        "owasp_unmapped": unmapped,
        "latest_incidents": [{"id": c["id"], "name": c["name"], "date": c["date"], "url": c["url"],
                              "summary": c["summary"][:240]} for c in incidents],
        "freshness": k.manifest["sources"],
    }

"""Numbers for the dashboard tiles and charts, and the CVE table. Moved from proto (its D1, D2)."""
import datetime as dt
from collections import Counter

from app.app_settings import PolicySettings, PrioritySettings
from app.knowledge import SEVERITY_ORDER
from app.priority import CveFacts, priority, sort_key
from app.verdict import verdict

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW"]


def affected(k, cve: dict, data: dict) -> dict:
    """The verdict for one CVE from the product's saved usage and version (A15). Advice only: never the status."""
    from app.state import State

    f = State.fields_of(cve["product"], data)
    coverage = k.osv["products"].get(cve["product"], {}).get("coverage", "none")
    entries = [e for e in k.osv["cves"].get(cve["id"], []) if e["product"] == cve["product"]]
    v = verdict(coverage, entries, f["usage"], f["version"])
    return {"verdict": v.verdict, "verdict_reason": v.reason, "fixed_version": v.fixed_version,
            "who_acts": v.who_acts, "usage": f["usage"], "version": f["version"],
            "internet_facing": f["internet_facing"]}


def prioritised(k, cve: dict, status: str, v: dict, data: dict, as_of: str) -> dict:
    """The priority rules' output for one watched CVE (A16), from the saved policy and threshold."""
    saved = data.get("settings", {})
    kev, epss = k.cves.kev.get(cve["id"]), k.epss_of(cve["id"])
    p = priority(CveFacts(severity=cve["severity"], kev=bool(kev), epss_percentile=epss["percentile"] if epss else None,
                          verdict=v["verdict"], internet_facing=v["internet_facing"], status=status,
                          published=cve["published"], kev_added=kev["dateAdded"] if kev else None,
                          kev_deadline=kev["dueDate"] if kev else None),
                 PolicySettings.model_validate(saved.get("policy", {})), as_of,
                 PrioritySettings.model_validate(saved.get("priority", {})).epss_percentile)
    return {"priority": p.level, "priority_reasons": list(p.reasons), "priority_rule": p.rule,
            "alert_priority": p.alert_priority, "due_date": p.due_date, "due_from": p.due_from, "overdue": p.overdue}


def _row(cve: dict, status: str, k, data: dict, as_of: str) -> dict:
    kev = k.cves.kev.get(cve["id"])
    cat = k.category(cve["owasp"])
    v = affected(k, cve, data)
    return {
        "id": cve["id"], "product": cve["product"], "product_name": k.products[cve["product"]],
        "severity": cve["severity"], "cvss": cve["cvss"], "published": cve["published"],
        "owasp": cve["owasp"], "owasp_title": cat["title"] if cat else None,
        "kev": bool(kev), "kev_deadline": kev["dueDate"] if kev else None,  # CISA's, a fact; not your due date
        "status": status, "summary": cve["description"][:220], "url": cve["url"],
        "epss": k.epss_of(cve["id"]), "possible_match": k.possible_match(cve["id"]),
        **v, **prioritised(k, cve, status, v, data, as_of),
    }


def _sort_key(r: dict):
    # By priority (A16): most urgent first, then the earliest due date, then the highest CVSS, then newest
    return (*sort_key(r["priority"], r["due_date"]), -(r["cvss"] or 0), _neg_date(r["published"]))


def _neg_date(iso: str) -> int:
    return -dt.date.fromisoformat(iso).toordinal()


def watched_rows(k, data: dict, as_of: str) -> list[dict]:
    """Every CVE of a watched product, sorted by priority."""
    from app.state import State

    watch = set(data["watchlist"])
    rows = [_row(c, State.status_of(c, data), k, data, as_of) for c in k.cves.all() if c["product"] in watch]
    return sorted(rows, key=_sort_key)


def list_cves(k, data: dict, as_of: str, product=None, severity_min=None, status="open", limit=50, offset=0,
              kev=None, published_since=None, verdict=None) -> dict:
    rows = watched_rows(k, data, as_of)
    if kev is not None:
        rows = [r for r in rows if r["kev"] == kev]
    if published_since:  # inclusive, YYYY-MM-DD: the "new in 30 days" tile links here with kpis.new_since
        rows = [r for r in rows if r["published"] >= published_since]
    if product:
        rows = [r for r in rows if r["product"] == product]
    if severity_min:
        rows = [r for r in rows if SEVERITY_ORDER.get(r["severity"] or "", 0) >= SEVERITY_ORDER[severity_min]]
    if status != "all":
        rows = [r for r in rows if r["status"] == status]
    if verdict:
        rows = [r for r in rows if r["verdict"] == verdict]
    return {"total": len(rows), "rows": rows[offset:offset + limit]}


def _months(start: str, end: str) -> list[str]:
    y, m = int(start[:4]), int(start[5:7])
    out = []
    while f"{y:04d}-{m:02d}" <= end[:7]:
        out.append(f"{y:04d}-{m:02d}")
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def summary(k, data: dict, as_of: str) -> dict:
    rows = watched_rows(k, data, as_of)
    open_rows = [r for r in rows if r["status"] == "open"]
    since = (dt.date.fromisoformat(as_of) - dt.timedelta(days=30)).isoformat()
    first_new_day = (dt.date.fromisoformat(as_of) - dt.timedelta(days=29)).isoformat()
    kev_open = sorted((r for r in open_rows if r["kev"]), key=lambda r: r["due_date"])  # your due date (A16)

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
            "kev_next_due": {"cve": kev_open[0]["id"], "due": kev_open[0]["due_date"],
                             "overdue": kev_open[0]["overdue"]} if kev_open else None,
            "kev_overdue": sum(r["overdue"] for r in kev_open),
            "overdue": sum(r["overdue"] for r in open_rows),
            "new_30d": sum(since < r["published"] <= as_of for r in rows),
            "new_since": first_new_day,  # the first of those 30 days: the tile's link filters on it
        },
        "by_product": by_product,
        "per_month": per_month,
        "by_owasp": by_owasp,
        "owasp_unmapped": unmapped,
        "latest_incidents": [{"id": c["id"], "name": c["name"], "date": c["date"], "url": c["url"],
                              "summary": c["summary"][:240]} for c in incidents],
        "freshness": k.manifest["sources"],
    }

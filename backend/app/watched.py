"""Your watched CVEs: everything Patch knows about a CVE for your stack, in one place.

Built once per request from the knowledge base, your stack (one State.read(): watchlist, product fields, decisions
and the merged settings) and the as-of date. It answers three questions:

- assess(cve_id): one CVE's assessment: the verdict (A15), your decision record (A16b), its priority and due date
  (A16). A CVE whose product isn't on your watchlist is a normal answer: watched False, no status, no priority.
  A closed CVE (app.status.is_closed: fixed, not affected, accepted before its review) has no priority either (B33).
- rows(...): the CVEs page's rows for a view (its filters), sorted by priority.
- most_urgent(): the open CVE at the top of the priority order, or None.
- page(cve_id): the page for one CVE (B35): the full facts, the affected versions, the links out, and its row from
  the CVEs page when it's watched (so the two pages never disagree).

The steps (verdict, then decision, then priority, which needs the decision's review date) and the policy merge stay
inside: callers never compose them.
"""
import datetime as dt
from dataclasses import dataclass

from app.knowledge import SEVERITY_ORDER
from app.priority import LEVELS, CveFacts, Priority, priority, sort_key
from app.state import ProductFields, State
from app.status import is_closed, is_open, review_due
from app.verdict import Verdict, no_fix, verdict

# The list an OWASP category belongs to, by its kind in owasp.json. The page names it, since "A05" alone doesn't say
# which Top 10 it comes from (#25: both lists are called "Top 10").
OWASP_LISTS = {"owasp_web": "OWASP Top 10 2025 (web applications)",
               "owasp_llm": "OWASP Top 10 for LLM Applications 2025"}
OSV_URL = "https://osv.dev/vulnerability/{}"  # OSV.dev's page for a CVE id


@dataclass(frozen=True)
class Assessment:
    """Everything Patch knows about one CVE for your stack."""
    cve: dict  # the snapshot's record
    watched: bool  # its product is on your watchlist
    status: str | None  # your CVE status: open, fixed, not_affected, accepted; None off the watchlist
    verdict: Verdict  # the version check's advice, never the status
    no_fix: bool  # OSV lists no fixed version: "no fix yet", never overdue
    usage: str
    version: str | None
    internet_facing: bool
    decision: dict | None  # the current decision record
    review_date: str | None  # an accepted CVE's review date
    history: list[dict]  # every decision record, oldest first
    open: bool  # open, or accepted with its review due
    review_due: bool
    open_days: int  # days since publication, at the as-of date
    priority: Priority | None  # the rules' level, reasons and your due date; None off the watchlist or closed (B33)
    alert_priority: int | None  # the rules' level as an alert priority (5/4/3/2), closed too: kev_recheck alerts a
    # fixed CVE (B04). None off the watchlist


class WatchedCves:
    def __init__(self, knowledge, state: State, as_of: str):
        self.k = knowledge
        self.as_of = as_of
        self._stack = state.read()  # one read per request: everything below agrees with it
        self._policy = self._stack.settings.policy
        self._epss_threshold = self._stack.settings.priority.epss_percentile

    @classmethod
    def of(cls, deps) -> "WatchedCves":
        return cls(deps.knowledge, deps.state, deps.as_of)

    @property
    def watchlist(self) -> list[str]:
        """Watched product ids, in watchlist order."""
        return list(self._stack.watchlist)

    def fields_of(self, pid: str) -> ProductFields:
        """A product's usage, version and internet-facing."""
        return self._stack.fields(pid)

    def assess(self, cve_id: str) -> Assessment:
        """KeyError when the CVE isn't in the snapshot."""
        cve = self.k.cves.get(cve_id)
        if cve is None:
            raise KeyError(cve_id)
        return self._assess(cve)

    def rows(self, product: str | None = None, severity: str | None = None, status: str = "open",
             kev: bool | None = None, since: str | None = None, verdict: str | None = None,
             new: bool | None = None) -> list[dict]:
        """The CVEs page's rows for a view, most urgent first. Only watched products have rows. The filters are the
        CVE view's (app.cve_filters.CveView, checked there; pass `**view.filters()`): `product` one id or several,
        comma-separated (`langflow,ollama`, A15b); `severity` LOW..CRITICAL, this or worse; `status` open (open, or
        accepted with its review due: A16b), all, or one CVE status; `kev`; `since` YYYY-MM-DD, inclusive;
        `verdict`; `new`, new since your previous check (B05)."""
        k, watch, fresh = self.k, set(self._stack.watchlist), self._stack.new_since_check
        products = set(product.split(",")) if product else None

        def keep(c: dict) -> bool:  # the filters that need only the snapshot: applied before the assessment
            return (c["product"] in watch
                    and (kev is None or bool(k.cves.kev.get(c["id"])) == kev)
                    and (new is None or (c["id"] in fresh) == new)
                    # inclusive: the dashboard's "new in 30 days" tile links here with kpis.new_since
                    and (not since or c["published"] >= since)
                    and (not products or c["product"] in products)
                    and (not severity
                         or SEVERITY_ORDER.get(c["severity"] or "", 0) >= SEVERITY_ORDER[severity]))

        rows = sorted((self._row(self._assess(c)) for c in k.cves.all() if keep(c)), key=_sort_key)
        if status == "open":
            rows = [r for r in rows if r["open"]]
        elif status != "all":
            rows = [r for r in rows if r["status"] == status]
        if verdict:
            rows = [r for r in rows if r["verdict"] == verdict]
        return rows

    def most_urgent(self) -> dict | None:
        """The open CVE at the top of the priority order: the CVEs page's first row (with its due date)."""
        return next(iter(self.rows()), None)

    def page(self, cve_id: str) -> dict:
        """The page for one CVE (B35). KeyError when the CVE isn't in the snapshot. `row` is the CVEs page's row
        (status, decision, history, priority, due date), or None off the watchlist; the rest is there either way."""
        a = self.assess(cve_id)
        k, cve, v = self.k, a.cve, a.verdict
        kev = k.cves.kev.get(cve["id"])
        cat = k.category(cve["owasp"])
        kind = k.owasp["categories"][cve["owasp"]].get("kind", "") if cat else ""
        return {
            "id": cve["id"], "product": cve["product"], "product_name": k.products[cve["product"]],
            "severity": cve["severity"], "cvss": cve["cvss"], "published": cve["published"], "cwes": cve["cwes"],
            "description": cve["description"],  # in full: the list cuts it to 220 characters
            "owasp": {**cat, "list": OWASP_LISTS.get(kind)} if cat else None,
            "kev": {"date_added": kev["dateAdded"], "deadline": kev["dueDate"], "required_action": kev["requiredAction"],
                    "ransomware": kev["knownRansomwareCampaignUse"]} if kev else None,
            "epss": k.epss_of(cve["id"]), "possible_match": k.possible_match(cve["id"]),
            "affected": [{"package": e["package"], "ecosystem": e["ecosystem"], "advisory": e["advisory"],
                          "ranges": e["ranges"]}
                         for e in k.osv["cves"].get(cve["id"], []) if e["product"] == cve["product"]],
            "verdict": v.verdict, "verdict_reason": v.reason, "fixed_version": v.fixed_version, "who_acts": v.who_acts,
            "no_fix": a.no_fix, "usage": a.usage, "version": a.version, "internet_facing": a.internet_facing,
            "url": cve["url"], "osv_url": OSV_URL.format(cve["id"]),
            "watched": a.watched, "row": self._row(a) if a.watched else None,
        }

    def _row(self, a: Assessment) -> dict:
        k, cve, p = self.k, a.cve, a.priority
        kev = k.cves.kev.get(cve["id"])
        cat = k.category(cve["owasp"])
        return {
            "id": cve["id"], "product": cve["product"], "product_name": k.products[cve["product"]],
            "severity": cve["severity"], "cvss": cve["cvss"], "published": cve["published"],
            "owasp": cve["owasp"], "owasp_title": cat["title"] if cat else None,
            "new": cve["id"] in self._stack.new_since_check,  # B05: new since your previous check
            "kev": bool(kev), "kev_deadline": kev["dueDate"] if kev else None,  # CISA's, a fact; not your due date
            "status": a.status, "summary": cve["description"][:220], "url": cve["url"],
            "epss": k.epss_of(cve["id"]), "possible_match": k.possible_match(cve["id"]),
            "verdict": a.verdict.verdict, "verdict_reason": a.verdict.reason, "fixed_version": a.verdict.fixed_version,
            "who_acts": a.verdict.who_acts, "usage": a.usage, "version": a.version,
            "internet_facing": a.internet_facing, "no_fix": a.no_fix,
            "open": a.open, "review_due": a.review_due, "review_date": a.review_date, "decision": a.decision,
            "history": a.history, "open_days": a.open_days,
            # B33: a closed CVE has no priority or due date (None, never overdue); the KEV deadline above stays
            "priority": p and p.level, "priority_reasons": list(p.reasons) if p else [],
            "priority_rule": p and p.rule, "alert_priority": a.alert_priority, "due_date": p and p.due_date,
            "due_from": p and p.due_from, "overdue": bool(p and p.overdue),
        }

    def _assess(self, cve: dict) -> Assessment:
        k, stack, as_of = self.k, self._stack, self.as_of
        watched = stack.watches(cve["product"])
        status = stack.statuses.get(cve["id"], "open") if watched else None
        f = stack.fields(cve["product"])
        coverage = k.osv["products"].get(cve["product"], {}).get("coverage", "none")
        entries = [e for e in k.osv["cves"].get(cve["id"], []) if e["product"] == cve["product"]]
        v = verdict(coverage, entries, f.usage, f.version)
        nf = no_fix(coverage, entries)
        d = stack.decision(cve["id"])
        review_date = d["review_date"] if d and status == "accepted" else None
        p = None
        if watched:
            kev, epss = k.cves.kev.get(cve["id"]), k.epss_of(cve["id"])
            p = priority(CveFacts(severity=cve["severity"], kev=bool(kev),
                                  epss_percentile=epss["percentile"] if epss else None, verdict=v.verdict,
                                  internet_facing=f.internet_facing, status=status, published=cve["published"],
                                  kev_added=kev["dateAdded"] if kev else None,
                                  kev_deadline=kev["dueDate"] if kev else None, review_date=review_date, no_fix=nf),
                         self._policy, as_of, self._epss_threshold)
        return Assessment(
            cve=cve, watched=watched, status=status, verdict=v, no_fix=nf, usage=f.usage, version=f.version,
            internet_facing=f.internet_facing, decision=d, review_date=review_date,
            history=stack.history(cve["id"]),
            open=watched and is_open(status, review_date, as_of),
            review_due=watched and review_due(status, review_date, as_of),
            open_days=(dt.date.fromisoformat(as_of) - dt.date.fromisoformat(cve["published"])).days,
            priority=None if is_closed(status, review_date, as_of) else p,
            alert_priority=p and p.alert_priority)


def _sort_key(r: dict):
    # By priority (A16): most urgent first, then the earliest due date, then the highest CVSS, then newest. Closed
    # CVEs (no priority, B33) come after every open one
    return (*(sort_key(r["priority"], r["due_date"]) if r["priority"] else (len(LEVELS), "")), -(r["cvss"] or 0),
            -dt.date.fromisoformat(r["published"]).toordinal())

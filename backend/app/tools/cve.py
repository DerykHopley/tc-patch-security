"""lookup_cve (T2): one CVE from the snapshot, with OWASP, KEV and watchlist context."""
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.errors import ToolError
from app.proposals import ProposalSource
from app.rag.chunking import chunk_cve
from app.rag.pipeline import to_source
from app.status import JUSTIFICATIONS, STATUSES
from app.tools.registry import (Category, PriorityLevel, Severity, ToolResult, ToolSpec, Verdict, WatchStatus,
                                WhoActs, register)
from app.watched import WatchedCves


class CveArgs(BaseModel):
    cve_id: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"(?i)^CVE-\d{4}-\d{4,}$")]


class Kev(ToolResult):
    date_added: str
    deadline: str  # CISA's date, not the user's due date
    ransomware: str
    required_action: str


class Epss(ToolResult):
    score: float
    percentile: float
    date: str


class Decision(ToolResult):
    """The user's current decision record (app.status, A16b)."""
    status: Literal[STATUSES]  # type: ignore[valid-type]
    justification: Literal[JUSTIFICATIONS] | None  # type: ignore[valid-type]
    reason: str | None
    note: str | None
    review_date: str | None
    compensating_control: str | None
    decided_at: str | None  # None: recorded before decision records
    decided_by: str | None
    via: str | None
    proposal: str | None = None  # the proposal you approved, for a change Patch proposed (B21)
    sources: list[ProposalSource] | None = None  # what that proposal cited (B22)


class Priority(ToolResult):
    level: PriorityLevel
    reasons: list[str]
    due_date: str
    due_from: str
    overdue: bool
    alert_priority: int


class CveResult(ToolResult):
    """lookup_cve: one CVE with its OWASP, KEV, EPSS and watchlist context, the verdict and the priority."""
    n: int
    id: str
    product: str
    published: str
    severity: Severity | None
    cvss: float | None
    cwes: list[str]
    owasp: Category | None
    description: str
    url: str
    kev: Kev | None
    watch_status: WatchStatus
    epss: Epss | None
    product_match: Literal["confirmed", "conflicting", "unknown"] | None
    possible_match: bool
    verdict: Verdict
    verdict_reason: str
    fixed_version: str | None
    who_acts: WhoActs
    no_fix: bool
    decision: Decision | None
    review_due: bool
    open_days: int
    priority: Priority | None  # None off the watchlist


def run(args: CveArgs, deps, ctx) -> dict:
    k = deps.knowledge
    cve = k.cves.get(args.cve_id)
    if cve is None:
        raise ToolError(f"{args.cve_id} isn't in my snapshot ({len(k.cves.all())} CVEs for "
                        f"{len(k.products)} LLM products, as of {deps.as_of}).", "cve_not_in_snapshot")
    kev = k.cves.kev.get(cve["id"])
    a = WatchedCves.of(deps).assess(cve["id"])  # verdict (advice, never the status), decision, priority
    v, p = a.verdict, a.priority
    source = to_source(len(ctx.sources) + 1, chunk_cve(cve, k.products[cve["product"]])[0], None)
    ctx.sources.append(source)
    return {
        "n": source.n,
        "id": cve["id"], "product": k.products[cve["product"]], "published": cve["published"],
        "severity": cve["severity"], "cvss": cve["cvss"], "cwes": cve["cwes"],
        "owasp": k.category(cve["owasp"]), "description": cve["description"], "url": cve["url"],
        "kev": None if not kev else {"date_added": kev["dateAdded"], "deadline": kev["dueDate"],
                                     "ransomware": kev["knownRansomwareCampaignUse"],
                                     "required_action": kev["requiredAction"]},
        "watch_status": a.status if a.watched else "not_watched",
        "epss": k.epss_of(cve["id"]),  # EPSS by FIRST, as of the snapshot date
        "product_match": k.product_match(cve["id"]),  # None when the product came from the CPE
        "possible_match": k.possible_match(cve["id"]),
        "verdict": v.verdict, "verdict_reason": v.reason, "fixed_version": v.fixed_version, "who_acts": v.who_acts,
        "no_fix": a.no_fix,  # OSV lists no fixed version: "no fix yet", not overdue (A16b)
        "decision": a.decision, "review_due": a.review_due, "open_days": a.open_days,
        # The rules' priority and your due date (A16); None off the watchlist. The KEV deadline is under "kev".
        "priority": None if p is None else {
            "level": p.level, "reasons": list(p.reasons), "due_date": p.due_date,
            "due_from": p.due_from, "overdue": p.overdue, "alert_priority": p.alert_priority},
    }


register(ToolSpec(
    name="lookup_cve",
    description="Look up one CVE by id (e.g. CVE-2024-8309): severity, CWEs, OWASP category, CISA KEV status, "
                "EPSS score and percentile, whether the product is only a possible match (guessed from the "
                "description), whether it's open on the user's watchlist, and the version check's verdict "
                "(affected, not affected, unknown) with its reason, the fixed version and who acts. For a watched CVE, "
                "also the priority set by the rules (urgent, high, normal, low) with its reasons, the user's due "
                "date and whether it's overdue; the KEV deadline is CISA's date, separate from the due date. "
                "Explain the priority from its reasons; never change it. Also the user's decision (status, reason or "
                "justification, review date) and no_fix: true when no fixed version exists yet, so it isn't overdue; "
                "the user may accept the risk on the CVEs page. You may suggest that, never set it.",
    args_model=CveArgs,
    result=CveResult,
    run=run,
))

"""check_affected (A15): the verdict for one CVE, or a watched product's open CVEs by verdict.

Reads the verdict rules' output; changes nothing. Patch reports the verdict, it never marks a CVE not affected:
only the user does that (a click on the CVEs page, or asking for it in so many words).
"""
from typing import Annotated

from pydantic import BaseModel, StringConstraints, model_validator

from app.errors import ToolError
from app.rag.chunking import chunk_cve
from app.rag.pipeline import to_source
from app.tools.registry import Severity, ToolResult, ToolSpec, Verdict, WatchStatus, WhoActs, register
from app.verdict import USAGE_LABELS
from app.watched import WatchedCves

ORDER = ("affected", "unknown", "not_affected")  # what needs you first
LISTED = 10
NOTE = "The verdict is advice from the version check. The CVE's status stays the user's decision."


class AffectedArgs(BaseModel):
    cve_id: Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True,
                                             pattern=r"(?i)^CVE-\d{4}-\d{4,}$")] | None = None
    product: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None

    @model_validator(mode="after")
    def needs_one(self):
        if not (self.cve_id or self.product):
            raise ValueError("give a cve_id, a product, or both")
        return self


class AffectedOne(ToolResult):
    """One CVE's verdict."""
    n: int
    id: str
    product: str
    severity: Severity | None
    verdict: Verdict
    reason: str
    fixed_version: str | None
    who_acts: WhoActs
    usage: str  # in words: "self-hosted app"
    version: str | None
    watch_status: WatchStatus
    possible_match: bool
    note: str


class VerdictCounts(ToolResult):
    affected: int
    unknown: int
    not_affected: int


class AffectedRow(ToolResult):
    id: str
    severity: Severity | None
    verdict: Verdict
    reason: str
    fixed_version: str | None


class AffectedProduct(ToolResult):
    """A watched product's open CVEs by verdict."""
    product: str
    usage: str
    version: str | None
    open: int
    counts: VerdictCounts
    cves: list[AffectedRow]  # the first LISTED, what needs you first
    who_acts: WhoActs | None  # None when nothing is open
    note: str


def _one(cve: dict, deps, ctx, watched: WatchedCves) -> dict:
    k = deps.knowledge
    a = watched.assess(cve["id"])
    v = a.verdict
    source = to_source(len(ctx.sources) + 1, chunk_cve(cve, k.products[cve["product"]])[0], None)
    ctx.sources.append(source)
    return {
        "n": source.n, "id": cve["id"], "product": k.products[cve["product"]], "severity": cve["severity"],
        "verdict": v.verdict, "reason": v.reason, "fixed_version": v.fixed_version,
        "who_acts": v.who_acts, "usage": USAGE_LABELS[a.usage], "version": a.version,
        "watch_status": a.status if a.watched else "not_watched", "possible_match": k.possible_match(cve["id"]), "note": NOTE,
    }


def run(args: AffectedArgs, deps, ctx) -> dict:
    k, watched = deps.knowledge, WatchedCves.of(deps)
    pid = None
    if args.product:
        pid = k.resolve_product(args.product)
        if not pid:
            raise ToolError(f"{args.product!r} isn't a product I track. Choose from: "
                            f"{', '.join(k.products.values())}.", "bad_value")
    if args.cve_id:
        cve = k.cves.get(args.cve_id)
        if cve is None:
            raise ToolError(f"{args.cve_id} isn't in my snapshot.", "cve_not_in_snapshot")
        if pid and cve["product"] != pid:
            raise ToolError(f"{cve['id']} is a {k.products[cve['product']]} CVE, not {k.products[pid]}.",
                            "bad_value")
        return _one(cve, deps, ctx, watched)
    if pid not in watched.watchlist:
        raise ToolError(f"{k.products[pid]} isn't on the user's watchlist, so none of its CVEs are open.",
                        "not_watched")
    rows = watched.rows(product=pid)  # open only, in the CVEs page's order
    rows.sort(key=lambda r: ORDER.index(r["verdict"]))  # stable: keeps the table's order inside each verdict
    f = watched.fields_of(pid)
    return {
        "product": k.products[pid], "usage": USAGE_LABELS[f.usage], "version": f.version,
        "open": len(rows), "counts": {v: sum(r["verdict"] == v for r in rows) for v in ORDER},
        "cves": [{"id": r["id"], "severity": r["severity"], "verdict": r["verdict"], "reason": r["verdict_reason"],
                  "fixed_version": r["fixed_version"]} for r in rows[:LISTED]],
        "who_acts": rows[0]["who_acts"] if rows else None, "note": NOTE,
    }


register(ToolSpec(
    name="check_affected",
    description="Am I affected? The version check's verdict (affected, not affected, unknown) with its reason, "
                "the fixed version and who acts (you, upstream, vendor), from the user's usage and version of the "
                "product. Give cve_id for one CVE, or product for that watched product's open CVEs by verdict. "
                "Read-only: report the verdict, never mark a CVE not affected yourself.",
    args_model=AffectedArgs,
    result=AffectedOne | AffectedProduct,
    run=run,
))

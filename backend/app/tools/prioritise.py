"""prioritise (A18): "what should I fix first?" The priority rules' order (A16) for the watchlist and the page's view.

Rules decide, Patch explains. The order is the CVEs page's: most urgent level first, then the earliest due date
(app.priority.sort_key, via app.watched). Only open CVEs (app.status: open, or accepted with its review due).
The page's checked filters (app.page_context) narrow the view; its status filter doesn't apply, since only open CVEs
are ranked. A `product` argument other than the page's product is a question beyond the view: the page's other
filters are dropped and listed as not applied. A product that isn't watched (from either) is an error that says so.
On the dashboard the page's product filter may hold several products (A15b, `langflow,ollama`): unwatched ones are
left out and listed; a `product` argument among them narrows the view and keeps its other filters.
Read-only: it changes no status.
"""
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.cve_filters import CveView
from app.errors import ToolError
from app.rag.chunking import chunk_cve
from app.rag.pipeline import to_source
from app.tools.registry import PriorityLevel, Severity, ToolResult, ToolSpec, Verdict, register
from app.watched import WatchedCves

DEFAULT_LIMIT = 5  # the dashboard's Top 5
MAX_LIMIT = 10
NOTE = ("This order comes from fixed priority rules: most urgent level first, then the earliest due date. Explain it "
        "from each CVE's reasons; never change the order, drop or add CVEs, or set a status. The user decides.")


class PrioritiseArgs(BaseModel):
    product: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


class Filters(ToolResult):
    """The view's filters that were applied (CveView's names, without status). A filter that isn't set is absent."""
    product: str = None  # type: ignore[assignment]  # one id, or several: "langflow,ollama"
    severity: Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"] = None  # type: ignore[assignment]
    verdict: Verdict = None  # type: ignore[assignment]
    kev: bool = None  # type: ignore[assignment]
    since: str = None  # type: ignore[assignment]  # YYYY-MM-DD


class FixFirstCve(ToolResult):
    rank: int
    n: int
    id: str
    product: str
    severity: Severity | None
    kev: bool
    epss_percentile: float | None
    verdict: Verdict
    status: Literal["open", "accepted"]  # accepted: its review is due
    review_due: bool
    priority: PriorityLevel
    reasons: list[str]
    due_date: str
    due_from: str
    overdue: bool
    no_fix: bool
    open_days: int


class FixFirstResult(ToolResult):
    """prioritise: the top open CVEs in the rules' order, and the view they come from."""
    filters: Filters
    ignored: list[str]  # the page's filters not applied, each with why
    product: str | None  # the products' names, comma-separated
    total_open: int
    cves: list[FixFirstCve]  # in the rules' order
    note: str


def _label(key: str, value) -> str:
    return f"{key}={str(value).lower() if isinstance(value, bool) else value}"


def run(args: PrioritiseArgs, deps, ctx) -> dict:
    k, watched_cves = deps.knowledge, WatchedCves.of(deps)
    # The page's view (its checked context: the CVE view's names) without its status: only open CVEs are ranked
    filters = {key: v for key, v in CveView.parse(ctx.page, k.resolve_product).filters().items()
               if key != "status" and v is not None}
    ignored = [f"status={ctx.page['status']}: only open CVEs are ranked"] if ctx.page.get("status") not in (
        None, "open") else []
    names = lambda pids: ", ".join(k.products[p] for p in pids.split(","))  # noqa: E731  # one or several (A15b)
    if args.product:
        pid = k.resolve_product(args.product)
        if not pid:
            raise ToolError(f"{args.product!r} isn't a product I track. Choose from: "
                            f"{', '.join(k.products.values())}.", "bad_value")
        if "product" in filters and pid in filters["product"].split(","):  # within the page's view: narrow it
            filters["product"] = pid
        elif pid != filters.get("product"):  # beyond the page's view: its other filters were for what's on screen
            view = names(filters["product"]) if "product" in filters else "all products"
            ignored += [f"{_label(key, filters[key])}: the page's filter for {view}, not {k.products[pid]}"
                        for key in filters if key != "product"]
            filters = {"product": pid}
    if "product" in filters:  # from the argument or the page: only watched products have open CVEs
        pids = filters["product"].split(",")
        watched = [p for p in pids if p in watched_cves.watchlist]
        if not watched:
            raise ToolError(f"{names(filters['product'])} {'is' if len(pids) == 1 else 'are'} not on the user's "
                            "watchlist, so none of its CVEs are open.", "not_watched")
        ignored += [f"product={p}: {k.products[p]} isn't on the watchlist" for p in pids if p not in watched]
        filters["product"] = ",".join(watched)
    rows = watched_cves.rows(**filters)  # status open: the default
    cves = []
    for rank, r in enumerate(rows[:args.limit], 1):
        source = to_source(len(ctx.sources) + 1, chunk_cve(k.cves.get(r["id"]), r["product_name"])[0], None)
        ctx.sources.append(source)
        cves.append({
            "rank": rank, "n": source.n, "id": r["id"], "product": r["product_name"], "severity": r["severity"],
            "kev": r["kev"], "epss_percentile": r["epss"]["percentile"] if r["epss"] else None,
            "verdict": r["verdict"], "status": r["status"], "review_due": r["review_due"],
            "priority": r["priority"], "reasons": r["priority_reasons"], "due_date": r["due_date"],
            "due_from": r["due_from"], "overdue": r["overdue"], "no_fix": r["no_fix"], "open_days": r["open_days"],
        })
    return {
        "filters": filters, "ignored": ignored,
        "product": names(filters["product"]) if "product" in filters else None,
        "total_open": len(rows), "cves": cves, "note": NOTE,
    }


register(ToolSpec(
    name="prioritise",
    description="What should I fix first? The top open CVEs on the user's watchlist in the order the priority rules "
                "give (urgent, high, normal, low; then the earliest due date), each with its level, reasons, due "
                "date, overdue, no_fix (no fixed version yet: decide by the due date whether to accept, mitigate or "
                "replace) and review_due (an accepted risk due for review). Narrowed to the page the user is on "
                "(its filters) automatically. Give product to look at one watched product; limit (1-10, default 5). "
                "Explain the order from the reasons; never re-rank it.",
    args_model=PrioritiseArgs,
    result=FixFirstResult,
    run=run,
))

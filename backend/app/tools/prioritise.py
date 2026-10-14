"""prioritise (A18): "what should I fix first?" The priority rules' order (A16) for the watchlist and the page's view.

Rules decide, Patch explains. The order is the CVEs page's: most urgent level first, then the earliest due date
(app.priority.sort_key, via dashboard.list_cves). Only open CVEs (app.status: open, or accepted with its review due).
The page's checked filters (app.page_context) narrow the view; its status filter doesn't apply, since only open CVEs
are ranked. A `product` argument replaces the page's product. Read-only: it changes no status.
"""
from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

from app.dashboard import list_cves
from app.errors import ToolError
from app.rag.chunking import chunk_cve
from app.rag.pipeline import to_source
from app.tools.registry import ToolSpec, register

DEFAULT_LIMIT = 5  # the dashboard's Top 5
MAX_LIMIT = 10
NOTE = ("This order comes from fixed priority rules: most urgent level first, then the earliest due date. Explain it "
        "from each CVE's reasons; never change the order, drop or add CVEs, or set a status. The user decides.")
# The page's filter names (app.page_context) → list_cves' parameters
FILTERS = {"product": "product", "severity": "severity_min", "verdict": "verdict", "kev": "kev",
           "since": "published_since"}


class PrioritiseArgs(BaseModel):
    product: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    limit: int = Field(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT)


def run(args: PrioritiseArgs, deps, ctx) -> dict:
    k, data = deps.knowledge, deps.state.snapshot()
    filters = {key: ctx.page[key] for key in FILTERS if key in ctx.page}
    if args.product:
        pid = k.resolve_product(args.product)
        if not pid:
            raise ToolError(f"{args.product!r} isn't a product I track. Choose from: "
                            f"{', '.join(k.products.values())}.", "bad_value")
        if pid not in data["watchlist"]:
            raise ToolError(f"{k.products[pid]} isn't on the user's watchlist, so none of its CVEs are open.",
                            "not_watched")
        filters["product"] = pid
    page = list_cves(k, data, deps.settings.as_of, status="open", limit=args.limit,
                     **{FILTERS[key]: v for key, v in filters.items()})
    cves = []
    for rank, r in enumerate(page["rows"], 1):
        source = to_source(len(ctx.sources) + 1, chunk_cve(k.cves.get(r["id"]), r["product_name"])[0], None)
        ctx.sources.append(source)
        cves.append({
            "rank": rank, "n": source.n, "id": r["id"], "product": r["product_name"], "severity": r["severity"],
            "kev": r["kev"], "epss_percentile": r["epss"]["percentile"] if r["epss"] else None,
            "verdict": r["verdict"], "status": r["status"], "review_due": r["review_due"],
            "priority": r["priority"], "reasons": r["priority_reasons"], "due_date": r["due_date"],
            "due_from": r["due_from"], "overdue": r["overdue"], "no_fix": r["no_fix"], "open_days": r["open_days"],
        })
    ignored = [f"status={ctx.page['status']}: only open CVEs are ranked"] if ctx.page.get("status") not in (
        None, "open") else []
    return {
        "filters": filters, "ignored": ignored,
        "product": k.products[filters["product"]] if "product" in filters else None,
        "total_open": page["total"], "cves": cves, "note": NOTE,
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
    run=run,
))

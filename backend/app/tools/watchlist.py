"""update_watchlist (T4): watch or unwatch a product, set a CVE's status, or set a product's details. It only
proposes the change (B21): nothing changes until the user approves it in the chat's card (app.proposals)."""
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app import proposals
from app.proposals import Proposal
from app.schemas import CveId
from app.tools.registry import ToolResult, ToolSpec, register
from app.status import JUSTIFICATIONS
from app.verdict import USAGES


class WatchArgs(BaseModel):
    action: Literal["watch", "unwatch", "set_status", "set_details"]
    product: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    cve_id: CveId | None = None
    # Never "accepted": accepting a risk is the user's alone (A16b). Patch may only suggest it.
    status: Literal["open", "fixed", "not_affected"] | None = None
    justification: Literal[JUSTIFICATIONS] | None = None  # type: ignore[valid-type]  # needed for not_affected
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    # set_details (A15): how the user runs the product. Only what's given changes; version "" clears it.
    usage: Literal[USAGES] | None = None  # type: ignore[valid-type]
    version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    internet_facing: bool | None = None
    why: Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)] | None = None  # on the card (B21)


class WatchlistResult(ToolResult):
    """update_watchlist when there's nothing to change (B21): why not, and the watchlist as it is."""
    message: str
    watchlist: list[str]  # the products' names


FIELDS = {"status", "justification", "note", "usage", "version", "internet_facing"}


def run(args: WatchArgs, deps, ctx) -> dict:
    """What the action needs and takes, and every error, are the proposal's own (app.proposals.propose, B27)."""
    p = proposals.propose(args.action, deps, cve_id=args.cve_id, product=args.product,
                          fields=args.model_dump(include=FIELDS), why=args.why)
    if isinstance(p, proposals.NoChange):
        k = deps.knowledge
        return {"message": p.message, "watchlist": [k.products[x] for x in deps.state.read().watchlist]}
    return p


register(ToolSpec(
    name="update_watchlist",
    description="Propose a change to the user's watchlist: action 'watch' or 'unwatch' with a product (e.g. "
                "Ollama), 'set_status' with cve_id and status (open, fixed, not_affected) only when the user asks "
                "for it (not_affected needs a justification: " + ", ".join(JUSTIFICATIONS) + "; an optional note), "
                "or 'set_details' with a product and any of usage (self_hosted, library, transitive, hosted), "
                "version, internet_facing. Optional why: your reason, in one sentence. It changes nothing: the user "
                "sees a card with the before and after, and approves, edits or cancels it.",
    args_model=WatchArgs,
    result=Proposal | WatchlistResult,
    # Accepting a risk isn't offered here: the user does it on the CVEs page, or by editing a proposal.
    run=run,
))

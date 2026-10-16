"""Buttons on tool cards (B24, #63): the next step is a click, sent as a structured action, never free text.

| Action  | What the button does                                   | Changes state?                               |
|---------|--------------------------------------------------------|----------------------------------------------|
| propose | Watch this product, Set my version…, Mark not affected…, Mark accepted… | never: it makes a B21 proposal; Approve changes it |
| refine  | Show only CVEs, Only critical, on the search card     | no: search runs again with that filter        |

A refine runs the card's tool again, not the model: the same rules give the same narrower list, with no second model
call, and nothing in the button's request can steer Patch. "Open in CVEs page" and "Ask about this" need no route:
one is a link, the other a chat message with the CVE in the page context (A18).
"""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app import proposals
from app.errors import InputError
from app.llm.base import ToolCall
from app.schemas import ToolCallRecord
from app.tools.registry import Context, run_tool

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]
CveId = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"(?i)^CVE-\d{4}-\d{4,}$")]


class Propose(BaseModel):
    """A change button: what it proposes, with the fields the user gave in its form. The checks are the proposal's
    own (the CVE decision dialog's and the Settings watchlist's)."""
    model_config = ConfigDict(extra="forbid")
    action: Literal["propose"]
    change: Literal["watch", "set_details", "set_status"]
    product: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    cve_id: CveId | None = None
    # set_status: the user's own button, so accepting a risk is allowed, as in the proposal's Edit (B21)
    status: Literal["not_affected", "accepted"] | None = None
    justification: Short | None = None
    reason: Short | None = None
    review_date: str | None = None
    compensating_control: Short | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None


# The refine buttons and the search filters they force (app.rag: Filters' names), with the chip's words.
REFINES = {"only_cves": ({"doc_type": "cve"}, "Only CVEs"),
           "only_critical": ({"severity_min": "CRITICAL"}, "Only critical")}


class Refine(BaseModel):
    """A refine button on the search card: run search_security again on the card's query with fixed filters."""
    model_config = ConfigDict(extra="forbid")
    action: Literal["refine"]
    tool: Literal["search_security"]
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]
    filters: list[Literal["only_cves", "only_critical"]] = Field(min_length=1, max_length=2)
    page: dict | None = None  # the answer's page context, checked again as for /chat


CardAction = Annotated[Propose | Refine, Field(discriminator="action")]


class Proposed(BaseModel):
    """A change button's reply: the proposal (null when it's already so), and what Patch says."""
    proposal: proposals.Proposal | None
    message: str


class Refined(BaseModel):
    """A refine button's reply: the chips (what was applied) and the new tool record for the new card."""
    applied: list[str]
    call: ToolCallRecord


def propose(body: Propose, deps) -> Proposed:
    if body.change in ("watch", "set_details") and not body.product:
        raise InputError(f"'{body.change}' needs a product.")
    if body.change == "set_status" and not (body.cve_id and body.status):
        raise InputError("'set_status' needs cve_id and status.")
    if body.change == "set_status":
        fields = body.model_dump(include={"status", "justification", "reason", "review_date", "compensating_control",
                                         "note"})
    elif body.change == "set_details":
        fields = {"version": body.version or ""}  # empty: "I don't know it", as in Settings
    else:
        fields = {}
    try:
        p = proposals.propose(body.change, deps, product=body.product, cve_id=body.cve_id, **fields)
    except proposals.Nothing as e:
        return Proposed(proposal=None, message=str(e))
    except KeyError:
        raise InputError(f"{body.cve_id} isn't in the snapshot.", "not_found") from None
    return Proposed(proposal=p, message=p["message"])


def refine(body: Refine, deps, page: dict) -> Refined:
    force: dict = {}
    for f in dict.fromkeys(body.filters):  # in order, once each
        force |= REFINES[f][0]
    call = ToolCall(id="refine", name=body.tool, args={"query": body.query})
    record = run_tool(call, deps, Context(page=page, user_id=deps.user_id, force_filters=force))
    return Refined(applied=[REFINES[f][1] for f in dict.fromkeys(body.filters)], call=record)

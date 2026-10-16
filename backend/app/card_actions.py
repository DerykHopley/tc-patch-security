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
from app.llm.base import ToolCall
from app.schemas import CveId, ToolCallRecord
from app.tools.registry import Context, run_tool

Short = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


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
    """What the change needs and takes, and every error (an InputError: a 400), are the proposal's own (B27)."""
    fields = body.model_dump(exclude={"action", "change", "product", "cve_id"})
    if body.change == "set_details":
        fields["version"] = body.version or ""  # empty: "I don't know it", as in Settings
    p = proposals.propose(body.change, deps, cve_id=body.cve_id, product=body.product, fields=fields)
    if isinstance(p, proposals.NoChange):
        return Proposed(proposal=None, message=p.message)
    return Proposed(proposal=p, message=p["message"])


def refine(body: Refine, deps, page: dict) -> Refined:
    force: dict = {}
    for f in dict.fromkeys(body.filters):  # in order, once each
        force |= REFINES[f][0]
    call = ToolCall(id="refine", name=body.tool, args={"query": body.query})
    record = run_tool(call, deps, Context(page=page, user_id=deps.user_id, force_filters=force))
    return Refined(applied=[REFINES[f][1] for f in dict.fromkeys(body.filters)], call=record)

"""Changes Patch proposes, you preview and approve (B21). A security assistant shouldn't change your records on a
model's say-so: the chat's update_watchlist only proposes, and nothing changes until you approve the card.

A proposal's life:

| From      | Action  | To        | Notes                                                                        |
|-----------|---------|-----------|------------------------------------------------------------------------------|
| (none)    | propose | proposed  | update_watchlist; checked like the forms; nothing changes                     |
| proposed  | edit    | proposed  | the same checks as the CVE decision dialog and the Settings watchlist         |
| proposed  | approve | approved  | through State's own methods, as the pages; who and when are recorded          |
| approved  | approve | approved  | the first result again, nothing more changes (a retry, a double click)        |
| proposed  | cancel  | cancelled | cancelling again is a no-op                                                   |
| proposed  | (1 h)   | expired   | can't be approved; propose again                                              |
| proposed  | approve | (refused) | stale: what it was based on changed since (the CVE's status, the watchlist)   |

Proposals live in the state file, next to what they change, so per-user state (B09) keys them per user for free.
Approving holds one lock from the check to the record, so two approves at once apply once. A crash between the
change and its record leaves the proposal stale, never applied twice.
"""
import datetime as dt
import uuid
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints

from app.errors import AppError, InputError
from app.status import DECIDED_BY, JUSTIFICATIONS, decision
from app.verdict import USAGE_LABELS, USAGES

TTL = dt.timedelta(hours=1)
Action = Literal["watch", "unwatch", "set_status", "set_details"]
ProposalState = Literal["proposed", "approved", "cancelled", "expired"]

STATUS_WORD = {"open": "Open", "fixed": "Fixed", "not_affected": "Not affected", "accepted": "Accepted"}
TITLE = {"open": "Reopen {cve}", "fixed": "Mark {cve} fixed", "not_affected": "Mark {cve} not affected",
         "accepted": "Accept the risk of {cve}"}
JUSTIFICATION_WORDS = {j: j.replace("_", " ") for j in JUSTIFICATIONS}
STATUS_FIELDS = ("status", "justification", "note", "reason", "review_date", "compensating_control")
DETAIL_FIELDS = ("usage", "version", "internet_facing")
Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]  # as the CVE decision dialog's


class ProposalError(AppError):
    """A proposal that can't be found (404) or can't do what was asked any more (409)."""

    def __init__(self, message: str, code: str, status: int = 409):
        super().__init__(message, code)
        self.status = status


class _Shape(BaseModel):
    # The tools' ToolResult config. Not imported from app.tools.registry: that module imports the tools, and the
    # update_watchlist tool imports this one.
    model_config = ConfigDict(extra="forbid")


class ProposalFields(_Shape):
    """What a proposal would set. Only the fields its action takes are filled; the others are null."""
    status: Literal["open", "fixed", "not_affected", "accepted"] | None
    justification: Literal[JUSTIFICATIONS] | None  # type: ignore[valid-type]
    note: str | None
    reason: str | None
    review_date: str | None
    compensating_control: str | None
    usage: Literal[USAGES] | None  # type: ignore[valid-type]
    version: str | None
    internet_facing: bool | None


class Proposal(_Shape):
    """update_watchlist (B21): a proposed change, not made yet. What, why, before and after; you approve, edit or
    cancel it in the chat's card."""
    proposal_id: str
    action: Action
    title: str  # what, in words: "Mark CVE-2024-8309 fixed"
    why: str | None  # the model's reason, if it gave one
    cve_id: str | None  # set_status
    product: str | None  # product id: watch, unwatch, set_details; the CVE's product for set_status
    product_name: str | None
    before: str
    after: str
    fields: ProposalFields
    state: ProposalState
    message: str  # what Patch says: nothing changed yet; or, once approved, what changed
    as_of: str  # the as-of date the decision is checked against (a review date must be after it)
    created_at: str
    expires_at: str
    approved_at: str | None
    approved_by: str | None


class ProposalEdit(BaseModel):
    """Your corrections (PATCH /proposals/{id}). A status change: the status and its record's fields, as the CVE
    decision dialog sends them. Product details: any of usage, version, internet_facing."""
    model_config = ConfigDict(extra="forbid")
    status: str | None = None
    justification: Text | None = None
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    reason: Text | None = None
    review_date: str | None = None
    compensating_control: Text | None = None
    usage: str | None = None
    version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    internet_facing: StrictBool | None = None


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).isoformat(timespec="seconds")


def _details_words(f: dict) -> str:
    return ", ".join([USAGE_LABELS[f["usage"]], f"version {f['version']}" if f["version"] else "no version given",
                      "internet-facing" if f["internet_facing"] else "not internet-facing"])


def _status_words(fields: dict) -> str:
    out = STATUS_WORD[fields["status"]]
    extra = [JUSTIFICATION_WORDS.get(fields.get("justification") or "", None), fields.get("reason"),
             f"review {fields['review_date']}" if fields.get("review_date") else None]
    extra = [x for x in extra if x]
    return f"{out} ({'; '.join(extra)})" if extra else out


class Nothing(Exception):
    """The change is already so: nothing to propose. Carries the message."""


def _based_on(rec: dict, deps) -> dict:
    """What the proposal depends on, read now: approving checks it hasn't changed."""
    stack = deps.state.read()
    if rec["action"] == "set_status":
        return {"status": stack.statuses.get(rec["cve_id"], "open"), "decisions": len(stack.history(rec["cve_id"]))}
    if rec["action"] == "set_details":
        return {"fields": stack.fields(rec["product"]).as_dict()}
    return {"watched": stack.watches(rec["product"])}


def _preview(rec: dict, deps) -> tuple[str, str, dict]:
    """Before, after and the checked fields for a proposal record. InputError if a field isn't allowed."""
    k, stack = deps.knowledge, deps.state.read()
    f = rec["fields"]
    if rec["action"] == "set_status":
        given = {x: f.get(x) for x in STATUS_FIELDS if x != "status"}
        checked = decision(f.get("status") or "", given, deps.as_of)  # the CVE decision dialog's rules
        before = STATUS_WORD[stack.statuses.get(rec["cve_id"], "open")]
        return before, _status_words(checked), {x: checked.get(x) for x in STATUS_FIELDS}
    if rec["action"] == "set_details":
        saved = stack.fields(rec["product"]).as_dict()
        new = deps.state.check_fields(rec["product"], saved | {x: f[x] for x in DETAIL_FIELDS if f.get(x) is not None})
        return _details_words(saved), _details_words(new), new
    watched = stack.watches(rec["product"])
    return ("Watched" if watched else "Not watched"), ("Not watched" if watched else "Watched"), {}


def _title(rec: dict, deps) -> str:
    name = deps.knowledge.products.get(rec["product"], rec["product"])
    if rec["action"] == "set_status":
        return TITLE[rec["fields"]["status"]].format(cve=rec["cve_id"])
    if rec["action"] == "set_details":
        return f"Change how you run {name}"
    return f"Add {name} to your watchlist" if rec["action"] == "watch" else f"Remove {name} from your watchlist"


PENDING = "Nothing has changed yet: approve it in the card, edit it, or cancel it."


def propose(action: str, deps, *, product: str | None = None, cve_id: str | None = None, why: str | None = None,
            **fields) -> dict:
    """A new proposal, saved, as the Proposal view. Nothing raised as Nothing; a bad value as InputError; an
    unknown CVE as KeyError."""
    k, stack = deps.knowledge, deps.state.read()
    if action == "set_status":
        cve = k.cves.get(cve_id)
        if cve is None:
            raise KeyError(cve_id)
        cve_id, product = cve["id"], cve["product"]
        if stack.statuses.get(cve_id, "open") == fields.get("status"):
            raise Nothing(f"{cve_id} is already {STATUS_WORD[fields['status']].lower()}: nothing to change.")
    else:
        pid = k.resolve_product(product)
        if not pid:
            raise InputError(f"{product!r} isn't a product I track. Choose from: {', '.join(k.products.values())}.")
        product = pid
        if action == "watch" and stack.watches(pid):
            raise Nothing(f"{k.products[pid]} is already on your watchlist: nothing to change.")
        if action == "unwatch" and not stack.watches(pid):
            raise Nothing(f"{k.products[pid]} isn't on your watchlist: nothing to change.")
    now = deps.clock()
    rec = {"id": uuid.uuid4().hex, "action": action, "cve_id": cve_id if action == "set_status" else None,
           "product": product, "why": why, "fields": dict(fields), "state": "proposed", "created_at": _iso(now),
           "expires_at": _iso(now + TTL), "approved_at": None, "approved_by": None, "message": PENDING}
    rec["before"], rec["after"], rec["fields"] = _preview(rec, deps)
    if action == "set_details" and rec["before"] == rec["after"]:
        raise Nothing(f"{k.products[product]} is already {rec['after']}: nothing to change.")
    rec["based_on"] = _based_on(rec, deps)
    deps.state.save_proposal(rec)
    return view(rec, deps)


STALE = {"set_status": "This CVE's status changed since Patch proposed this. Propose it again.",
         "set_details": "This product's details changed since Patch proposed this. Propose it again.",
         "watch": "Your watchlist changed since Patch proposed this. Propose it again.",
         "unwatch": "Your watchlist changed since Patch proposed this. Propose it again."}


def _record(deps, pid: str) -> dict:
    rec = deps.state.proposal(pid)
    if rec is None:
        raise ProposalError(f"There's no proposal {pid!r}. It may be from before a reset.", "not_found", 404)
    return rec


def _check_open(rec: dict, deps) -> None:
    """A proposal you can still edit or approve: not cancelled, not approved, not expired."""
    state = view(rec, deps)["state"]
    if state == "cancelled":
        raise ProposalError("This proposal was cancelled. Ask Patch to propose it again.", "cancelled")
    if state == "approved":
        raise ProposalError("This proposal was already approved.", "approved")
    if state == "expired":
        raise ProposalError("This proposal expired: proposals last an hour. Ask Patch to propose it again.",
                            "expired")


def get(deps, pid: str) -> dict:
    return view(_record(deps, pid), deps)


def _apply(rec: dict, deps) -> str:
    """Make the change through State's own methods, the ones the pages use. Returns what changed, in words."""
    k, state, f = deps.knowledge, deps.state, rec["fields"]
    name = k.products.get(rec["product"], rec["product"])
    if rec["action"] == "set_status":
        given = {x: f[x] for x in STATUS_FIELDS if x != "status" and f.get(x) is not None}
        cve, _ = state.set_status(rec["cve_id"], f["status"], deps.as_of, "chat", proposal=rec["id"], **given)
        msg = f"Marked {cve['id']} as {STATUS_WORD[f['status']].lower()}."
        if not state.read().watches(cve["product"]):
            msg += f" {name} isn't on your watchlist, so the dashboard won't show it."
        return msg
    if rec["action"] == "set_details":
        new = state.set_fields(rec["product"], usage=f["usage"], version=f["version"] or "",
                               internet_facing=f["internet_facing"])
        return f"{name}: {_details_words(new)}."
    if rec["action"] == "watch":
        state.watch(rec["product"])
        return f"Added {name} to your watchlist."
    state.unwatch(rec["product"])
    return f"Removed {name} from your watchlist."


def approve(deps, pid: str) -> dict:
    """Apply a proposal once. Approving it again returns the first result and changes nothing more."""
    with deps.state.approvals:
        rec = _record(deps, pid)
        if rec["state"] == "approved":
            return view(rec, deps)
        _check_open(rec, deps)
        if _based_on(rec, deps) != rec["based_on"]:
            raise ProposalError(STALE[rec["action"]], "stale")
        rec["message"] = _apply(rec, deps)
        rec |= {"state": "approved", "approved_at": _iso(deps.clock()), "approved_by": DECIDED_BY}
        deps.state.save_proposal(rec)
        return view(rec, deps)


def cancel(deps, pid: str) -> dict:
    """Cancel a proposal that wasn't approved. Cancelling it again is a no-op."""
    with deps.state.approvals:
        rec = _record(deps, pid)
        if rec["state"] == "approved":
            raise ProposalError("This proposal was already approved, so it can't be cancelled.", "approved")
        if rec["state"] != "cancelled":
            rec |= {"state": "cancelled", "message": "Cancelled: nothing was changed."}
            deps.state.save_proposal(rec)
        return view(rec, deps)


def edit(deps, pid: str, changes: ProposalEdit) -> dict:
    """Your corrections, checked as the CVE decision dialog (a status) or the Settings watchlist (a product's
    details) check them. A status change takes the whole form: fields left out are cleared."""
    with deps.state.approvals:
        rec = _record(deps, pid)
        _check_open(rec, deps)
        given = changes.model_dump(exclude_unset=True)
        if rec["action"] in ("watch", "unwatch"):
            raise InputError("A watchlist proposal has nothing to edit: approve it or cancel it.")
        allowed = STATUS_FIELDS if rec["action"] == "set_status" else DETAIL_FIELDS
        if wrong := [x for x in given if x not in allowed]:
            what = "A status change" if rec["action"] == "set_status" else "A product's details"
            raise InputError(f"{what} doesn't take {', '.join(wrong)}.")
        if rec["action"] == "set_status":
            _, rec["after"], rec["fields"] = _preview(rec | {"fields": given}, deps)
        else:
            new = deps.state.check_fields(rec["product"], {**rec["fields"], **given})  # version "" clears it
            rec["after"], rec["fields"] = _details_words(new), new
        deps.state.save_proposal(rec)
        return view(rec, deps)


def view(rec: dict, deps) -> dict:
    """The Proposal as the card and the tool show it. A proposed one past its time is expired."""
    state = rec["state"]
    if state == "proposed" and deps.clock() >= dt.datetime.fromisoformat(rec["expires_at"]):
        state = "expired"
    fields = {x: rec["fields"].get(x) for x in (*STATUS_FIELDS, *DETAIL_FIELDS)}
    return Proposal(
        proposal_id=rec["id"], action=rec["action"], title=_title(rec, deps), why=rec["why"], cve_id=rec["cve_id"],
        product=rec["product"], product_name=deps.knowledge.products.get(rec["product"]), before=rec["before"],
        after=rec["after"], fields=ProposalFields(**fields), state=state, message=rec["message"],
        as_of=deps.as_of, created_at=rec["created_at"], expires_at=rec["expires_at"],
        approved_at=rec["approved_at"], approved_by=rec["approved_by"]).model_dump()

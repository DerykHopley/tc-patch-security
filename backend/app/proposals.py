"""Changes Patch proposes, you preview and approve (B21). A security assistant shouldn't change your records on a
model's say-so: the chat's update_watchlist only proposes, and nothing changes until you approve the card.

A proposal's life:

| From      | Action  | To        | Notes                                                                        |
|-----------|---------|-----------|------------------------------------------------------------------------------|
| (none)    | propose | proposed  | update_watchlist, propose_decision (B22), a card button (B24); checked here    |
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
from collections.abc import Callable
from dataclasses import dataclass
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints

from app.errors import AppError, InputError
from app.status import JUSTIFICATIONS, decision
from app.times import iso_utc
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


class ProposalSource(_Shape):
    """A source a proposed decision cites (B22): what it rests on, so you can check it before you approve. A web
    source is always marked "web result, unverified"."""
    n: int  # its number in the answer
    kind: Literal["knowledge", "web"]
    label: Literal["knowledge base", "web result, unverified"]
    title: str
    url: str
    site: str | None  # a web source's site


class Proposal(_Shape):
    """update_watchlist (B21) or propose_decision (B22): a proposed change, not made yet. What, why, before and
    after, and for a proposed decision the sources it rests on; you approve, edit or cancel it in the chat's card."""
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
    sources: list[ProposalSource]  # what a proposed decision cites (B22); empty for the other proposals
    editable: list[Literal[STATUS_FIELDS + DETAIL_FIELDS]]  # type: ignore[valid-type]  # what the card's Edit shows
    link_to: Literal["cve", "watchlist"]  # where the card's Done links: a kind; the frontend knows the page (B27)


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



def _details_words(f: dict) -> str:
    return ", ".join([USAGE_LABELS[f["usage"]], f"version {f['version']}" if f["version"] else "no version given",
                      "internet-facing" if f["internet_facing"] else "not internet-facing"])


def _status_words(fields: dict) -> str:
    out = STATUS_WORD[fields["status"]]
    extra = [JUSTIFICATION_WORDS.get(fields.get("justification") or "", None), fields.get("reason"),
             f"review {fields['review_date']}" if fields.get("review_date") else None]
    extra = [x for x in extra if x]
    return f"{out} ({'; '.join(extra)})" if extra else out


@dataclass(frozen=True)
class NoChange:
    """propose's answer when the change is already so: nothing to propose, and why. An answer, not an error (B27)."""
    message: str


# --- Each action's handlers, in one place (the Change map below): what it rests on, its before and after, its title,
# how approving applies it, and what an edit may change.

def _status_based_on(rec: dict, stack) -> dict:
    return {"status": stack.statuses.get(rec["cve_id"], "open"), "decisions": len(stack.history(rec["cve_id"]))}


def _details_based_on(rec: dict, stack) -> dict:
    return {"fields": stack.fields(rec["product"]).as_dict()}


def _watch_based_on(rec: dict, stack) -> dict:
    return {"watched": stack.watches(rec["product"])}


def _status_preview(rec: dict, deps, stack) -> tuple[str, str, dict]:
    f = rec["fields"]
    given = {x: f.get(x) for x in STATUS_FIELDS if x != "status"}
    checked = decision(f.get("status") or "", given, deps.as_of)  # the CVE decision dialog's rules
    before = STATUS_WORD[stack.statuses.get(rec["cve_id"], "open")]
    return before, _status_words(checked), {x: checked.get(x) for x in STATUS_FIELDS}


def _details_preview(rec: dict, deps, stack) -> tuple[str, str, dict]:
    f = rec["fields"]
    saved = stack.fields(rec["product"]).as_dict()
    new = deps.state.check_fields(rec["product"], saved | {x: f[x] for x in DETAIL_FIELDS if f.get(x) is not None})
    return _details_words(saved), _details_words(new), new


def _watch_preview(rec: dict, deps, stack) -> tuple[str, str, dict]:
    watched = stack.watches(rec["product"])
    return ("Watched" if watched else "Not watched"), ("Not watched" if watched else "Watched"), {}


def _status_apply(rec: dict, deps, name: str) -> str:
    state, f = deps.state, rec["fields"]
    given = {x: f[x] for x in STATUS_FIELDS if x != "status" and f.get(x) is not None}
    cve, _ = state.set_status(rec["cve_id"], f["status"], deps.as_of, "chat", proposal=rec["id"],
                              sources=rec.get("sources") or None, by=deps.decided_by, **given)
    msg = f"Marked {cve['id']} as {STATUS_WORD[f['status']].lower()}."
    if not state.read().watches(cve["product"]):
        msg += f" {name} isn't on your watchlist, so the dashboard won't show it."
    return msg


def _details_apply(rec: dict, deps, name: str) -> str:
    f = rec["fields"]
    new = deps.state.set_fields(rec["product"], usage=f["usage"], version=f["version"] or "",
                                internet_facing=f["internet_facing"])
    return f"{name}: {_details_words(new)}."


def _watch_apply(rec: dict, deps, name: str) -> str:
    deps.state.watch(rec["product"])
    return f"Added {name} to your watchlist."


def _unwatch_apply(rec: dict, deps, name: str) -> str:
    deps.state.unwatch(rec["product"])
    return f"Removed {name} from your watchlist."


def _status_edit(rec: dict, given: dict, deps) -> None:
    _, rec["after"], rec["fields"] = _status_preview(rec | {"fields": given}, deps, deps.state.read())


def _details_edit(rec: dict, given: dict, deps) -> None:
    new = deps.state.check_fields(rec["product"], {**rec["fields"], **given})  # version "" clears it
    rec["after"], rec["fields"] = _details_words(new), new


@dataclass(frozen=True)
class Change:
    """One action a proposal can take, with its handlers. `needs`: what propose must be given (cve_id, product or a
    field). `editable`: the fields it takes, when proposed and when edited; propose refuses any other. `edit` applies
    an edit (None: nothing to edit, approve or cancel it). `link_to`: where the card's Done links."""
    based_on: Callable[[dict, Any], dict]  # (rec, stack): what approving checks hasn't changed
    preview: Callable[[dict, Any, Any], tuple[str, str, dict]]  # (rec, deps, stack): before, after, checked fields
    title: Callable[[dict, str], str]  # (rec, product name)
    apply: Callable[[dict, Any, str], str]  # (rec, deps, product name): make the change, say what changed
    stale: str  # approving refused: what it was based on changed
    needs: tuple[str, ...]
    link_to: Literal["cve", "watchlist"]
    editable: tuple[str, ...] = ()
    edit: Callable[[dict, dict, Any], None] | None = None  # (rec, given, deps): the new after and fields
    what: str = ""  # an edit's subject, for "… doesn't take …"


_WATCHLIST_CHANGED = "Your watchlist changed since Patch proposed this. Propose it again."
CHANGES: dict[str, Change] = {
    "set_status": Change(_status_based_on, _status_preview,
                         lambda rec, name: TITLE[rec["fields"]["status"]].format(cve=rec["cve_id"]), _status_apply,
                         "This CVE's status changed since Patch proposed this. Propose it again.",
                         ("cve_id", "status"), "cve", STATUS_FIELDS, _status_edit, "A status change"),
    "set_details": Change(_details_based_on, _details_preview, lambda rec, name: f"Change how you run {name}",
                          _details_apply, "This product's details changed since Patch proposed this. Propose it again.",
                          ("product",), "watchlist", DETAIL_FIELDS, _details_edit, "A product's details"),
    "watch": Change(_watch_based_on, _watch_preview, lambda rec, name: f"Add {name} to your watchlist", _watch_apply,
                    _WATCHLIST_CHANGED, ("product",), "watchlist"),
    "unwatch": Change(_watch_based_on, _watch_preview, lambda rec, name: f"Remove {name} from your watchlist",
                      _unwatch_apply, _WATCHLIST_CHANGED, ("product",), "watchlist"),
}


def _name(rec: dict, deps) -> str:
    return deps.knowledge.products.get(rec["product"], rec["product"])


PENDING = "Nothing has changed yet: approve it in the card, edit it, or cancel it."


def propose(action: str, deps, *, cve_id: str | None = None, product: str | None = None, fields: dict | None = None,
            why: str | None = None, sources: list[dict] | None = None) -> dict | NoChange:
    """The one way in for a proposal (B27): a new one, saved, as the Proposal view; or NoChange when it's already
    so. `fields`: what it would set; None values are dropped, and a field the action doesn't take is refused.
    Raises InputError: `cve_not_in_snapshot` for an unknown CVE, `bad_value` for anything else wrong (something the
    action needs, a field it doesn't take, a value the forms' checks refuse). `sources`: what a proposed decision
    cites (B22), as ProposalSource dicts; approving keeps them in the decision record."""
    change = CHANGES.get(action)
    if change is None:
        raise InputError(f"There's no change {action!r} to propose.", "bad_value")
    fields = {x: v for x, v in (fields or {}).items() if v is not None}
    given = {"cve_id": cve_id, "product": product, **fields}
    if missing := [x for x in change.needs if not given.get(x)]:
        raise InputError(f"'{action}' needs {' and '.join(missing)}.", "bad_value")
    if wrong := [x for x in fields if x not in change.editable]:
        raise InputError(f"'{action}' doesn't take {', '.join(wrong)}.", "bad_value")
    k, stack = deps.knowledge, deps.state.read()
    if action == "set_status":
        cve = k.cves.get(cve_id)
        if cve is None:
            raise InputError(f"{cve_id} isn't in my snapshot.", "cve_not_in_snapshot")
        cve_id, product = cve["id"], cve["product"]
        if stack.statuses.get(cve_id, "open") == fields["status"]:
            return NoChange(f"{cve_id} is already {STATUS_WORD.get(fields['status'], '?').lower()}: "
                            "nothing to change.")
    else:
        pid = k.resolve_product(product)
        if not pid:
            raise InputError(f"{product!r} isn't a product I track. Choose from: {', '.join(k.products.values())}.",
                             "bad_value")
        product, cve_id = pid, None
        if action == "watch" and stack.watches(pid):
            return NoChange(f"{k.products[pid]} is already on your watchlist: nothing to change.")
        if action == "unwatch" and not stack.watches(pid):
            return NoChange(f"{k.products[pid]} isn't on your watchlist: nothing to change.")
    now = deps.clock()
    rec = {"id": uuid.uuid4().hex, "action": action, "cve_id": cve_id, "product": product, "why": why,
           "fields": fields, "state": "proposed", "created_at": iso_utc(now), "expires_at": iso_utc(now + TTL),
           "approved_at": None, "approved_by": None, "message": PENDING, "sources": list(sources or [])}
    try:
        rec["before"], rec["after"], rec["fields"] = change.preview(rec, deps, stack)
    except InputError as e:  # the CVE decision dialog's or the Settings watchlist's own checks
        raise InputError(e.message, "bad_value") from None
    if action == "set_details" and rec["before"] == rec["after"]:
        return NoChange(f"{k.products[product]} is already {rec['after']}: nothing to change.")
    rec["based_on"] = change.based_on(rec, deps.state.read())
    deps.state.save_proposal(rec)
    return view(rec, deps)


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


def approve(deps, pid: str) -> dict:
    """Apply a proposal once, through State's own methods (the ones the pages use). Approving it again returns the
    first result and changes nothing more."""
    with deps.state.approvals:
        rec = _record(deps, pid)
        if rec["state"] == "approved":
            return view(rec, deps)
        _check_open(rec, deps)
        change = CHANGES[rec["action"]]
        if change.based_on(rec, deps.state.read()) != rec["based_on"]:
            raise ProposalError(change.stale, "stale")
        rec["message"] = change.apply(rec, deps, _name(rec, deps))
        rec |= {"state": "approved", "approved_at": iso_utc(deps.clock()), "approved_by": deps.decided_by}
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
        change = CHANGES[rec["action"]]
        if change.edit is None:
            raise InputError("A watchlist proposal has nothing to edit: approve it or cancel it.")
        if wrong := [x for x in given if x not in change.editable]:
            raise InputError(f"{change.what} doesn't take {', '.join(wrong)}.")
        change.edit(rec, given, deps)
        deps.state.save_proposal(rec)
        return view(rec, deps)


def view(rec: dict, deps) -> dict:
    """The Proposal as the card and the tool show it. A proposed one past its time is expired."""
    state = rec["state"]
    if state == "proposed" and deps.clock() >= dt.datetime.fromisoformat(rec["expires_at"]):
        state = "expired"
    fields = {x: rec["fields"].get(x) for x in (*STATUS_FIELDS, *DETAIL_FIELDS)}
    change = CHANGES[rec["action"]]
    return Proposal(
        proposal_id=rec["id"], action=rec["action"], title=change.title(rec, _name(rec, deps)), why=rec["why"],
        cve_id=rec["cve_id"],
        product=rec["product"], product_name=deps.knowledge.products.get(rec["product"]), before=rec["before"],
        after=rec["after"], fields=ProposalFields(**fields), state=state, message=rec["message"],
        as_of=deps.as_of, created_at=rec["created_at"], expires_at=rec["expires_at"],
        approved_at=rec["approved_at"], approved_by=rec["approved_by"],
        sources=rec.get("sources", []),  # a proposal saved before B22 has none
        editable=list(change.editable), link_to=change.link_to).model_dump()

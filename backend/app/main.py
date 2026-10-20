"""FastAPI app: routes, error handlers, CORS.

Run: `uv run uvicorn app.main:app --port 8000` (settings from the environment, see .env.example).
"""
import datetime as dt
import hmac
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, Header, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints

from app import access, agent, card_actions, chat_turn, dashboard, page_context, proposals, refresh, server_log
from app.alerts import alert_counts
from app.app_settings import AppSettings, ResetRequest, TestAlertRequest
from app.auth import SIGNED_OUT, SignedOut, Verifier, current_user, is_owner, owner_only
from app.config import Settings
from app.cve_filters import CveView, InvalidFilter
from app.deps import Deps, build_deps
from app.dev import dev_router
from app.errors import InputError, LLMError, NotAllowed, NotApproved, NotOwner, RateLimited
from app.notify import (RUN_WAIT, NotifyError, TelegramNotifier, WaitBudget, channel_status, deliver, format_alert,
                        send_on, tap_link)
from app.live_data import MixedFeeds
from app.server_settings import ServerUpdate, TelegramToken, effective as server_effective, status as server_status
from app.server_settings import updated as server_updated
from app.one_port import one_port
from app.profile import NAME_MAX, ProfileUpdate, clean_name
from app.rate_limits import ChatLimits, refused
from app.proposals import ProposalEdit, ProposalError
from app.refresh import CheckReply
from app.llm.base import ToolCall
from app.schemas import ChatReply, ChatRequest, ToolCallRecord
from app.tools.registry import Context, offered_tool, run_tool
from app.verdict import USAGES
from app.watched import WatchedCves

log = logging.getLogger(__name__)

Text = Annotated[str, StringConstraints(strip_whitespace=True, max_length=300)]


class StatusUpdate(BaseModel):
    """A status change and its decision record (A16b). Which fields a status needs is checked by app.status."""
    model_config = ConfigDict(extra="forbid")
    status: str
    justification: Text | None = None  # not affected: a VEX justification
    reason: Text | None = None  # accepted
    review_date: str | None = None  # accepted, YYYY-MM-DD
    compensating_control: Text | None = None  # accepted, optional
    note: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None


class WatchedProduct(BaseModel):
    """One watched product with its fields (A15). Missing fields take the defaults."""
    model_config = ConfigDict(extra="forbid")
    product: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)]
    usage: Literal[USAGES] | None = None  # type: ignore[valid-type]
    version: Annotated[str, StringConstraints(strip_whitespace=True, max_length=40)] | None = None
    internet_facing: StrictBool | None = None


class WatchlistUpdate(BaseModel):
    products: list[Annotated[str, StringConstraints(max_length=40)] | WatchedProduct]  # a plain name keeps its fields


class ToolRetry(BaseModel):
    """Try again on a tool card (B20): one step of an answer, run again with the same arguments."""
    name: str
    args: dict
    page: dict | None = None  # the answer's page context; checked again, as for /chat


class AccessRequest(BaseModel):
    """B38: a request to use Patch, with an optional note for the owner (plain text, at most 280 characters once
    trimmed). The length is checked after `access.clean_note`."""
    model_config = ConfigDict(extra="forbid")
    note: Annotated[str, StringConstraints(max_length=2000)] | None = None


class AccessChange(BaseModel):
    """B38: the owner approves, refuses, or undoes a refusal (back to waiting or straight to approved). B45: and sets
    the person's role, when approving or later. At least one of the two."""
    model_config = ConfigDict(extra="forbid")
    status: Literal["waiting", "approved", "refused"] | None = None
    role: Literal["viewer", "trusted", "reviewer"] | None = None


class TelegramChatsRequest(BaseModel):
    """B57: Find my chat id. The token typed on Settings (not saved yet); none: the one that applies."""
    model_config = ConfigDict(extra="forbid")
    bot_token: TelegramToken | None = None


class FakeFeedsRequest(BaseModel):
    """The fake feeds that fail from now on (B20). The fake feeds only."""
    fail: list[Literal["nvd", "kev", "osv", "epss"]]


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def _too_many(exc: RateLimited, user: str, route: str, extra: dict | None = None) -> JSONResponse:
    """The one 429 form (B11): the error with its retry time, and Retry-After. Logged with the user and route."""
    log.warning("Rate limit: user=%s route=%s retry_at=%s: %s", user, route, exc.retry_at, exc.message)
    return JSONResponse(status_code=429, headers={"Retry-After": str(exc.retry_after)}, content={
        "error": {"code": exc.code, "message": exc.message, "retry_at": exc.retry_at,
                  "retry_after": exc.retry_after}, **(extra or {})})


def create_app(deps: Deps | None = None) -> FastAPI:
    deps = deps or build_deps(Settings.from_env())  # a bad setting fails here, with a plain message

    # With sign-in on (B10) the API's docs aren't served: they would map every route for anyone
    hidden = {"docs_url": None, "redoc_url": None, "openapi_url": None} if deps.settings.auth else {}
    app = FastAPI(title="Patch, the LLM-security assistant", **hidden)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=deps.settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type", "Authorization"],  # Authorization: the Clerk session token (B10)
    )
    # Sign-in (B10): every route on `api` needs a user (its router's dependency); only /health is on `app` itself.
    # B13: the scheduled refresh route (Cloud Scheduler) is on `app` too, with its own secret header instead of a user.
    app.state.verify = Verifier(deps.settings) if deps.settings.auth else None
    app.state.owner = deps.settings.owner  # app.auth.owner_only
    app.state.role = deps.users.access.role  # app.auth.allowed (B45): read on every check, so a change applies next

    def known(user: Annotated[str, Depends(current_user)]) -> str:
        """Every request on `api` has a user, and that user counts for the refresh from now on (story 61): their
        alerts and "new since last check" come even before they save anything, and after a reset. With sign-in on,
        only an approved user (B38): anyone else gets a 403 with their status, and doesn't count."""
        status = deps.users.access.status(user)
        if status != "approved":
            raise NotApproved(status)
        deps.users.seen(user)
        return user

    api = APIRouter(dependencies=[Depends(known)])
    # B38: the routes a signed-in user who isn't approved yet may use: their status and their request
    asking = APIRouter(dependencies=[Depends(current_user)])

    @app.exception_handler(SignedOut)
    async def signed_out(request: Request, exc: SignedOut):
        return _error(401, "signed_out", SIGNED_OUT)

    @app.exception_handler(RequestValidationError)
    async def bad_request(request: Request, exc: RequestValidationError):
        problems = "; ".join(f"{'.'.join(map(str, e['loc'][1:])) or 'body'}: {e['msg']}" for e in exc.errors())
        return _error(400, "invalid_request", f"The request isn't in the expected shape. {problems}")

    @app.exception_handler(InputError)
    async def input_error(request: Request, exc: InputError):
        return _error(400, exc.code, exc.message)

    @app.exception_handler(LLMError)
    async def llm_error(request: Request, exc: LLMError):
        log.warning("LLM error: %s", exc.message)
        if exc.code == "spending_cap":  # B11: OpenRouter's 402, passed on as itself with its plain message
            return _error(402, exc.code, exc.public or LLMError.SPENDING_CAP)
        return _error(502, "llm_error", exc.public or LLMError.GENERIC)

    @app.exception_handler(RateLimited)
    async def rate_limited(request: Request, exc: RateLimited):
        return _too_many(exc, request.state.user, request.url.path)

    @app.exception_handler(ProposalError)
    async def proposal_error(request: Request, exc: ProposalError):
        return _error(exc.status, exc.code, exc.message)

    @app.exception_handler(NotAllowed)  # B45: a role's route group; NotOwner is one of them
    async def not_allowed(request: Request, exc: NotAllowed):
        return _error(403, exc.code, exc.message)

    @app.exception_handler(NotApproved)
    async def not_approved(request: Request, exc: NotApproved):
        return JSONResponse(status_code=403, content={"error": {"code": exc.code, "status": exc.status,
                                                                "message": exc.message}})

    @app.exception_handler(NotifyError)
    async def notify_error(request: Request, exc: NotifyError):
        return _error(400 if exc.code == "not_configured" else 502, exc.code, exc.message)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        log.exception("unhandled error")  # stack trace in the server log only
        return _error(500, "internal_error", "Something went wrong on the server.")

    @app.middleware("http")
    async def fresh_data(request: Request, call_next):
        """Before each request: the owner's saved server settings (B26: live mode switched on Settings, by this
        server or another instance), and in live mode a new live version from Check now or the CLI (B02)."""
        try:
            await run_in_threadpool(deps.sync)
        except Exception:  # keep serving the data already loaded; the next request tries again
            log.exception("Loading the new settings or live version failed")
        return await call_next(request)

    def you(user: Annotated[str, Depends(current_user)]) -> Deps:
        """The parts acting for the calling user (B09): their state (their profile's name for decision records, B48)
        and their id. Every route that reads or writes a user's state takes this; the live data and the refresh are
        shared."""
        return deps.for_user(user)

    You = Annotated[Deps, Depends(you)]

    limits = ChatLimits(deps.settings.chat_per_minute, deps.settings.chat_per_day, lambda: deps.clock())

    def chat_allowed(request: Request, user: Annotated[str, Depends(current_user)]) -> None:
        """B11: one chat message counted for the caller, or a 429 before the model is asked."""
        request.state.user = user
        limits.take(user)

    def data_status() -> dict:
        """The data mode and when the live data was last checked (None in snapshot mode, or before the first run)."""
        return {"mode": deps.settings.data_mode,
                "last_checked": deps.refresher.last_checked() if deps.refresher else None}

    def schedule_status(user: str) -> dict:
        """B19: the schedule, which is the owner's (B09); `yours`: the caller is the owner, so may change it. Anyone
        else sees it read-only, as "the owner's schedule"."""
        return {**refresh.schedule_status(deps.refresher, deps.owner_state.settings().alerts),
                "yours": user == deps.settings.owner}

    @app.get("/health")
    def health():
        return {"status": "ok", "llm": deps.llm.name, "model": deps.llm.label(), "as_of": deps.as_of,
                "dev_panel": deps.settings.dev_panel, **data_status(),
                # B10: whether to sign in, and the Clerk instance's publishable key (not a secret): read at run
                # time, so one built frontend (the container's) fits any Clerk instance
                "auth": {"on": deps.settings.auth,
                         "publishable_key": deps.settings.clerk_publishable_key if deps.settings.auth else None}}

    # --- Sign-up requests (B38, #81): sign-up is open in Clerk; the owner lets each new account in

    def own_access(user: str) -> dict:
        entry = deps.users.access.entry(user) if deps.settings.auth else None
        return {"status": deps.users.access.status(user), "owner": user == deps.settings.owner,
                "role": deps.users.access.role(user),  # B45: read on each page load, so a change shows next load
                "sign_in": deps.settings.auth, "note": entry["note"] if entry else None,
                "at": entry["at"] if entry else None}

    @asking.get("/access")
    def get_access(user: Annotated[str, Depends(current_user)]):
        """The caller's own status: approved (the owner always; everyone with sign-in off), waiting, refused, or
        none (hasn't asked yet), with their own note."""
        return own_access(user)

    @asking.post("/access/request")
    def request_access(body: AccessRequest, user: Annotated[str, Depends(current_user)], later: BackgroundTasks):
        """Ask the owner to be let in. A new request alerts the owner once, on their channels; the alert says only
        that a note is there, never its text (a stranger's words stay off the owner's lock screen). Asking again
        changes nothing: a waiting request stays as it was, a refused one stays refused, with no new alert.
        B55: the alert goes after the reply (a background task), so its waits after an ntfy 429 never hold up the
        requester's page."""
        note = access.clean_note(body.note)
        if note and len(note) > access.NOTE_MAX:
            raise InputError(f"The note can be at most {access.NOTE_MAX} characters.", "note_too_long")
        if deps.users.access.status(user) in ("approved", "refused"):
            return own_access(user)
        entry, new = deps.users.access.request(user, note)
        if new:
            later.add_task(alert_and_mark, user, bool(entry["note"]))
        return own_access(user)

    def alert_and_mark(user: str, with_note: bool) -> None:
        alert_owner(requester_name(user), with_note)
        deps.users.access.mark_alerted(user)

    def requester_name(user: str) -> str:
        """The name in a request's alert (B48): Clerk's, looked up as the Requests card does (CLERK_SECRET_KEY), else
        the user id. Never the session token's claims, never anything the requester typed."""
        if deps.people is not None:
            try:
                name = deps.people([user]).get(user, {}).get("name")
                if name:
                    return name
            except Exception:
                log.exception("Looking up a request's name in Clerk failed")
        return user

    def alert_owner(name: str, with_note: bool) -> None:
        """One alert per request, on the owner's ticked channels, sent at once (quiet hours hold CVE alerts only).
        B55: an ntfy 429 is tried again inside the send, within RUN_WAIT in all; any other failure is logged (by
        send_on) and not tried again: the request still waits on the Requests card."""
        msg = {"title": "New access request", "body": f"From {name[:60]}" + (" (with a note)" if with_note else ""),
               "priority": 4, "tags": ["access_request"], "click": f"{deps.settings.app_url}/settings#requests"}
        wait = WaitBudget(RUN_WAIT, deps.transports.sleep)
        for channel in deps.owner_state.settings().alerts.channels:
            send_on(channel, msg, deps.settings, deps.transports, wait)

    @api.get("/access/requests", dependencies=[Depends(owner_only)])
    def list_requests():
        """The owner's Requests card: every request, newest first, with names and emails asked from Clerk now (one
        call). Patch keeps none of those. Without the secret key, or with Clerk unreachable, user ids only."""
        entries = deps.users.access.all() if deps.settings.auth else {}
        people: dict[str, dict] = {}
        if entries and deps.people is not None:
            try:
                people = deps.people(sorted(entries))
            except Exception:
                log.exception("Looking up the requests' names in Clerk failed")
        rows = [{"user_id": uid, "status": e["status"], "note": e.get("note"), "by": e.get("by"), "at": e.get("at"),
                 "requested_at": e.get("requested_at"), "migrated": bool(e.get("migrated")),
                 "role": e.get("role") or access.DEFAULT_ROLE,
                 "name": people.get(uid, {}).get("name"), "email": people.get(uid, {}).get("email")}
                for uid, e in entries.items()]
        rows.sort(key=lambda r: r["requested_at"] or r["at"] or "", reverse=True)
        return {"requests": rows, "names": bool(people), "you": deps.settings.owner}

    @api.put("/access/requests/{uid}")
    def change_request(uid: str, body: AccessChange, request: Request,
                       owner: Annotated[str, Depends(owner_only)]):
        if is_owner(request, uid):
            raise InputError("The owner is always approved.", "owner")
        if body.status is None and body.role is None:
            raise InputError("Say what to change: the status, the role, or both.", "nothing_to_change")
        try:
            entry = deps.users.access.set(uid, body.status, by=owner, role=body.role)
        except KeyError:
            return _error(404, "not_found", "There's no request from that user.")
        return {"user_id": uid, **entry}

    @api.post("/access/requests/{uid}/remove", dependencies=[Depends(owner_only)])
    def remove_request(uid: str, request: Request):
        """Remove the person: their request and note go; they can ask again (one more alert). Their saved state
        stays, so approving them again brings their watchlist back."""
        if is_owner(request, uid):
            raise InputError("The owner is always approved.", "owner")
        deps.users.access.remove(uid)
        return {"removed": uid}

    # --- Chat (A06)

    @api.post("/chat", response_model=ChatReply, dependencies=[Depends(chat_allowed)])
    def chat(req: ChatRequest, d: You):
        return chat_turn.turn(req, d)  # guard, explain level, page context, step limit (app.chat_turn)

    @api.post("/chat/tool", response_model=ToolCallRecord)
    def retry_tool(body: ToolRetry, d: You, request: Request, user: Annotated[str, Depends(current_user)]):
        """Try again (B20): run one tool step again, as the answer did but without the tool-failure switch. Its
        result goes on its card only: the model doesn't see it, so the answer's text is never rewritten by it.
        Only a tool offered to this user now runs (the chat's own list); one that asks the model or the network
        counts as a chat message (B11), as a refine does."""
        spec = offered_tool(body.name, d)
        if spec is None:
            raise InputError(f"There's no {body.name!r} tool to try again here.", "not_offered")
        if spec.calls_out:
            chat_allowed(request, user)
        page, _ = page_context.validate(body.page, d.knowledge.resolve_product)
        return run_tool(ToolCall(id="retry", name=body.name, args=body.args), d, Context(page=page, user_id=d.user_id))

    @api.post("/chat/action", response_model=card_actions.Proposed | card_actions.Refined)
    def card_action(body: card_actions.CardAction, d: You, request: Request,
                    user: Annotated[str, Depends(current_user)]):
        """A button on a tool card (B24): propose a change to the caller's state (nothing changes until it's
        approved), or run the card's tool again with a fixed filter. A refine asks the model to translate the query
        again, so it counts as a chat message (B11); a proposal runs no model and doesn't."""
        if isinstance(body, card_actions.Propose):
            return card_actions.propose(body, d)
        chat_allowed(request, user)
        return card_actions.refine(body, d, page_context.validate(body.page, d.knowledge.resolve_product)[0])

    @api.get("/examples")
    def examples():
        return agent.examples(web=deps.web is not None)

    # --- Changes Patch proposes (B21): nothing changes until you approve the card

    @api.get("/proposals/{pid}")
    def get_proposal(pid: str, d: You):
        return proposals.get(d, pid)

    @api.post("/proposals/{pid}/approve")
    def approve_proposal(pid: str, d: You):
        return proposals.approve(d, pid)

    @api.post("/proposals/{pid}/cancel")
    def cancel_proposal(pid: str, d: You):
        return proposals.cancel(d, pid)

    @api.patch("/proposals/{pid}")
    def edit_proposal(pid: str, body: ProposalEdit, d: You):
        return proposals.edit(d, pid, body)

    # --- Dashboard (A04). Reads and writes the caller's state, the same state the chat's tools use.

    @api.get("/dashboard")
    def get_dashboard(d: You, product: str | None = None):
        """`product`: the dashboard's filter (A15b), `a,b`. Unknown or unwatched products are ignored."""
        watched = WatchedCves.of(d)
        summary = dashboard.summary(d.knowledge, watched, dashboard.applied_filter(d.knowledge, watched, product))
        # The freshness panel: Live or Snapshot, last checked (B02), and the last run for its partial or failed
        # banner (B20). The next try is the run's start + 5 minutes, the one rule for every trigger.
        last = deps.refresher.last_result() if deps.refresher else None  # B37: with the caller's own alerts only
        return summary | {"data": {**data_status(), "last_result": last.for_user(d.user_id).model_dump() if last else None,
                                    "schedule": schedule_status(d.user_id),  # B19: "Schedule paused"
                                    # B28: the owner is told when live mode reads the made-up test data
                                    "feeds": deps.settings.feeds if d.user_id == deps.settings.owner else None}}

    @api.get("/cves")
    def get_cves(request: Request, d: You, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        """The CVE view's filters by their names (app.cve_filters: product, severity, status, kev, since, verdict;
        the old severity_min and published_since still work), checked by the same rules as the chat's page
        context."""
        try:
            view = CveView.parse(request.query_params, d.knowledge.resolve_product)
        except InvalidFilter as e:
            raise InputError(str(e)) from None
        watched = WatchedCves.of(d)
        rows = watched.rows(**view.filters())
        # B40: every new row the caller hasn't seen, whatever the filters: "Mark all as seen" shows while it's above 0
        return {"total": len(rows), "rows": rows[offset:offset + limit], "new_total": new_total(watched)}

    def new_total(watched: WatchedCves) -> int:
        return len(watched.rows(status="all", new=True))

    @api.post("/cves/seen")
    def mark_all_seen(d: You):
        """B40: "Mark all as seen" on the CVEs list: nothing is new for the caller any more."""
        d.state.seen()
        return {"new_total": 0}

    @api.get("/cves/{cve_id}")
    def get_cve(cve_id: str, d: You):
        """The page for one CVE (B35): its facts in full and, when it's watched, its row from the CVEs page."""
        try:
            return WatchedCves.of(d).page(cve_id.strip().upper())
        except KeyError:
            return _error(404, "not_found", f"No such CVE: {cve_id[:40]} isn't in the snapshot.")

    @api.post("/cves/{cve_id}/seen")
    def cve_seen(cve_id: str, d: You):
        """B40: the CVE page was opened, so this CVE isn't new for the caller any more. A POST from the page, not a
        side effect of GET /cves/<id>: reads (the chat's tools, a reload's prefetch) never mark anything seen."""
        cve = d.knowledge.cves.get(cve_id.strip().upper())
        if cve is None:
            return _error(404, "not_found", f"No such CVE: {cve_id[:40]} isn't in the snapshot.")
        d.state.seen(cve["id"])
        return {"id": cve["id"], "new_total": new_total(WatchedCves.of(d))}

    @api.patch("/cves/{cve_id}")
    def patch_cve(cve_id: str, body: StatusUpdate, d: You):
        try:
            cve, record = d.state.set_status(cve_id, body.status, d.as_of, "page", by=d.decided_by,
                                                **body.model_dump(exclude={"status"}))
        except KeyError:
            return _error(404, "not_found", f"{cve_id} isn't in the snapshot.")
        return {"id": cve["id"], "status": body.status, "decision": record}

    def watchlist_body(d: Deps):
        """The watchlist, and every product with its fields (watched first, in watchlist order), so the editor
        can show a product's fields as soon as it's ticked."""
        stack, k = d.state.read(), d.knowledge
        products = []
        for pid in [*stack.watchlist, *(p for p in k.products if not stack.watches(p))]:
            osv = k.osv["products"].get(pid, {"coverage": "none", "packages": []})
            products.append({"product": pid, "name": k.products[pid], "watched": stack.watches(pid),
                             **stack.fields(pid).as_dict(), "coverage": osv["coverage"],
                             "ecosystem": osv["packages"][0]["ecosystem"] if osv["packages"] else None})
        return {"watchlist": list(stack.watchlist), "products": products}

    # --- Your profile (B48, #77): anonymous by default, an optional display name in the caller's own state

    @api.get("/profile")
    def get_profile(d: You):
        return {"name": d.state.profile_name()}

    @api.put("/profile")
    def put_profile(body: ProfileUpdate, d: You):
        """Set, change or remove (null or empty) the caller's display name. Plain text, one line, at most NAME_MAX."""
        name = clean_name(body.name)
        if name and len(name) > NAME_MAX:
            raise InputError(f"A display name can be at most {NAME_MAX} characters.", "name_too_long")
        return {"name": d.state.save_profile_name(name)}

    @api.get("/watchlist")
    def get_watchlist(d: You):
        return watchlist_body(d)

    @api.put("/watchlist")
    def put_watchlist(body: WatchlistUpdate, d: You):
        names = [p if isinstance(p, str) else p.product for p in body.products]
        fields = {p.product: p.model_dump(exclude={"product"}) for p in body.products if not isinstance(p, str)}
        d.state.set_watchlist(names, fields)
        return watchlist_body(d)

    # --- Settings page (A13): alert rules, channels, test alerts, reset

    def server_part(user: str) -> dict | None:
        """B26: the owner's server settings, as Settings shows them (secrets only as set or not); None for anyone
        else, who never sees these fields."""
        if user != deps.settings.owner:
            return None
        return server_status(deps.env, deps.owner_state.server_settings())

    @api.get("/settings")
    def get_settings(d: You):
        """The caller's settings. The channels (how each is set up: a masked address, the ntfy server) are the
        owner's, so anyone else gets none (B50, #95: B48 hid the Delivery card, the reply still held them)."""
        owner = d.user_id == deps.settings.owner
        return {"settings": d.state.settings().model_dump(), "schedule": schedule_status(d.user_id),
                "channels": channel_status(deps.settings, deps.transports) if owner else None,
                "alert_tz": deps.settings.alert_tz, "server": server_part(d.user_id), "owner": owner}

    @api.put("/settings/server", dependencies=[Depends(owner_only)])
    def put_server_settings(body: ServerUpdate):
        """B26: what the owner sets instead of .env. A field left out stays, a value saves it, null removes the saved
        one. One the environment sets is refused (400 set_in_env): the environment wins. Applied at once, with no
        restart: live or snapshot data, the time zone, the alert link, the channels. The reply never holds a
        secret."""
        owner = deps.owner_state
        saved = server_updated(deps.env, owner.server_settings(), body)
        try:  # B28: live mode on a folder the other kind of feeds wrote is refused before anything is saved
            deps.check_live_folder(server_effective(deps.env, saved))
        except MixedFeeds as e:
            raise InputError(str(e), "mixed_feeds") from None
        owner.save_server_settings(saved)
        deps.sync()
        log.info("Server settings changed on Settings: %s", ", ".join(sorted(body.model_fields_set)) or "nothing")
        return {"server": server_part(deps.settings.owner),
                "channels": channel_status(deps.settings, deps.transports), "alert_tz": deps.settings.alert_tz}

    @api.post("/settings/telegram/chats", dependencies=[Depends(owner_only)])
    def telegram_chats(body: TelegramChatsRequest):
        """B57, Find my chat id: the chats that wrote to the bot lately (Telegram's getUpdates, asked here so the
        token never goes into a browser's address bar). The typed token if there is one (not saved), else the one
        that applies. The dry run (the browser check) asks Telegram nothing and gives one example chat."""
        token = body.bot_token or deps.settings.telegram_bot_token
        if not token:
            raise InputError("Type the bot token first: Patch asks Telegram with it.", "not_configured")
        if deps.settings.notify_dry_run:
            return {"chats": [{"id": "123456789", "name": "Example chat (dry run: Telegram wasn't asked)",
                               "kind": "private"}]}
        return {"chats": TelegramNotifier(token, "", opener=deps.transports.opener).chats()}

    @api.put("/settings")
    def put_settings(body: AppSettings, d: You):
        """The caller's settings. The schedule (hours, paused) runs the shared refresh, so only the owner's count:
        anyone else's change to them is refused, and the rest of their settings save as usual."""
        if d.user_id != deps.settings.owner:
            saved = d.state.settings().alerts
            if (body.alerts.schedule_hours, body.alerts.schedule_paused) != (saved.schedule_hours,
                                                                              saved.schedule_paused):
                raise NotOwner("The schedule is the owner's: it runs the one refresh every user shares. Only the "
                               "owner can change or pause it.")
        return {"settings": d.state.save_settings(body).model_dump()}

    @api.get("/alerts")
    def get_alerts(d: You):
        return {"alerts": d.state.alerts_log()[:20]}

    @api.post("/alerts/test")
    def test_alert(body: TestAlertRequest, d: You):
        """A real alert from the most urgent open CVE on the watchlist, on one channel. "preview" only records it.
        The channels are the owner's (B09): another user may only preview."""
        if body.channel != "preview" and d.user_id != deps.settings.owner:
            raise InputError("Alerts go to the owner's channels only, so you can't send a test alert. Use Preview to "
                             "see the message.", "not_owner")
        row = WatchedCves.of(d).most_urgent()  # the top of the priority order, with its due date
        if row is None:
            raise InputError("There are no open CVEs on your watchlist to build a test alert from.")
        cve = deps.knowledge.cves.get(row["id"])
        msg = format_alert(cve, "kev" if row["kev"] else "new", deps.knowledge, deps.settings.app_url, due=row)
        msg["title"] = "Test · " + msg["title"]
        entry = deliver(body.channel, msg, deps.settings, deps.transports, d.state)
        note = ("Recorded only: nothing was sent." if body.channel == "preview"
                else f"Sent by {body.channel}. Check that it arrived.")
        # B26: what tapping the phone alert does (ntfy; email has the same link or none). B57: Telegram's link is the
        # message's Open in Patch button
        link = tap_link(msg["click"])
        if body.channel == "telegram":
            tap = (f"Open in Patch opens Patch at {cve['id']}." if link else
                   "The message has no Open in Patch button: the app address for alert links can't be reached from "
                   "a phone.")
        else:
            tap = (f"Tapping it opens Patch at {cve['id']}." if link else
                   "Tapping it opens the message in the ntfy app: the app address for alert links can't be reached "
                   "from a phone.")
        return {"alert": msg, "channel": body.channel, "sent": entry["sent"], "note": note, "tap_link": link,
                "tap": tap}

    @api.post("/state/reset")
    def reset_state(body: ResetRequest, d: You):
        d.state.reset()  # the caller's state only (B09)
        return {"reset": True, "watchlist": list(d.state.read().watchlist)}

    # --- Live data (B02): Check now and the refresh status. The CLI (python -m app.refresh) runs the same function.

    def live_only():
        if deps.refresher is None:
            raise InputError("The data is a frozen snapshot, so there is nothing to check. Switch to live data on "
                             "Settings (the owner) to refresh it from the feeds.", "snapshot_mode")
        return deps.refresher

    @api.post("/refresh", response_model=CheckReply)
    def check_now(user: Annotated[str, Depends(current_user)]):
        """Check now: run the refresh (or be refused: one at a time, at most one per 5 minutes). A refusal is the
        429 form (B11), still carrying the reply: the refusal and the last run's result, for the freshness card.
        Either way the result holds the caller's own alerts only (B37, #87): the run alerts every user."""
        reply = live_only().run("button")
        if reply.result is not None:
            reply = reply.model_copy(update={"result": reply.result.for_user(user)})
        if reply.ran:
            deps.sync()  # load the new version now, so the reply comes when the new CVEs can be found
            assert reply.result is not None  # B34: the dashboard's line counts the caller's own alerts
            return reply.model_copy(update={"alerts_for_you": alert_counts(reply.result.alerts.get(user, []))})
        assert reply.refusal is not None
        nxt = dt.datetime.fromisoformat(reply.refusal.next_allowed)
        return _too_many(refused(reply.refusal.message, deps.clock(), nxt, say_when=False), user, "/refresh",
                         reply.model_dump())

    if deps.settings.scheduler_secret:
        secret = deps.settings.scheduler_secret.encode()

        @app.post("/refresh/scheduled")
        def scheduled_refresh(x_scheduler_secret: Annotated[str, Header()] = ""):
            """B13: Cloud Scheduler's hourly tick. On `app`, not `api`: the deliberate exception to "every route needs
            a user" (B10), since the scheduler has no Clerk session. It needs its own secret instead, compared in
            constant time so the answer's timing says nothing about how much of a guess was right. It runs the
            schedule exactly as the systemd timer's CLI does (app.refresh.scheduled_tick): the refresh only when the
            owner's Settings schedule is due and not paused. A run where no feed answered is a 502, so Cloud
            Scheduler's log shows the failed attempt; everything else is a 200."""
            if not hmac.compare_digest(x_scheduler_secret.encode(), secret):
                log.warning("Scheduled refresh refused: missing or wrong X-Scheduler-Secret")
                return _error(401, "not_scheduler", "This route is for the scheduler only.")
            body = refresh.scheduled_tick(live_only(), deps.owner_state.settings().alerts)
            if body["ran"]:
                deps.sync()
            failed = body["ran"] and body["result"] and body["result"]["status"] == "failed"
            return JSONResponse(status_code=502 if failed else 200, content=body)

    @api.get("/refresh")
    def refresh_status(user: Annotated[str, Depends(current_user)]):
        return {**data_status(), **(deps.refresher.status(user) if deps.refresher else
                                    {"running": False, "next_allowed": None, "last_result": None})}

    @api.get("/refresh/runs")
    def refresh_runs(d: You):
        """B19: the "Refresh runs" card: the schedule (paused or not, when next due) and the last 20 runs, with the
        caller's own alert counts (B09)."""
        return {**data_status(), "schedule": schedule_status(d.user_id),
                "runs": deps.refresher.history(d.user_id) if deps.refresher else []}

    if deps.settings.feeds == "fake":  # B26: live mode can be switched on later, so the routes exist in both modes
        @api.post("/refresh/reset", dependencies=[Depends(owner_only)])
        def reset_live_data(body: ResetRequest):
            """The fake feeds only: the live data back to the snapshot, an empty run log and no alerts, so the browser check
            can run Check now again (DECISIONS.md, 2026-10-15). The real feeds have no such route."""
            live_only().reset()
            for user in deps.users.ids():  # B04: so the next Check now alerts again, for every user (B09)
                deps.users.state(user).clear_alerts()
            deps.sync()
            return {"reset": True}

        @api.post("/refresh/fake-feeds", dependencies=[Depends(owner_only)])
        def fail_fake_feeds(body: FakeFeedsRequest):
            """The fake feeds only: which of them fail from now on (B20, the browser check's partial run). Like
            FAKE_FEEDS_FAIL, for this server until it restarts; `[]` makes every feed answer again."""
            live_only().feeds.fail = ",".join(body.fail) or None
            return {"fail": body.fail}

    # --- Dev panel (A11): only when DEV_PANEL is on, because it shows internals. Off, every /dev route is a 404.
    if deps.settings.dev_panel:
        api.include_router(dev_router(deps))
    app.include_router(asking)
    app.include_router(api)

    # --- One port (B12): with FRONTEND_DIR set (the container), the built frontend too, and the API under /api
    if deps.settings.frontend_dir is not None:
        # B61: the app address as the alerts use it (B26: the environment's, else the owner's saved one), read when a
        # page is asked for: a link fetcher may be the first request after a cold start, before any API call syncs
        return one_port(app, deps.settings.frontend_dir,
                        lambda: server_effective(deps.env, deps.owner_state.server_settings()).app_url)
    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` builds the app on first access, so importing this module in tests is free.
    if name == "app":
        server_log.setup()  # B54: the app's own log lines, before building it logs any
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)

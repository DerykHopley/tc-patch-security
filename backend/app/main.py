"""FastAPI app: routes, error handlers, CORS.

Run: `uv run uvicorn app.main:app --port 8000` (settings from the environment, see .env.example).
"""
import logging

from fastapi import FastAPI, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints

from app import agent, chat_turn, dashboard
from app.app_settings import AppSettings, ResetRequest, TestAlertRequest
from app.config import Settings
from app.cve_filters import CveView, InvalidFilter
from app.deps import Deps, build_deps
from app.dev import dev_router
from app.errors import InputError, LLMError
from app.notify import NotifyError, channel_status, deliver, format_alert
from app.one_port import one_port
from app.refresh import CheckReply
from app.schemas import ChatReply, ChatRequest
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


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(deps: Deps | None = None) -> FastAPI:
    deps = deps or build_deps(Settings.from_env())  # a bad setting fails here, with a plain message

    app = FastAPI(title="Patch, the LLM-security assistant")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=deps.settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH"],
        allow_headers=["Content-Type"],
    )

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
        return _error(502, "llm_error", exc.public or "The language model didn't respond properly. Try again in a moment.")

    @app.exception_handler(NotifyError)
    async def notify_error(request: Request, exc: NotifyError):
        return _error(400 if exc.code == "not_configured" else 502, exc.code, exc.message)

    @app.exception_handler(Exception)
    async def internal_error(request: Request, exc: Exception):
        log.exception("unhandled error")  # stack trace in the server log only
        return _error(500, "internal_error", "Something went wrong on the server.")

    if deps.live:
        @app.middleware("http")
        async def fresh_data(request: Request, call_next):
            """Live mode (B02): a new live version, from Check now or the CLI, is loaded before the next request."""
            try:
                await run_in_threadpool(deps.sync)
            except Exception:  # keep serving the data already loaded; the next request tries again
                log.exception("Loading the new live version failed")
            return await call_next(request)

    def data_status() -> dict:
        """The data mode and when the live data was last checked (None in snapshot mode, or before the first run)."""
        return {"mode": deps.settings.data_mode,
                "last_checked": deps.refresher.last_checked() if deps.refresher else None}

    @app.get("/health")
    def health():
        return {"status": "ok", "llm": deps.llm.name, "model": deps.llm.label(), "as_of": deps.as_of,
                "dev_panel": deps.settings.dev_panel, **data_status()}

    # --- Chat (A06)

    @app.post("/chat", response_model=ChatReply)
    def chat(req: ChatRequest):
        return chat_turn.turn(req, deps)  # guard, explain level, page context, step limit (app.chat_turn)

    @app.get("/examples")
    def examples():
        return agent.examples()

    # --- Dashboard (A04). Reads and writes deps.state, the same state the chat's tools use.

    @app.get("/dashboard")
    def get_dashboard(product: str | None = None):
        """`product`: the dashboard's filter (A15b), `a,b`. Unknown or unwatched products are ignored."""
        watched = WatchedCves.of(deps)
        summary = dashboard.summary(deps.knowledge, watched, dashboard.applied_filter(deps.knowledge, watched, product))
        return summary | {"data": data_status()}  # the freshness panel: Live or Snapshot, last checked (B02)

    @app.get("/cves")
    def get_cves(request: Request, limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        """The CVE view's filters by their names (app.cve_filters: product, severity, status, kev, since, verdict;
        the old severity_min and published_since still work), checked by the same rules as the chat's page
        context."""
        try:
            view = CveView.parse(request.query_params, deps.knowledge.resolve_product)
        except InvalidFilter as e:
            raise InputError(str(e)) from None
        rows = WatchedCves.of(deps).rows(**view.filters())
        return {"total": len(rows), "rows": rows[offset:offset + limit]}

    @app.patch("/cves/{cve_id}")
    def patch_cve(cve_id: str, body: StatusUpdate):
        try:
            cve, record = deps.state.set_status(cve_id, body.status, deps.as_of, "page",
                                                **body.model_dump(exclude={"status"}))
        except KeyError:
            return _error(404, "not_found", f"{cve_id} isn't in the snapshot.")
        return {"id": cve["id"], "status": body.status, "decision": record}

    def watchlist_body():
        """The watchlist, and every product with its fields (watched first, in watchlist order), so the editor
        can show a product's fields as soon as it's ticked."""
        stack, k = deps.state.read(), deps.knowledge
        products = []
        for pid in [*stack.watchlist, *(p for p in k.products if not stack.watches(p))]:
            osv = k.osv["products"].get(pid, {"coverage": "none", "packages": []})
            products.append({"product": pid, "name": k.products[pid], "watched": stack.watches(pid),
                             **stack.fields(pid).as_dict(), "coverage": osv["coverage"],
                             "ecosystem": osv["packages"][0]["ecosystem"] if osv["packages"] else None})
        return {"watchlist": list(stack.watchlist), "products": products}

    @app.get("/watchlist")
    def get_watchlist():
        return watchlist_body()

    @app.put("/watchlist")
    def put_watchlist(body: WatchlistUpdate):
        names = [p if isinstance(p, str) else p.product for p in body.products]
        fields = {p.product: p.model_dump(exclude={"product"}) for p in body.products if not isinstance(p, str)}
        deps.state.set_watchlist(names, fields)
        return watchlist_body()

    # --- Settings page (A13): alert rules, channels, test alerts, reset

    @app.get("/settings")
    def get_settings():
        return {"settings": deps.state.settings().model_dump(),
                "channels": channel_status(deps.settings, deps.transports)}

    @app.put("/settings")
    def put_settings(body: AppSettings):
        return {"settings": deps.state.save_settings(body).model_dump()}

    @app.get("/alerts")
    def get_alerts():
        return {"alerts": deps.state.alerts_log()[:20]}

    @app.post("/alerts/test")
    def test_alert(body: TestAlertRequest):
        """A real alert from the most urgent open CVE on the watchlist, on one channel. "preview" only records it."""
        row = WatchedCves.of(deps).most_urgent()  # the top of the priority order, with its due date
        if row is None:
            raise InputError("There are no open CVEs on your watchlist to build a test alert from.")
        cve = deps.knowledge.cves.get(row["id"])
        msg = format_alert(cve, "kev" if row["kev"] else "new", deps.knowledge, deps.settings.app_url, due=row)
        msg["title"] = "Test · " + msg["title"]
        entry = deliver(body.channel, msg, deps.settings, deps.transports, deps.state)
        note = ("Recorded only: nothing was sent." if body.channel == "preview"
                else f"Sent by {body.channel}. Check that it arrived.")
        return {"alert": msg, "channel": body.channel, "sent": entry["sent"], "note": note}

    @app.post("/state/reset")
    def reset_state(body: ResetRequest):
        deps.state.reset()
        return {"reset": True, "watchlist": list(deps.state.read().watchlist)}

    # --- Live data (B02): Check now and the refresh status. The CLI (python -m app.refresh) runs the same function.

    def live_only():
        if deps.refresher is None:
            raise InputError("The data is a frozen snapshot, so there is nothing to check. Set DATA_MODE=live to "
                             "refresh it from the feeds.", "snapshot_mode")
        return deps.refresher

    @app.post("/refresh", response_model=CheckReply)
    def check_now():
        """Check now: run the refresh (or be refused: one at a time, at most one per 5 minutes)."""
        reply = live_only().run("button")
        if reply.ran:
            deps.sync()  # load the new version now, so the reply comes when the new CVEs can be found
        return reply

    @app.get("/refresh")
    def refresh_status():
        return {**data_status(), **(deps.refresher.status() if deps.refresher else
                                    {"running": False, "next_allowed": None, "last_result": None})}

    if deps.live and deps.settings.feeds == "fake":
        @app.post("/refresh/reset")
        def reset_live_data(body: ResetRequest):
            """The fake feeds only: the live data back to the snapshot and an empty run log, so the browser check
            can run Check now again (DECISIONS.md, 2026-10-15). The real feeds have no such route."""
            live_only().reset()
            deps.sync()
            return {"reset": True}

    # --- Dev panel (A11): only when DEV_PANEL is on, because it shows internals. Off, every /dev route is a 404.
    if deps.settings.dev_panel:
        app.include_router(dev_router(deps))

    # --- One port (B12): with FRONTEND_DIR set (the container), the built frontend too, and the API under /api
    if deps.settings.frontend_dir is not None:
        return one_port(app, deps.settings.frontend_dir)
    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` builds the app on first access, so importing this module in tests is free.
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)

"""FastAPI app: routes, error handlers, CORS.

Run: `uv run uvicorn app.main:app --port 8000` (settings from the environment, see .env.example).
"""
import logging

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StrictBool, StringConstraints

from app import agent, cve_filters, dashboard, guard, page_context
from app.app_settings import AppSettings, ResetRequest, TestAlertRequest
from app.config import Settings
from app.deps import Deps, build_deps
from app.dev import dev_router
from app.errors import InputError, LLMError
from app.notify import NotifyError, channel_status, deliver, format_alert
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

    @app.get("/health")
    def health():
        return {"status": "ok", "llm": deps.llm.name, "model": deps.llm.label(), "as_of": deps.settings.as_of,
                "dev_panel": deps.settings.dev_panel}

    # --- Chat (A06)

    @app.post("/chat", response_model=ChatReply)
    def chat(req: ChatRequest):
        history = [t.model_dump() for t in req.history]
        message, flags = guard.check_message(req.message, history)  # limits and flags, before any LLM call
        level = req.explain_level or deps.state.settings().explain_level  # an override is for this message only
        page, dropped = page_context.validate(req.page, deps.knowledge.resolve_product)  # fixed fields only (A18)
        reply = agent.answer(message, history, deps, max_steps=deps.dev().max_steps, flags=flags, level=level,
                             page=page)
        reply.dropped_context = dropped
        return reply

    @app.get("/examples")
    def examples():
        return agent.examples()

    # --- Dashboard (A04). Reads and writes deps.state, the same state the chat's tools use.

    @app.get("/dashboard")
    def get_dashboard(product: str | None = None):
        """`product`: the dashboard's filter (A15b), `a,b`. Unknown or unwatched products are ignored."""
        watched = WatchedCves.of(deps)
        return dashboard.summary(deps.knowledge, watched, dashboard.applied_filter(deps.knowledge, watched, product))

    @app.get("/cves")
    def get_cves(product: str | None = None, severity_min: str | None = None, status: str = "open",
                 limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), kev: bool | None = None,
                 published_since: str | None = None, verdict: str | None = None):
        pid = None  # the shared rules (app.cve_filters), the same as the chat's page context
        if product:  # one, or several from a dashboard link (A15b): `langflow,ollama`
            pid = cve_filters.products(product, deps.knowledge.resolve_product)
            if not pid:
                bad = next((p for p in product.split(",")
                            if not cve_filters.product(p, deps.knowledge.resolve_product)), product)
                raise InputError(f"{bad.strip()!r} isn't a product I track.")
        severity = cve_filters.severity(severity_min) if severity_min else None
        if severity_min and not severity:
            raise InputError("severity_min must be LOW, MEDIUM, HIGH or CRITICAL.")
        if not cve_filters.status(status):
            raise InputError("status must be open, fixed, not_affected, accepted or all.")
        if published_since:
            published_since = cve_filters.date(published_since)
            if not published_since:
                raise InputError("published_since must be a date, YYYY-MM-DD.")
        if verdict and not cve_filters.verdict(verdict):
            raise InputError("verdict must be affected, not_affected or unknown.")
        rows = WatchedCves.of(deps).rows(pid, severity, status, kev, published_since, verdict)
        return {"total": len(rows), "rows": rows[offset:offset + limit]}

    @app.patch("/cves/{cve_id}")
    def patch_cve(cve_id: str, body: StatusUpdate):
        try:
            cve, record = deps.state.set_status(cve_id, body.status, deps.settings.as_of, "page",
                                                **body.model_dump(exclude={"status"}))
        except KeyError:
            return _error(404, "not_found", f"{cve_id} isn't in the snapshot.")
        return {"id": cve["id"], "status": body.status, "decision": record}

    def watchlist_body():
        """The watchlist, and every product with its fields (watched first, in watchlist order), so the editor
        can show a product's fields as soon as it's ticked."""
        data, k = deps.state.snapshot(), deps.knowledge
        products = []
        for pid in data["watchlist"] + [p for p in k.products if p not in data["watchlist"]]:
            osv = k.osv["products"].get(pid, {"coverage": "none", "packages": []})
            products.append({"product": pid, "name": k.products[pid], "watched": pid in data["watchlist"],
                             **deps.state.fields_of(pid, data), "coverage": osv["coverage"],
                             "ecosystem": osv["packages"][0]["ecosystem"] if osv["packages"] else None})
        return {"watchlist": data["watchlist"], "products": products}

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
        return {"reset": True, "watchlist": deps.state.snapshot()["watchlist"]}

    # --- Dev panel (A11): only when DEV_PANEL is on, because it shows internals. Off, every /dev route is a 404.
    if deps.settings.dev_panel:
        app.include_router(dev_router(deps))

    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` builds the app on first access, so importing this module in tests is free.
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)

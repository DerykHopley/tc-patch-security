"""FastAPI app: routes, error handlers, CORS.

Run: `uv run uvicorn app.main:app --port 8000` (settings from the environment, see .env.example).
"""
import logging

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app import agent, dashboard, guard
from app.config import Settings
from app.deps import Deps, build_deps
from app.errors import InputError, LLMError
from app.knowledge import SEVERITY_ORDER
from app.schemas import ChatReply, ChatRequest

log = logging.getLogger(__name__)

CVE_STATUS_FILTERS = ("open", "fixed", "not_affected", "all")


class StatusUpdate(BaseModel):
    status: str


class WatchlistUpdate(BaseModel):
    products: list[str]


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
        return agent.answer(message, history, deps, flags=flags)

    @app.get("/examples")
    def examples():
        return agent.examples()

    # --- Dashboard (A04). Reads and writes deps.state, the same state the chat's tools use.

    @app.get("/dashboard")
    def get_dashboard():
        return dashboard.summary(deps.knowledge, deps.state.snapshot(), deps.settings.as_of)

    @app.get("/cves")
    def get_cves(product: str | None = None, severity_min: str | None = None, status: str = "open",
                 limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0)):
        pid = None
        if product:
            pid = deps.knowledge.resolve_product(product)
            if not pid:
                raise InputError(f"{product!r} isn't a product I track.")
        severity = severity_min.upper() if severity_min else None
        if severity and severity not in SEVERITY_ORDER:
            raise InputError("severity_min must be LOW, MEDIUM, HIGH or CRITICAL.")
        if status not in CVE_STATUS_FILTERS:
            raise InputError("status must be open, fixed, not_affected or all.")
        return dashboard.list_cves(deps.knowledge, deps.state.snapshot(), pid, severity, status, limit, offset)

    @app.patch("/cves/{cve_id}")
    def patch_cve(cve_id: str, body: StatusUpdate):
        try:
            cve = deps.state.set_status(cve_id, body.status)
        except KeyError:
            return _error(404, "not_found", f"{cve_id} isn't in the snapshot.")
        return {"id": cve["id"], "status": body.status}

    @app.get("/watchlist")
    def get_watchlist():
        return {"watchlist": deps.state.snapshot()["watchlist"]}

    @app.put("/watchlist")
    def put_watchlist(body: WatchlistUpdate):
        return {"watchlist": deps.state.set_watchlist(body.products)}

    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` builds the app on first access, so importing this module in tests is free.
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)

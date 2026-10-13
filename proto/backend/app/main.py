"""FastAPI app: routes, error handlers, CORS (A1–A5, D1–D4, G1–G4, X1–X4, V1, V6)."""
import json
import logging
from collections import Counter

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import dashboard, evals, guard
from app.agent import answer
from app.config import FIXTURES, Settings
from app.deps import Deps, build_deps
from app.errors import InputError, LLMError
from app.knowledge import SEVERITY_ORDER
from app.llm.router import local_url_allowed
from app.notify import NotifyError, channel_status, deliver, format_alert, notifier_for
from app.rag.pipeline import SearchOptions, search_security
from app.rag.projection import projection_for
from app.schemas import (AppSettings, ChatReply, ChatRequest, DevSearchRequest, ResetRequest, StatusUpdate,
                         TestAlertRequest, WatchlistUpdate)

log = logging.getLogger(__name__)


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}})


def create_app(deps: Deps | None = None) -> FastAPI:
    # Built at start-up, so a missing OpenRouter key fails here with a clear message (L2).
    deps = deps or build_deps(Settings.from_env())
    examples = [{"id": s["id"], "question": s["question"]}
                for s in json.loads((FIXTURES / "fake_script.json").read_text())["scripts"]]

    app = FastAPI(title="LLM-security assistant prototype")
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
        return {"status": "ok", "llm": deps.llm.name, "as_of": deps.settings.as_of,
                "dev_panel": deps.settings.dev_panel,
                "model": deps.llm.label() if hasattr(deps.llm, "label") else deps.llm.name}

    @app.get("/examples")
    def get_examples():
        return examples

    @app.post("/chat", response_model=ChatReply)
    def chat(req: ChatRequest):
        history = [t.model_dump() for t in req.history]
        message, flags = guard.check_message(req.message, history)  # V1, V2: before any LLM call
        return answer(message, history, deps, flags=flags)

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
        if severity_min and severity_min.upper() not in SEVERITY_ORDER:
            raise InputError("severity_min must be LOW, MEDIUM, HIGH or CRITICAL.")
        if status not in ("open", "fixed", "not_affected", "all"):
            raise InputError("status must be open, fixed, not_affected or all.")
        return dashboard.list_cves(deps.knowledge, deps.state.snapshot(), pid,
                                   severity_min.upper() if severity_min else None, status, limit, offset)

    @app.get("/watchlist")
    def get_watchlist():
        return {"watchlist": deps.state.snapshot()["watchlist"]}

    @app.put("/watchlist")
    def put_watchlist(body: WatchlistUpdate):
        return {"watchlist": deps.state.set_watchlist(body.products)}

    @app.patch("/cves/{cve_id}")
    def patch_cve(cve_id: str, body: StatusUpdate):
        try:
            cve = deps.state.set_status(cve_id, body.status)
        except KeyError:
            return _error(404, "not_found", f"{cve_id} isn't in the snapshot.")
        return {"id": cve["id"], "status": body.status}

    # --- Settings page (G1–G4)

    @app.get("/settings")
    def get_settings():
        return {
            "settings": deps.state.settings().model_dump(),
            "env": {"llm_provider": deps.llm.name, "env_model": deps.settings.openrouter_model,
                    "openrouter_key": bool(deps.settings.openrouter_api_key),
                    "local_hosts": deps.settings.local_llm_hosts,
                    "channels": channel_status(deps.settings), "dev_panel": deps.settings.dev_panel},
        }

    @app.put("/settings")
    def put_settings(body: AppSettings):
        d = body.dev
        if d.provider == "openrouter" and not deps.settings.openrouter_api_key:
            raise InputError("OpenRouter needs OPENROUTER_API_KEY in backend/.env. Add it and restart the backend.")
        if not local_url_allowed(d.local_base_url, deps.settings.local_llm_hosts):
            raise InputError("The local model URL must be on this machine, for example http://localhost:11434/v1. "
                             "Other hosts need LOCAL_LLM_HOSTS in backend/.env.")
        return {"settings": deps.state.save_settings(body).model_dump()}

    @app.get("/alerts")
    def get_alerts():
        return {"alerts": deps.state.alerts_log()[:20]}

    @app.post("/alerts/test")
    def test_alert(body: TestAlertRequest | None = None):
        """A real alert from the most urgent open CVE on the watchlist, sent on one channel (N2).
        "preview" only records it."""
        channel = body.channel if body else "preview"
        top = dashboard.list_cves(deps.knowledge, deps.state.snapshot(), limit=1)["rows"]
        if not top:
            raise InputError("There are no open CVEs on your watchlist to build a test alert from.")
        cve = deps.knowledge.cves.get(top[0]["id"])
        msg = format_alert(cve, "kev" if cve["kev"] else "new", deps.knowledge, deps.settings.app_url)
        msg["title"] = "Test · " + msg["title"]
        entry = deliver(notifier_for(channel, deps.settings, deps.state), msg, deps.state)
        note = ("Recorded only: nothing was sent." if channel == "preview"
                else f"Sent by {channel}. Check that it arrived.")
        return {"alert": msg, "notifier": channel, "sent": entry["sent"], "note": note}

    @app.post("/state/reset")
    def reset_state(body: ResetRequest):
        deps.state.reset()
        return {"reset": True, "watchlist": deps.state.snapshot()["watchlist"]}

    # --- Dev panel (X1–X4): only when DEV_PANEL is on, because it exposes internals

    if deps.settings.dev_panel:
        @app.get("/dev/info")
        def dev_info():
            chunks = deps.index.chunks
            return {
                "chunks": len(chunks),
                "by_doc_type": dict(Counter(c.doc_type for c in chunks).most_common()),
                "embedder": type(deps.index.embedder).__name__,
                "dim": getattr(deps.index.embedder, "dim", None),
                "word_gate": deps.index.words is not None,
                "llm": deps.llm.name,
                "env_model": deps.settings.openrouter_model,
                "as_of": deps.settings.as_of,
            }

        @app.get("/dev/map")
        def dev_map():
            """Every chunk as a point on a 2D PCA map (X5)."""
            proj = projection_for(deps.index)
            return {
                "explained": [round(e, 4) for e in proj.explained],
                "points": [{"id": c.chunk_id, "doc_id": c.doc_id, "title": c.title, "type": c.doc_type,
                            "x": round(float(x), 4), "y": round(float(y), 4)}
                           for c, (x, y) in zip(deps.index.chunks, proj.coords)],
            }

        @app.get("/dev/models")
        def dev_models(base_url: str):
            """The models a local server offers (M1). Loopback only, like the router."""
            if not local_url_allowed(base_url, deps.settings.local_llm_hosts):
                raise InputError("The local model URL must be on this machine (localhost).")
            import urllib.request
            try:
                with urllib.request.urlopen(base_url.rstrip("/") + "/models", timeout=5) as r:
                    data = json.loads(r.read())
            except OSError:
                return _error(502, "unreachable", f"Nothing answered at {base_url}. Start Ollama, LM Studio's "
                              "server or llama.cpp, then try again.")
            return {"models": sorted(m.get("id", "") for m in data.get("data", []) if m.get("id"))}

        @app.post("/dev/eval")
        def dev_eval_start():
            """Run the 11 example questions against the current model, in the background (M2)."""
            try:
                return evals.start(deps)
            except RuntimeError as e:
                raise InputError(str(e))

        @app.get("/dev/eval/{run_id}")
        def dev_eval_get(run_id: str):
            run = evals.get(run_id, deps) if run_id.replace("-", "").isalnum() else None
            return run or _error(404, "not_found", "No model check with that id.")

        @app.get("/dev/evals")
        def dev_eval_history():
            return {"runs": evals.history(deps)}

        @app.post("/dev/search")
        def dev_search(body: DevSearchRequest):
            """The search pipeline with the current dev settings, showing each step (X3)."""
            dev = deps.state.settings().dev
            opts = SearchOptions(top_n=dev.top_n, per_query_k=dev.per_query_k, per_doc_cap=dev.per_doc_cap,
                                 rrf_k=dev.rrf_k, use_rewrites=dev.use_rewrites, use_filters=dev.use_filters)
            res = search_security(body.query, deps.llm, deps.index, deps.knowledge.resolve_product, opts=opts)
            titles = {h.chunk.chunk_id: h.chunk.title for _, hits in res.lists for h in hits}
            return {
                "query": res.query.model_dump(),
                "lists": [{"query": q, "hits": [{"chunk_id": h.chunk.chunk_id, "title": h.chunk.title,
                                                 "doc_type": h.chunk.doc_type, "score": round(h.score, 3)}
                                                for h in hits]} for q, hits in res.lists],
                "fused": [{"chunk_id": cid, "title": titles[cid], "rrf": round(score, 5)}
                          for cid, score in res.fused[:15]],
                "final": [s.model_dump() for s in res.sources],
                "options": dev.model_dump(),
                # Where each query lands on the map, by the same projection as the chunks (X5).
                "map": [{"query": q, "x": round(float(p[0]), 4), "y": round(float(p[1]), 4)}
                        for (q, _), p in zip(res.lists, projection_for(deps.index).project(
                            deps.index.embedder.embed([q for q, _ in res.lists])))],
            }

    return app


def __getattr__(name: str):
    # `uvicorn app.main:app` builds the app on first access, so importing this module in tests is free.
    if name == "app":
        globals()["app"] = create_app()
        return globals()["app"]
    raise AttributeError(name)

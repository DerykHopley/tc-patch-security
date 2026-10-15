"""The dev panel's routes (A11): model switch, local-model discovery, search tuning, the playground, the embedding map.

Mounted only when DEV_PANEL is on (they show internals): off, every /dev route is a 404.
"""
from collections import Counter

import httpx
from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from app import openrouter_models
from app.app_settings import DevSettings
from app.errors import InputError
from app.evals import model_check, report, retrieval
from app.llm.urls import local_url_allowed
from app.rag.pipeline import search_security
from app.rag.projection import projection_for
from app.tools.registry import TOOLS

FUSED_SHOWN = 15  # the fused column: enough to see what the per-document cap and top-n cut
MODELS_TIMEOUT = 5  # seconds: listing models is quick even when loading one is slow
NOT_LOCAL = ("The local model URL must be on this machine, for example http://localhost:11434/v1. "
             "Other hosts need LOCAL_LLM_HOSTS in backend/.env.")


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)


def _hit(chunk, score: float) -> dict:
    return {"chunk_id": chunk.chunk_id, "title": chunk.title, "doc_type": chunk.doc_type, "score": round(score, 4)}


def _place(index, queries: list[str]) -> list[dict]:
    """Where each query lands on the map, by the same projection as the chunks."""
    if not queries:
        return []
    points = projection_for(index).project(index.embedder.embed(queries))
    return [{"query": q, "x": round(float(x), 4), "y": round(float(y), 4)} for q, (x, y) in zip(queries, points)]


class ModelCheckRequest(BaseModel):
    ids: list[str] = Field(default_factory=list, max_length=50)  # empty: every question


def _unreachable(message: str) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": {"code": "unreachable", "message": message}})


def _ids(csv: str) -> list[str] | None:
    return [x.strip() for x in csv.split(",") if x.strip()] or None


def _not_found(message: str) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": {"code": "not_found", "message": message}})


class FailTools(BaseModel):
    tools: list[str]


def dev_router(deps) -> APIRouter:
    r = APIRouter(prefix="/dev")
    openrouter_list = openrouter_models.ModelList()  # one per app: tests each get a fresh cache

    @r.get("/settings")
    def get_dev_settings():
        return {"settings": deps.state.dev_settings().model_dump(),
                "defaults": deps.state.dev_defaults.model_dump(),
                "openrouter_key": bool(deps.settings.openrouter_api_key)}

    @r.put("/settings")
    def put_dev_settings(body: DevSettings):
        if body.provider == "openrouter" and not deps.settings.openrouter_api_key:
            raise InputError("OpenRouter needs OPENROUTER_API_KEY in backend/.env. Add it and restart the backend.")
        if not local_url_allowed(body.local_url, deps.settings.local_llm_hosts):
            raise InputError(NOT_LOCAL)
        if body.provider == "local" and not body.local_model:
            raise InputError("Choose a local model first: Find models lists the ones the server has.")
        return {"settings": deps.state.save_dev_settings(body).model_dump()}

    @r.post("/fail-tools")
    def fail_tools(body: FailTools):
        """The tool-failure switch (B20, docs/failure-demo.md): these chat tools time out in every answer until the
        server restarts or the list is emptied; Try again still runs them. Starts as FAIL_TOOLS."""
        if unknown := [t for t in body.tools if t not in TOOLS]:
            raise InputError(f"No chat tool called {', '.join(unknown)}. Choose from: {', '.join(TOOLS)}.")
        deps.fail_tools = set(body.tools)
        return {"tools": sorted(deps.fail_tools)}

    @r.get("/info")
    def info():
        chunks = deps.index.chunks
        return {"chunks": len(chunks), "by_doc_type": dict(Counter(c.doc_type for c in chunks).most_common()),
                "embedder": deps.index.embedder_name, "dim": deps.index.dim, "min_score": deps.index.min_score,
                "as_of": deps.as_of, "local_hosts": deps.settings.local_llm_hosts}

    @r.get("/models")
    def models(url: str = ""):
        """The models a local server offers (its OpenAI-compatible /models). The SSRF guard applies: only this
        machine, and redirects are never followed, so a local server can't bounce the request elsewhere."""
        if not local_url_allowed(url, deps.settings.local_llm_hosts):
            raise InputError(NOT_LOCAL)
        client = deps.http_client or httpx.Client(timeout=MODELS_TIMEOUT)
        try:
            res = client.get(url.rstrip("/") + "/models", follow_redirects=False, timeout=MODELS_TIMEOUT)
            res.raise_for_status()
            data = res.json()
        except httpx.TransportError:
            return _unreachable(f"Nothing answered at {url}. Start Ollama, LM Studio's server or llama.cpp, "
                                "then try again.")
        except (httpx.HTTPStatusError, ValueError):
            return _unreachable(f"The server at {url} didn't list its models (OpenAI-compatible /models).")
        finally:
            if client is not deps.http_client:
                client.close()
        items = data.get("data") if isinstance(data, dict) else None
        return {"models": sorted(str(m["id"]) for m in items or [] if isinstance(m, dict) and m.get("id"))}

    @r.get("/openrouter-models")
    def openrouter_model_list():
        """The OpenRouter models this key may use that take tools, for the Dev page's dropdown."""
        client = deps.http_client or httpx.Client()
        try:
            models, reason = openrouter_list.get(client, deps.settings.openrouter_api_key)
        finally:
            if client is not deps.http_client:
                client.close()
        scores = model_check.openrouter_scores(deps)  # read fresh: a run just finished shows at once
        return {"models": [m | {"check": scores.get(m["id"])} for m in models], "reason": reason}

    @r.post("/search")
    def playground(body: SearchRequest):
        """search_security with the saved settings, every step shown: the plan, each retriever's list per query
        (before fusion), the fused ranking and the final sources (after the per-document cap and top-n)."""
        dev = deps.dev()
        res = search_security(body.query, deps.llm, deps.retrievers, deps.knowledge.resolve_product,
                              opts=deps.search_options())
        chunks = {h.chunk.chunk_id: h.chunk for _, _, hits in res.lists for h in hits}
        return {
            "query": res.query.model_dump(),
            "options": dev.model_dump(include={"top_n", "per_query_k", "per_doc_cap", "rrf_k", "keyword_weight",
                                               "use_rewrites", "use_filters"}),
            "lists": [{"retriever": name, "query": q, "hits": [_hit(h.chunk, h.score) for h in hits]}
                      for name, q, hits in res.lists],
            "fused": [{"chunk_id": cid, "title": chunks[cid].title, "doc_type": chunks[cid].doc_type,
                       "rrf": round(score, 5)} for cid, score in res.fused[:FUSED_SHOWN]],
            "final": [s.model_dump() for s in res.sources],
            "map": _place(deps.index, [q for q in dict.fromkeys(q for _, q, _ in res.lists)]),
        }

    @r.get("/map")
    def embedding_map():
        """Every chunk as a point: PCA of the vectors in the Chroma index."""
        proj = projection_for(deps.index)
        return {
            "embedder": deps.index.embedder_name, "dim": deps.index.dim,
            "explained": [round(e, 4) for e in proj.explained],
            "points": [{"id": c.chunk_id, "doc_id": c.doc_id, "title": c.title, "type": c.doc_type,
                        "x": round(float(x), 4), "y": round(float(y), 4)}
                       for c, (x, y) in zip(deps.index.chunks, proj.coords)],
        }

    # --- The model check (A12): exact checks on the scripted questions, in the background, on a copy of the state

    @r.post("/model-check")
    def start_model_check(body: ModelCheckRequest):
        return model_check.start(deps, body.ids or None)

    @r.get("/model-check/{run_id}")
    def get_model_check(run_id: str):
        return model_check.get(deps, run_id) or _not_found("No model check with that id.")

    @r.get("/model-checks")
    def list_model_checks():
        return {"runs": model_check.listing(deps)}

    # --- Retrieval metrics (A12) for the embedder the index was built with; another embedder = another index

    @r.post("/retrieval-check")
    def run_retrieval_check():
        return retrieval.run(deps, deps.index, deps.keyword)

    @r.get("/retrieval-check/{run_id}")
    def get_retrieval_check(run_id: str):
        return retrieval.get(deps, run_id) or _not_found("No retrieval check with that id.")

    @r.get("/retrieval-checks")
    def list_retrieval_checks():
        return {"runs": retrieval.listing(deps)}

    @r.get("/report", response_class=HTMLResponse)
    def evaluation_report(model_ids: str = Query("", alias="models"), retrieval_ids: str = Query("", alias="retrieval")):
        """The report page from saved runs: the ones named (comma-separated ids), else the latest per model and
        per embedder. Findings are written later, for the published copy (python -m app.evals report)."""
        return HTMLResponse(report.from_store(report.store_of(deps.settings), deps.settings.as_of,
                                              _ids(model_ids), _ids(retrieval_ids)))

    return r

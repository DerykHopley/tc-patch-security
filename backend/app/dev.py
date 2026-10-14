"""The dev panel's routes (A11): model switch, local-model discovery, search tuning, the playground, the embedding map.

Mounted only when DEV_PANEL is on (they show internals): off, every /dev route is a 404.
"""
import httpx
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.app_settings import DevSettings
from app.errors import InputError
from app.llm.urls import local_url_allowed

MODELS_TIMEOUT = 5  # seconds: listing models is quick even when loading one is slow
NOT_LOCAL = ("The local model URL must be on this machine, for example http://localhost:11434/v1. "
             "Other hosts need LOCAL_LLM_HOSTS in backend/.env.")


def _unreachable(message: str) -> JSONResponse:
    return JSONResponse(status_code=502, content={"error": {"code": "unreachable", "message": message}})


def dev_router(deps) -> APIRouter:
    r = APIRouter(prefix="/dev")

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

    return r

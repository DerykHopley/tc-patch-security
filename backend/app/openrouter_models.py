"""The OpenRouter models this key may use, for the Dev page's dropdown.

GET /models/user lists only the models the account's guardrail allows, so the dropdown offers the real set of
choices. Only models that take tools are kept: Patch's agent needs them. The key goes to OpenRouter and nowhere else:
never into a reply or a log line.
"""
import logging
import threading
import time

import httpx

from app.llm.providers import OPENROUTER_URL

TIMEOUT = 10  # seconds
CACHE_SECONDS = 3600
log = logging.getLogger(__name__)


def _per_million(price) -> float | None:
    """OpenRouter's price is USD per token as a string; "-1" (or anything odd) means variable: unknown."""
    try:
        value = float(price)
    except (TypeError, ValueError):
        return None
    return None if value < 0 else round(value * 1_000_000, 4)


def _entry(m: dict) -> dict:
    pricing = m.get("pricing") or {}
    return {"id": m["id"], "name": m.get("name") or m["id"], "input_per_m": _per_million(pricing.get("prompt")),
            "output_per_m": _per_million(pricing.get("completion")), "context_length": m.get("context_length")}


def _fetch(client: httpx.Client, key: str) -> list[dict]:
    res = client.get(f"{OPENROUTER_URL}/models/user", headers={"Authorization": f"Bearer {key}"}, timeout=TIMEOUT)
    res.raise_for_status()
    items = res.json().get("data") or []
    models = [_entry(m) for m in items
              if isinstance(m, dict) and m.get("id") and "tools" in (m.get("supported_parameters") or [])]
    return sorted(models, key=lambda m: (m["input_per_m"] is None, m["input_per_m"] or 0, m["id"]))


def fetch(client: httpx.Client, key: str) -> tuple[list[dict], str | None]:
    """The tool-capable models, cheapest input first (unknown prices last), or no models and a plain reason.
    The reasons name the status or the kind of failure only: an exception's text could carry the request."""
    if not key:
        return [], "no OpenRouter key in backend/.env"
    try:
        return _fetch(client, key), None
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        hint = " Check OPENROUTER_API_KEY in backend/.env." if status in (401, 403) else ""
        reason = f"OpenRouter answered {status} when asked for the model list.{hint}"
    except httpx.TransportError as e:
        reason = f"Can't reach OpenRouter ({type(e).__name__})."
    except (ValueError, AttributeError, KeyError, TypeError):
        reason = "OpenRouter's model list didn't look as expected."
    log.warning("OpenRouter model list: %s", reason)
    return [], reason


class ModelList:
    """fetch() with an hour's memory: the list changes rarely and the Dev page asks on every visit. Only a list is
    remembered; after a failure the next visit asks again."""

    def __init__(self):
        self._at: float | None = None
        self._models: list[dict] = []
        self._lock = threading.Lock()

    def get(self, client: httpx.Client, key: str) -> tuple[list[dict], str | None]:
        with self._lock:
            if self._at is not None and time.monotonic() - self._at < CACHE_SECONDS:
                return self._models, None
            models, reason = fetch(client, key)
            if reason is None:
                self._at, self._models = time.monotonic(), models
            return models, reason

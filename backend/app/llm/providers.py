"""Which model answers: FakeLLM, OpenRouter or a local OpenAI-compatible server.

`make_llm` builds the model the env names. `LLMRouter` (A11) picks one on every call from the dev panel's saved
choices, so switching models needs no restart. Local URLs are limited to this machine (the SSRF guard, app.llm.urls).
"""
from collections.abc import Callable

from app.config import Settings
from app.errors import LLMError
from app.llm.base import LLM, LLMReply, QueryPlan
from app.llm.fake import FakeLLM
from app.llm.openai_compat import ChatModelLLM
from app.llm.urls import local_url_allowed

OPENROUTER_URL = "https://openrouter.ai/api/v1"
LOCAL_TIMEOUT = 300  # local models are slow to load the first time
NOT_LOCAL = "The local model URL must be on this machine (localhost)."

__all__ = ["LLMRouter", "local_url_allowed", "make_llm"]


def _openrouter(settings: Settings, model: str, temperature: float, http_client) -> ChatModelLLM:
    if not settings.openrouter_api_key:
        raise LLMError("no OpenRouter key", public="OpenRouter needs OPENROUTER_API_KEY in backend/.env.")
    return ChatModelLLM("openrouter", OPENROUTER_URL, model, api_key=settings.openrouter_api_key,
                        label=f"OpenRouter · {model}", temperature=temperature, max_retries=2,
                        http_client=http_client)


def _local(settings: Settings, url: str, model: str, temperature: float, http_client) -> ChatModelLLM:
    if not local_url_allowed(url, settings.local_llm_hosts):
        raise LLMError("local URL not allowed", public=NOT_LOCAL)
    if not model:
        raise LLMError("no local model", public="Choose a local model on the Dev page first.")
    return ChatModelLLM("local", url, model, label=f"Local · {model}", temperature=temperature,
                        timeout=LOCAL_TIMEOUT, http_client=http_client)


def make_llm(settings: Settings, http_client=None) -> LLM:
    """The model for settings.llm_provider. Builds a client only: no request is made until the first question."""
    if settings.llm_provider == "openrouter":
        return _openrouter(settings, settings.openrouter_model, 0.2, http_client)
    if settings.llm_provider == "local":
        return _local(settings, settings.local_llm_url, settings.local_llm_model, 0.2, http_client)
    return FakeLLM()


class LLMRouter:
    """The LLM seam over the dev panel's choices: `dev()` is read on every call. One client per (provider, URL, model,
    temperature) is kept, so a local server's "no JSON mode" discovery survives between calls."""

    def __init__(self, settings: Settings, dev: Callable, http_client=None):
        self.settings = settings
        self.dev = dev  # () -> DevSettings
        self.http_client = http_client
        self.fake = FakeLLM()
        self._clients: dict[tuple, ChatModelLLM] = {}

    @property
    def name(self) -> str:
        return self.dev().provider

    def current(self) -> LLM:
        d = self.dev()
        if d.provider == "fake":
            return self.fake
        local = d.provider == "local"
        key = (d.provider, d.local_url if local else "", d.local_model if local else d.openrouter_model, d.temperature)
        if key not in self._clients:
            self._clients[key] = (_local(self.settings, d.local_url, d.local_model, d.temperature, self.http_client)
                                  if local else
                                  _openrouter(self.settings, d.openrouter_model, d.temperature, self.http_client))
        return self._clients[key]

    def label(self) -> str:
        d = self.dev()
        return {"fake": self.fake.label(), "openrouter": f"OpenRouter · {d.openrouter_model}",
                "local": f"Local · {d.local_model or 'no model chosen'}"}[d.provider]

    def translate(self, question: str) -> tuple[QueryPlan, LLMReply]:
        return self.current().translate(question)

    def step(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        return self.current().step(messages, tools)

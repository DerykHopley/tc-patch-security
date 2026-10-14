"""Which model answers: FakeLLM, OpenRouter or a local OpenAI-compatible server, from the settings.

Local URLs are limited to this machine (the SSRF guard, app.llm.urls).
"""
from app.config import Settings
from app.errors import LLMError
from app.llm.base import LLM
from app.llm.fake import FakeLLM
from app.llm.openai_compat import ChatModelLLM
from app.llm.urls import local_url_allowed

OPENROUTER_URL = "https://openrouter.ai/api/v1"
LOCAL_TIMEOUT = 300  # local models are slow to load the first time

__all__ = ["local_url_allowed", "make_llm"]


def make_llm(settings: Settings, http_client=None) -> LLM:
    """The model for settings.llm_provider. Builds a client only: no request is made until the first question."""
    if settings.llm_provider == "openrouter":
        return ChatModelLLM("openrouter", OPENROUTER_URL, settings.openrouter_model, api_key=settings.openrouter_api_key,
                            label=f"OpenRouter · {settings.openrouter_model}", max_retries=2, http_client=http_client)
    if settings.llm_provider == "local":
        if not local_url_allowed(settings.local_llm_url, settings.local_llm_hosts):
            raise LLMError("local URL not allowed", public="The local model URL must be on this machine (localhost).")
        return ChatModelLLM("local", settings.local_llm_url, settings.local_llm_model,
                            label=f"Local · {settings.local_llm_model}", timeout=LOCAL_TIMEOUT, http_client=http_client)
    return FakeLLM()

"""LLMRouter: picks FakeLLM, OpenRouter or a local model on every call, from the dev panel's settings (M1).

So switching models needs no restart, and the eval can run the same questions against each.
"""
from urllib.parse import urlsplit

from app.errors import LLMError
from app.llm.fake import FakeLLM
from app.llm.openai_compat import OpenAICompatLLM
from app.llm.openrouter import OpenRouterLLM


def local_url_allowed(url: str, hosts: list[str]) -> bool:
    """Only loopback (and LOCAL_LLM_HOSTS): a model URL set from the UI must not reach other machines (SSRF)."""
    try:
        parts = urlsplit(url)
    except ValueError:
        return False
    return parts.scheme in ("http", "https") and not parts.username and parts.hostname in hosts


class LLMRouter:
    def __init__(self, settings, dev):
        self.settings = settings
        self.dev = dev  # () -> DevSettings
        self.fake = FakeLLM()
        self._clients: dict[tuple, OpenAICompatLLM] = {}

    @property
    def name(self) -> str:
        return self.dev().provider

    def current(self):
        d = self.dev()
        if d.provider == "fake":
            return self.fake
        if d.provider == "openrouter":
            if not self.settings.openrouter_api_key:
                raise LLMError("no OpenRouter key", public="OpenRouter needs OPENROUTER_API_KEY in backend/.env.")
            key = ("openrouter",)
            if key not in self._clients:
                self._clients[key] = OpenRouterLLM(self.settings.openrouter_api_key, d.model, options=self.dev)
            return self._clients[key]
        if not local_url_allowed(d.local_base_url, self.settings.local_llm_hosts):
            raise LLMError("local URL not allowed", public="The local model URL must be on this machine (localhost).")
        key = ("local", d.local_base_url)
        if key not in self._clients:
            # Local models are slow to load the first time: a long timeout.
            self._clients[key] = OpenAICompatLLM("local", d.local_base_url, "local",
                                                 lambda: (self.dev().local_model, self.dev().temperature), timeout=300)
        return self._clients[key]

    def label(self) -> str:
        d = self.dev()
        return {"fake": "FakeLLM (scripted)", "openrouter": f"OpenRouter · {d.model}",
                "local": f"Local · {d.local_model or 'no model'}"}[d.provider]

    def translate(self, question):
        return self.current().translate(question)

    def step(self, messages, tools):
        return self.current().step(messages, tools)

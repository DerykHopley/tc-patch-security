"""OpenRouterLLM: the shared OpenAI-compatible client pointed at OpenRouter (L2). Checked by hand only."""
from app.llm.openai_compat import OpenAICompatLLM

OPENROUTER_URL = "https://openrouter.ai/api/v1"


class OpenRouterLLM(OpenAICompatLLM):
    def __init__(self, api_key: str, model: str, options=None, http_client=None):
        # options() returns the dev settings; without it, the .env model at temperature 0.2.
        opts = (lambda: (options().model, options().temperature)) if options else (lambda: (model, 0.2))
        super().__init__("openrouter", OPENROUTER_URL, api_key, opts, timeout=60, http_client=http_client)

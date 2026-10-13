"""One client for every OpenAI-compatible chat API: OpenRouter, and local servers (Ollama, LM Studio,
llama.cpp). Not in the automated suite against a real server; tests use a fake HTTP transport.

Local models differ from hosted ones in ways this handles:
- Some servers reject `response_format: json_object` → retry without it and pull the JSON out of the text.
- Reasoning models (Qwen3, DeepSeek-R1) put <think>…</think> before the answer → strip it.
- They are slow on first load → a longer timeout, and a plain message when the server isn't running.
"""
import json
import re

import openai

from app import guard
from app.errors import LLMError
from app.llm.base import LLMReply, QueryPlan, ToolCall

TRANSLATE_PROMPT = f"""You turn a question about LLM and application security into a search plan. Reply with JSON only:
{{"semantic_query": "...", "rewrites": ["...", "...", "..."], "filters": {{}}}}
- semantic_query: the topic of the question, without product names, severities or dates.
- rewrites: 3 different phrasings, using words a security advisory, OWASP page or MITRE ATLAS entry would use.
- filters (all optional; only set one the question clearly asks for):
  "doc_type": one of {guard.DOC_TYPES}
  "product": an LLM product name, e.g. LangChain, Langflow, Ollama, vLLM, Open WebUI
  "severity_min": LOW, MEDIUM, HIGH or CRITICAL ("this or worse")
  "owasp": one of {guard.OWASP_CODES}
  "kev": "true" for vulnerabilities known to be exploited in the wild
  "date_from", "date_to": YYYY-MM-DD"""

THINK = re.compile(r"<think>.*?</think>\s*", re.DOTALL)


def strip_think(text: str | None) -> str | None:
    return THINK.sub("", text).strip() if text else text


def first_json_object(text: str) -> dict:
    """The first {...} in the text: models sometimes wrap JSON in prose or code fences."""
    start = text.find("{")
    while start != -1:
        depth = 0
        for i, ch in enumerate(text[start:], start):
            depth += ch == "{"
            depth -= ch == "}"
            if depth == 0:
                try:
                    return json.loads(text[start:i + 1])
                except json.JSONDecodeError:
                    break
        start = text.find("{", start + 1)
    raise ValueError("no JSON object found")


class OpenAICompatLLM:
    def __init__(self, name: str, base_url: str, api_key: str, options, timeout: float = 60, http_client=None):
        """options() → (model, temperature), read on every call so dev panel changes apply at once."""
        self.name = name
        self.base_url = base_url
        self.options = options
        self.json_mode = True  # turned off for good after a server rejects it
        self.client = openai.OpenAI(api_key=api_key or "none", base_url=base_url, timeout=timeout,
                                    max_retries=0, http_client=http_client)

    def _create(self, **kwargs):
        model, temperature = self.options()
        if not model:
            raise LLMError("no model set", public=f"Choose a {self.name} model in the dev panel first.")
        try:
            return self.client.chat.completions.create(model=model, temperature=temperature, **kwargs)
        except openai.APIConnectionError as e:
            raise LLMError(f"{self.name} unreachable: {e}",
                           public=f"Can't reach the {self.name} model server at {self.base_url}. Is it running?") from e
        except openai.NotFoundError as e:
            raise LLMError(f"{self.name} model not found: {e}",
                           public=f"The {self.name} server doesn't have the model {model!r}. Load or pull it first.") from e
        except openai.OpenAIError as e:
            raise LLMError(f"{self.name} request failed: {type(e).__name__}: {e}") from e

    @staticmethod
    def _usage(resp) -> tuple[int, int]:
        u = getattr(resp, "usage", None)
        return (u.prompt_tokens or 0, u.completion_tokens or 0) if u else (0, 0)

    def translate(self, question: str) -> tuple[QueryPlan, LLMReply]:
        messages = [{"role": "system", "content": TRANSLATE_PROMPT}, {"role": "user", "content": question}]
        resp = None
        if self.json_mode:
            try:
                resp = self._create(messages=messages, response_format={"type": "json_object"})
            except LLMError as e:
                if "BadRequestError" not in e.message:
                    raise
                self.json_mode = False  # this server doesn't support JSON mode; ask in plain text from now on
        if resp is None:
            resp = self._create(messages=messages)
        raw = strip_think(resp.choices[0].message.content) or ""
        try:
            data = first_json_object(raw)
            plan = QueryPlan(
                semantic_query=str(data.get("semantic_query") or question),
                rewrites=[str(r) for r in (data.get("rewrites") or [])][:3],
                filters={k: str(v) for k, v in (data.get("filters") or {}).items() if v},
            )
        except (ValueError, AttributeError, TypeError):
            # A bad plan shouldn't fail the chat: fall back to searching the question as is.
            plan = QueryPlan(semantic_query=question)
        n_in, n_out = self._usage(resp)
        return plan, LLMReply(input_tokens=n_in, output_tokens=n_out)

    def step(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        resp = self._create(messages=messages, tools=tools)
        msg = resp.choices[0].message
        calls = []
        for tc in msg.tool_calls or []:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {"_unparsed": tc.function.arguments}  # run_tool turns this into a bad_arguments error
            calls.append(ToolCall(id=tc.id or f"call_{len(calls)}", name=tc.function.name,
                                  args=args if isinstance(args, dict) else {}))
        n_in, n_out = self._usage(resp)
        return LLMReply(content=strip_think(msg.content), tool_calls=calls, input_tokens=n_in, output_tokens=n_out)

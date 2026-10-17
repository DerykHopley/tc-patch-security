"""The real model: LangChain's ChatOpenAI behind our LLM seam (docs/adr/0001-thin-langchain.md).

One class for every OpenAI-compatible chat API: OpenRouter, and local servers (Ollama, LM Studio, llama.cpp).
LangChain is the client only: tools are declared with bind_tools, but the agent loop, the tool registry and
argument validation stay ours (app.agent, app.tools.registry).

Ported from proto's OpenAICompatLLM. Local models differ from hosted ones in ways this handles:
- Some servers reject `response_format: json_object` → retry without it and pull the JSON out of the text.
- Reasoning models (Qwen3, DeepSeek-R1) put <think>…</think> before the answer → strip it.
- They are slow on first load → a longer timeout, and "Is it running?" when the server can't be reached.

Cost: OpenRouter adds `usage.cost` (USD) to every response; other servers don't, so they cost 0.
"""
import json
import re

import openai
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

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


def to_langchain(messages: list[dict]) -> list[BaseMessage]:
    """Our agent loop's OpenAI-format dicts → LangChain messages. ChatOpenAI turns them back into the same JSON."""
    out: list[BaseMessage] = []
    for m in messages:
        role, content = m["role"], m.get("content") or ""
        if role == "system":
            out.append(SystemMessage(content))
        elif role == "user":
            out.append(HumanMessage(content))
        elif role == "assistant":
            calls = [{"id": tc["id"], "name": tc["function"]["name"],
                      "args": json.loads(tc["function"]["arguments"] or "{}")} for tc in m.get("tool_calls") or []]
            out.append(AIMessage(content, tool_calls=calls))
        elif role == "tool":
            out.append(ToolMessage(content, tool_call_id=m["tool_call_id"]))
        else:
            raise ValueError(f"unknown message role {role!r}")
    return out


def _text(msg: AIMessage) -> str:
    return msg.content if isinstance(msg.content, str) else msg.text


def _reason(e: openai.APIStatusError) -> str:
    """The server's own error message, on one line (OpenRouter's 404s explain which rule removed the model)."""
    body = e.body if isinstance(e.body, dict) else {}
    msg = body.get("message") or (body.get("error") or {}).get("message") or str(e)
    return " ".join(str(msg).split())


class ChatModelLLM:
    """The LLM protocol on ChatOpenAI. `name` is the provider: "openrouter" or "local"."""

    def __init__(self, name: str, base_url: str, model: str, api_key: str = "", label: str = "",
                 temperature: float = 0.2, timeout: float = 60, max_retries: int = 0, http_client=None):
        self.name = name
        self.base_url = base_url
        self.model = model
        self._label = label or f"{name} · {model}"
        self.json_mode = True  # turned off for good after a server rejects it
        self.chat = ChatOpenAI(model=model, base_url=base_url, api_key=api_key or "none", temperature=temperature,
                               timeout=timeout, max_retries=max_retries, http_client=http_client)

    def label(self) -> str:
        return self._label

    def _invoke(self, runnable, messages: list[BaseMessage]) -> AIMessage:
        try:
            msg = runnable.invoke(messages)
        except openai.APIConnectionError as e:  # includes timeouts
            raise LLMError(f"{self.name} unreachable: {e}",
                           public=f"Can't reach the {self.name} model server at {self.base_url}. Is it running?") from e
        except openai.NotFoundError as e:
            if self.name == "openrouter":  # 404 there = no provider may serve it (guardrail, data policy): say why
                raise LLMError(f"{self.name} model not served: {e}",
                               public=f"OpenRouter can't serve the model {self.model!r}: {_reason(e)} "
                                      "Check the model and your OpenRouter workspace settings.") from e
            raise LLMError(f"{self.name} model not found: {e}",
                           public=f"The {self.name} server doesn't have the model {self.model!r}. "
                                  "Load or pull it first.") from e
        except openai.AuthenticationError as e:
            raise LLMError(f"{self.name} rejected the key: {e}",
                           public=f"The {self.name} server rejected the API key. Check it in backend/.env.") from e
        except openai.APIStatusError as e:
            if e.status_code == 402:  # OpenRouter: the key's spending cap is reached, or no credits left
                raise LLMError(f"{self.name} payment required: {e}",
                               public=LLMError.SPENDING_CAP, code="spending_cap") from e
            raise LLMError(f"{self.name} request failed: {type(e).__name__}: {e}") from e
        except openai.OpenAIError as e:
            raise LLMError(f"{self.name} request failed: {type(e).__name__}: {e}") from e
        assert isinstance(msg, AIMessage)
        return msg

    @staticmethod
    def _usage(msg: AIMessage) -> dict:
        u = msg.usage_metadata or {}
        raw = msg.response_metadata.get("token_usage") or {}
        cost = raw.get("cost") if isinstance(raw, dict) else None
        return {"input_tokens": u.get("input_tokens", 0), "output_tokens": u.get("output_tokens", 0),
                "cost": float(cost) if isinstance(cost, (int, float)) else 0.0}

    def translate(self, question: str) -> tuple[QueryPlan, LLMReply]:
        messages = [SystemMessage(TRANSLATE_PROMPT), HumanMessage(question)]
        msg = None
        if self.json_mode:
            try:
                msg = self._invoke(self.chat.bind(response_format={"type": "json_object"}), messages)
            except LLMError as e:
                if not isinstance(e.__cause__, openai.BadRequestError):
                    raise
                self.json_mode = False  # this server doesn't support JSON mode; ask in plain text from now on
        if msg is None:
            msg = self._invoke(self.chat, messages)
        raw = strip_think(_text(msg)) or ""
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
        return plan, LLMReply(**self._usage(msg))

    def step(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        msg = self._invoke(self.chat.bind_tools(tools), to_langchain(messages))
        calls = [ToolCall(id=tc.get("id") or f"call_{i}", name=tc["name"], args=tc["args"])
                 for i, tc in enumerate(msg.tool_calls)]
        # Arguments that aren't valid JSON: still run, so run_tool reports bad_arguments to the model.
        calls += [ToolCall(id=tc.get("id") or f"bad_{i}", name=tc.get("name") or "", args={})
                  for i, tc in enumerate(msg.invalid_tool_calls)]
        return LLMReply(content=strip_think(_text(msg)), tool_calls=calls, **self._usage(msg))

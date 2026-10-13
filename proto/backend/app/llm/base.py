"""The LLM seam. FakeLLM and OpenRouterLLM both implement this protocol."""
from typing import Protocol

from pydantic import BaseModel, Field

from app.errors import LLMError  # noqa: F401  (re-exported: llm.LLMError)


class QueryPlan(BaseModel):
    semantic_query: str
    rewrites: list[str] = Field(default_factory=list)  # 3 from a real or scripted LLM
    filters: dict[str, str] = Field(default_factory=dict)  # source, topic, date_from, date_to; unvalidated


class ToolCall(BaseModel):
    id: str
    name: str
    args: dict


class LLMReply(BaseModel):
    content: str | None = None  # final answer when tool_calls is empty
    tool_calls: list[ToolCall] = Field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    estimated: bool = False


class LLM(Protocol):
    name: str

    def translate(self, question: str) -> tuple[QueryPlan, LLMReply]:
        """Multi-query rewrites and self-query filters in one call."""

    def step(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        """One agent step: tool calls, or a final answer. OpenAI chat format."""

"""The model seam. FakeLLM implements it now; the real model behind LangChain comes in A08
(docs/adr/0001-thin-langchain.md). Moved from proto, plus label() from the skeleton.
"""
from typing import Protocol

from pydantic import BaseModel, Field


class QueryPlan(BaseModel):
    semantic_query: str
    rewrites: list[str] = Field(default_factory=list)  # 3 from a real or scripted LLM
    filters: dict[str, str] = Field(default_factory=dict)  # unvalidated: guard.validate_filters checks them


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
    name: str  # provider id: "fake", later "openrouter", "local"

    def label(self) -> str:
        """The model in use, as shown to the user."""
        ...

    def translate(self, question: str) -> tuple[QueryPlan, LLMReply]:
        """Multi-query rewrites and self-query filters in one call."""
        ...

    def step(self, messages: list[dict], tools: list[dict]) -> LLMReply:
        """One agent step: tool calls, or a final answer. OpenAI chat format."""
        ...

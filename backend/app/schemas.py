"""Chat request and reply shapes. Moved from proto (A06); other routes add their own shapes."""
from typing import Literal

from pydantic import BaseModel, Field


class Turn(BaseModel):
    role: str  # checked in guard.check_message, so the error message is plain (V1)
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Turn] = Field(default_factory=list)


class Source(BaseModel):
    n: int
    chunk_id: str
    doc_id: str
    doc_type: str
    title: str
    section: str | None = None
    date: str | None = None
    url: str
    snippet: str
    score: float | None = None  # similarity; None for a source added by lookup_cve
    # CVE only
    product: str | None = None
    severity: str | None = None
    cvss: float | None = None
    kev: bool | None = None


class QueryInfo(BaseModel):
    original: str
    semantic_query: str
    rewrites: list[str]
    filters: dict[str, str]
    dropped_filters: list[str]
    relaxed: bool


class ToolCallRecord(BaseModel):
    id: str
    name: str
    args: dict
    status: Literal["ok", "error"]
    result: dict | None = None
    error: dict | None = None  # {code, message}
    duration_ms: float


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    estimated: bool = False


class ChatReply(BaseModel):
    answer: str
    sources: list[Source]
    tool_calls: list[ToolCallRecord]
    query: QueryInfo | None
    usage: Usage
    steps: int
    flags: list[str] = Field(default_factory=list)  # "injection_phrasing": flagged, still answered

"""Chat request and reply shapes. Moved from proto (A06); other routes add their own shapes."""
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.app_settings import ExplainLevel


# A CVE id as tools and buttons take it: any case in, upper case out (CVE-2025-3248). One definition, so every tool
# argument and the card actions accept the same ids.
CveId = Annotated[str, StringConstraints(strip_whitespace=True, to_upper=True, pattern=r"(?i)^CVE-\d{4}-\d{4,}$")]


class Turn(BaseModel):
    role: str  # checked in guard.check_message, so the error message is plain (V1)
    content: str


class ChatRequest(BaseModel):
    message: str
    history: list[Turn] = Field(default_factory=list)
    explain_level: ExplainLevel | None = None  # this message only; none = the saved level (A19)
    # What the user is looking at (A18): fixed fields only, each checked by app.page_context; the rest is dropped
    page: dict[str, Any] | None = None


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
    score: float | None = None  # fused RRF score (A10); None for a source added by lookup_cve
    # CVE only
    product: str | None = None
    severity: str | None = None
    cvss: float | None = None
    kev: bool | None = None
    # Web only (B08): the page's site, and "injection_phrasing" when its text tries to give instructions
    site: str | None = None
    flags: list[str] = Field(default_factory=list)


class QueryInfo(BaseModel):
    original: str
    semantic_query: str
    rewrites: list[str]
    filters: dict[str, str]
    dropped_filters: list[str]
    relaxed: bool
    found_by: dict[int, list[str]] = Field(default_factory=dict)  # source n → ["keyword", "vector"] (A10)


class ToolCallRecord(BaseModel):
    id: str
    name: str
    args: dict
    status: Literal["ok", "error"]
    result: dict | None = None
    error: dict | None = None  # {code, message}
    duration_ms: float
    retryable: bool = False  # B20: an error that may pass on a second try (a timeout, a rate limit): "Try again"


class Usage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    llm_calls: int = 0
    estimated: bool = False
    cost: float = 0.0  # USD, summed over the answer's LLM calls (OpenRouter's usage.cost); 0 for local and FakeLLM


class ChatReply(BaseModel):
    answer: str
    sources: list[Source]
    tool_calls: list[ToolCallRecord]
    query: QueryInfo | None
    usage: Usage
    steps: int
    flags: list[str] = Field(default_factory=list)  # "injection_phrasing": flagged, still answered
    bad_citations: list[int] = Field(default_factory=list)  # [n] removed from the answer: no source n (A08)
    no_citations: bool = False  # the answer has sources but cites none of them: shown as a quiet note
    explain_level: ExplainLevel = "normal"  # the level this answer was pitched at (A19)
    page_context: dict[str, Any] = Field(default_factory=dict)  # the checked page context Patch had (A18)
    dropped_context: list[str] = Field(default_factory=list)  # page-context values dropped: "key=value"

"""API request and reply shapes (A1, A2)."""
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
    # CVE only (A2)
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
    flags: list[str] = Field(default_factory=list)  # V2


class StatusUpdate(BaseModel):
    status: str


class WatchlistUpdate(BaseModel):
    products: list[str]


# --- Settings (G1–G4) and dev panel (X1–X4)

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class AlertSettings(BaseModel):
    """Saved now; the refresh worker in ALERTS-PLAN.md will read them."""
    enabled: bool = True
    min_severity: Severity = "HIGH"
    kev: bool = True
    kev_recheck: bool = True
    unscored: bool = True
    now_critical: bool = True
    digest_over: int = Field(5, ge=1, le=50)
    schedule_hours: Literal[1, 3, 6, 12, 24] = 6
    quiet_start: str | None = Field(None, pattern=HHMM)
    quiet_end: str | None = Field(None, pattern=HHMM)
    channels: list[Literal["ntfy", "email", "desktop"]] = Field(default_factory=lambda: ["desktop"])  # N1


class DevSettings(BaseModel):
    """Live: the agent, search_security and the LLM router read these on every request."""
    provider: Literal["fake", "openrouter", "local"] = "fake"  # M1
    model: str = Field("openai/gpt-4o-mini", min_length=3, max_length=100, pattern=r"^[\w.\-]+/[\w.:\-]+$")
    local_base_url: str = Field("http://localhost:11434/v1", max_length=200, pattern=r"^https?://[^\s]+$")
    local_model: str = Field("", max_length=200, pattern=r"^[\w.:/@\-]*$")
    temperature: float = Field(0.2, ge=0, le=2)
    max_steps: int = Field(4, ge=1, le=8)
    top_n: int = Field(5, ge=1, le=10)
    per_query_k: int = Field(10, ge=1, le=30)
    per_doc_cap: int = Field(2, ge=1, le=5)
    rrf_k: int = Field(60, ge=1, le=200)
    use_rewrites: bool = True
    use_filters: bool = True


class AppSettings(BaseModel):
    alerts: AlertSettings = Field(default_factory=AlertSettings)
    dev: DevSettings = Field(default_factory=DevSettings)


class ResetRequest(BaseModel):
    confirm: Literal["reset"]


class TestAlertRequest(BaseModel):
    channel: Literal["ntfy", "email", "desktop", "preview"] = "preview"


class DevSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)

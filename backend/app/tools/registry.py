"""Tool specs, their JSON schemas for the LLM, and run_tool(): validate → run → check the result → time → record
(T5, T6).

Each tool declares its result's shape (architecture review, candidate 6): a ToolResult model, or a union of them.
run_tool checks every result against it, so a drifting shape is a tool_failed record, never a silently wrong FakeLLM
template or an empty card. The frontend's types (frontend/src/toolResults.ts) are written from the same models.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from app.config import DEFAULT_USER
from app.errors import LLMError, ToolError
from app.llm.base import LLMReply, ToolCall
from app.schemas import QueryInfo, Source, ToolCallRecord, Usage

log = logging.getLogger(__name__)


@dataclass
class Context:
    """Per-request state the tools add to: sources across search calls, the last query, usage. `page`: the checked
    page context (A18), read by prioritise. `user_id`: whose request it is (B09: the auth dependency's, through
    Deps.user_id; the default user while sign-in is off). research_web counts its daily cap by it (B08), and
    check_updates picks the user's alerts by it (B06)."""
    sources: list[Source] = field(default_factory=list)
    query: QueryInfo | None = None
    usage: Usage = field(default_factory=Usage)
    page: dict = field(default_factory=dict)
    user_id: str = DEFAULT_USER
    force_filters: dict = field(default_factory=dict)  # B24: a refine button's search filters, never relaxed away

    def add_usage(self, reply: LLMReply) -> None:
        self.usage.input_tokens += reply.input_tokens
        self.usage.output_tokens += reply.output_tokens
        self.usage.llm_calls += 1
        self.usage.cost += reply.cost
        self.usage.estimated = self.usage.estimated or reply.estimated


class ToolResult(BaseModel):
    """A tool result's declared shape: every key it has, and nothing else."""
    model_config = ConfigDict(extra="forbid")


# Values several tools' results share. Severity "NONE": NVD scored the CVE with nothing to score; None: not scored.
Severity = Literal["CRITICAL", "HIGH", "MEDIUM", "LOW", "NONE"]
Verdict = Literal["affected", "not_affected", "unknown"]
WhoActs = Literal["you", "upstream", "vendor"]
WatchStatus = Literal["open", "fixed", "not_affected", "accepted", "not_watched"]
PriorityLevel = Literal["urgent", "high", "normal", "low"]


class Category(ToolResult):
    """An OWASP Top 10 category."""
    code: str
    title: str
    url: str


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    result: Any  # a ToolResult model, or a union of them (Annotated with a discriminator where there is one)
    run: Callable  # (args, deps, ctx) -> dict, in the shape of `result`
    offered: Callable = lambda deps: True  # (deps) -> bool: an off tool isn't offered to the model, nor run (B08)

    def __post_init__(self):
        self.results = TypeAdapter(self.result)

    def check(self, result: dict) -> dict:
        """The result as is, once it matches the declared shape. Raises ValidationError if it doesn't."""
        self.results.validate_python(result)
        return result

    def schema(self) -> dict:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": params}}


TOOLS: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    TOOLS[spec.name] = spec
    return spec


def tool_schemas(deps=None) -> list[dict]:
    """The tools offered to the model. Without deps, every tool."""
    return [t.schema() for t in TOOLS.values() if deps is None or t.offered(deps)]


# Errors that may pass on a second try (B20): the tool card offers "Try again" for these only. A bad argument or an
# unknown id gives the same error every time.
RETRYABLE = {"timeout", "rate_limited", "tool_failed", "unavailable", "web_unavailable"}
# Steps that stopped short without a mistake in the call: the answer must say so. The web research cap is one, but
# not retryable: it counts per day.
UNFINISHED = RETRYABLE | {"web_limit"}


def failed_on_purpose(call: ToolCall) -> ToolCallRecord:
    """The tool-failure switch (FAIL_TOOLS, the dev panel; B20): the step times out without running the tool."""
    return ToolCallRecord(id=call.id, name=call.name, args=call.args, status="error", duration_ms=0.0, retryable=True,
                          error={"code": "timeout", "message": f"{call.name} timed out before it answered."})


def _plain(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'arguments'}: {err['msg']}" for err in e.errors())


def run_tool(call: ToolCall, deps, ctx: Context, tools: dict[str, ToolSpec] | None = None) -> ToolCallRecord:
    """`tools`: the specs to run from; the chat's TOOLS by default (the MCP server passes its own, B23)."""
    start = time.perf_counter()

    def record(status, result=None, error=None):
        ms = round((time.perf_counter() - start) * 1000, 2)
        return ToolCallRecord(id=call.id, name=call.name, args=call.args, status=status,
                              result=result, error=error, duration_ms=ms,
                              retryable=bool(error) and error["code"] in RETRYABLE)

    spec = (TOOLS if tools is None else tools).get(call.name)
    if spec is None:
        return record("error", error={"code": "unknown_tool", "message": f"There is no tool called {call.name!r}."})
    if not spec.offered(deps):  # a model may name a tool it wasn't offered
        return record("error", error={"code": "tool_off", "message": f"The {call.name} tool is off."})
    try:
        args = spec.args_model.model_validate(call.args)
    except ValidationError as e:
        return record("error", error={"code": "bad_arguments", "message": _plain(e)})
    try:
        result = spec.run(args, deps, ctx)
    except ToolError as e:
        return record("error", error={"code": e.code, "message": e.message})
    except LLMError:
        raise  # search_security calls the LLM; its failure is an HTTP 502, not a tool error (V6)
    except Exception:
        log.exception("tool %s failed", call.name)
        return record("error", error={"code": "tool_failed", "message": f"The {call.name} tool failed unexpectedly."})
    try:
        return record("ok", result=spec.check(result))
    except ValidationError as e:  # the tool's code drifted from its declared result: a bug, not the model's mistake
        log.error("tool %s returned a result that doesn't match its declared shape: %s", call.name, e)
        return record("error", error={"code": "tool_failed", "message": f"The {call.name} tool failed unexpectedly."})


# Importing the tool modules registers them.
from app.tools import affected, cve, decision, prioritise, search, updates, watchlist, weakness, web  # noqa: E402,F401

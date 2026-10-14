"""Tool specs, their JSON schemas for the LLM, and run_tool(): validate → run → time → record (T5, T6)."""
import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from pydantic import BaseModel, ValidationError

from app.errors import LLMError, ToolError
from app.llm.base import LLMReply, ToolCall
from app.schemas import QueryInfo, Source, ToolCallRecord, Usage

log = logging.getLogger(__name__)


@dataclass
class Context:
    """Per-request state the tools add to: sources across search calls, the last query, usage. `page`: the checked
    page context (A18), read by prioritise."""
    sources: list[Source] = field(default_factory=list)
    query: QueryInfo | None = None
    usage: Usage = field(default_factory=Usage)
    page: dict = field(default_factory=dict)

    def add_usage(self, reply: LLMReply) -> None:
        self.usage.input_tokens += reply.input_tokens
        self.usage.output_tokens += reply.output_tokens
        self.usage.llm_calls += 1
        self.usage.cost += reply.cost
        self.usage.estimated = self.usage.estimated or reply.estimated


@dataclass
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    run: Callable  # (args, deps, ctx) -> dict

    def schema(self) -> dict:
        params = self.args_model.model_json_schema()
        params.pop("title", None)
        return {"type": "function", "function": {"name": self.name, "description": self.description, "parameters": params}}


TOOLS: dict[str, ToolSpec] = {}


def register(spec: ToolSpec) -> ToolSpec:
    TOOLS[spec.name] = spec
    return spec


def tool_schemas() -> list[dict]:
    return [t.schema() for t in TOOLS.values()]


def _plain(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'arguments'}: {err['msg']}" for err in e.errors())


def run_tool(call: ToolCall, deps, ctx: Context) -> ToolCallRecord:
    start = time.perf_counter()

    def record(status, result=None, error=None):
        ms = round((time.perf_counter() - start) * 1000, 2)
        return ToolCallRecord(id=call.id, name=call.name, args=call.args, status=status,
                              result=result, error=error, duration_ms=ms)

    spec = TOOLS.get(call.name)
    if spec is None:
        return record("error", error={"code": "unknown_tool", "message": f"There is no tool called {call.name!r}."})
    try:
        args = spec.args_model.model_validate(call.args)
    except ValidationError as e:
        return record("error", error={"code": "bad_arguments", "message": _plain(e)})
    try:
        return record("ok", result=spec.run(args, deps, ctx))
    except ToolError as e:
        return record("error", error={"code": e.code, "message": e.message})
    except LLMError:
        raise  # search_security calls the LLM; its failure is an HTTP 502, not a tool error (V6)
    except Exception:
        log.exception("tool %s failed", call.name)
        return record("error", error={"code": "tool_failed", "message": f"The {call.name} tool failed unexpectedly."})


# Importing the tool modules registers them.
from app.tools import affected, cve, prioritise, search, watchlist, weakness  # noqa: E402,F401

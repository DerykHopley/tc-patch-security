"""Declared tool result shapes (architecture review, candidate 6): every tool's result is checked against its model."""
import pytest
from pydantic import BaseModel

from app.llm.base import ToolCall
from app.tools import registry
from app.tools.registry import TOOLS, Context, ToolResult, ToolSpec, run_tool


class NoArgs(BaseModel):
    pass


class Shape(ToolResult):
    message: str
    count: int


@pytest.fixture
def drifting_tool():
    """A tool whose result doesn't match its declared model: `returns` sets what it returns."""
    spec = ToolSpec(name="drifting", description="test", args_model=NoArgs, result=Shape,
                    run=lambda args, deps, ctx: spec.returns)
    registry.register(spec)
    yield spec
    del TOOLS["drifting"]


def run(spec, returns):
    spec.returns = returns
    return run_tool(ToolCall(id="t", name=spec.name, args={}), None, Context())


def test_a_result_that_matches_its_model_is_returned_as_is(drifting_tool):
    rec = run(drifting_tool, {"message": "hi", "count": 2})
    assert rec.status == "ok" and rec.result == {"message": "hi", "count": 2}


@pytest.mark.parametrize("returns", [
    {"message": "hi"},  # a key went missing
    {"message": "hi", "count": 2, "extra": True},  # a key nobody declared
    {"message": "hi", "count": "two"},  # a value of the wrong type
])
def test_a_drifting_result_shape_is_a_tool_failure(drifting_tool, returns):
    rec = run(drifting_tool, returns)
    assert rec.status == "error" and rec.result is None
    assert rec.error["code"] == "tool_failed"


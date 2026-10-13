from app.agent import answer
from app.llm.base import LLMReply, ToolCall
from app.llm.fake import FakeLLM


class LoopingLLM(FakeLLM):
    """Always asks for another tool call: the agent must stop it (T7)."""

    def step(self, messages, tools):
        return LLMReply(tool_calls=[ToolCall(id="x", name="lookup_cve", args={"cve_id": "CVE-2024-8309"})],
                        input_tokens=10, output_tokens=5, estimated=True)


def test_t7_loop_stops_after_max_steps(deps):
    deps.llm = LoopingLLM()
    reply = answer("look it up forever", [], deps)
    assert reply.steps == 4 and len(reply.tool_calls) == 4
    assert "stopped after 4 steps" in reply.answer


def test_t6_every_tool_call_recorded(deps):
    reply = answer("Explain CVE-2024-8309 and how to prevent that kind of bug", [], deps)
    assert [t.name for t in reply.tool_calls] == ["lookup_cve", "search_security"]
    for t in reply.tool_calls:
        assert t.status == "ok" and t.result and t.duration_ms >= 0 and t.args


def test_r7_citations_match_sources(deps):
    reply = answer("Explain CVE-2024-8309 and how to prevent that kind of bug", [], deps)
    ns = {s.n for s in reply.sources}
    import re
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", reply.answer)}
    assert cited and cited <= ns
    assert [s.n for s in reply.sources] == list(range(1, len(reply.sources) + 1))


def test_unscripted_cve_question_looks_up_then_searches(deps):
    reply = answer("Explain CVE-2025-3248 and how to defend against it.", [], deps)
    assert [t.name for t in reply.tool_calls] == ["lookup_cve", "search_security"]
    assert reply.tool_calls[1].args["query"] == "How to prevent Injection"
    assert "Exploited in the wild" in reply.answer


def test_unscripted_weakness_question(deps):
    reply = answer("Tell me about CWE-79", [], deps)
    assert [t.name for t in reply.tool_calls] == ["explain_weakness"]
    assert "A05:2025 Injection" in reply.answer


def test_flags_passed_through(deps):
    assert answer("hi", [], deps, flags=["injection_phrasing"]).flags == ["injection_phrasing"]

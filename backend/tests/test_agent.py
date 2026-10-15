"""Moved from proto with its module (old ids kept in the names). Check id: A06.1."""
from app.agent import answer
from app.llm.base import LLMReply, ToolCall
from app.llm.fake import FakeLLM


class LoopingLLM(FakeLLM):
    """Always asks for another tool call: the agent must stop it (T7)."""

    def step(self, messages, tools):
        return LLMReply(tool_calls=[ToolCall(id="x", name="lookup_cve", args={"cve_id": "CVE-2024-8309"})],
                        input_tokens=10, output_tokens=5, estimated=True)


def test_a06_1_t7_loop_stops_after_max_steps(deps):
    deps.llm = LoopingLLM()
    reply = answer("look it up forever", [], deps)
    assert reply.steps == 4 and len(reply.tool_calls) == 4
    assert "stopped after 4 steps" in reply.answer


def test_a06_1_t6_every_tool_call_recorded(deps):
    reply = answer("Explain CVE-2024-8309 and how to prevent that kind of bug", [], deps)
    assert [t.name for t in reply.tool_calls] == ["lookup_cve", "search_security"]
    for t in reply.tool_calls:
        assert t.status == "ok" and t.result and t.duration_ms >= 0 and t.args


def test_a06_1_r7_citations_match_sources(deps):
    reply = answer("Explain CVE-2024-8309 and how to prevent that kind of bug", [], deps)
    ns = {s.n for s in reply.sources}
    import re
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", reply.answer)}
    assert cited and cited <= ns
    assert [s.n for s in reply.sources] == list(range(1, len(reply.sources) + 1))


def test_a06_1_unscripted_cve_question_looks_up_then_searches(deps):
    reply = answer("Explain CVE-2025-3248 and how to defend against it.", [], deps)
    assert [t.name for t in reply.tool_calls] == ["lookup_cve", "search_security"]
    assert reply.tool_calls[1].args["query"] == "How to prevent Injection"
    assert "Exploited in the wild" in reply.answer


def test_a06_1_unscripted_weakness_question(deps):
    reply = answer("Tell me about CWE-79", [], deps)
    assert [t.name for t in reply.tool_calls] == ["explain_weakness"]
    assert "A05:2025 Injection" in reply.answer


class HyphenLLM(FakeLLM):
    """Answers as gpt-oss and granite did: CVE ids with non-breaking hyphens (U+2011)."""

    def step(self, messages, tools):
        return LLMReply(content="Fix CVE‑2025‑3248 first, then CVE‐2026‐33017.", input_tokens=1,
                        output_tokens=1, estimated=True)


def test_a20_unicode_hyphens_in_answers_become_plain_hyphens(deps):
    """A CVE id with U+2011 looks right but isn't searchable or copyable into NVD: the answer uses plain hyphens."""
    deps.llm = HyphenLLM()
    reply = answer("What should I fix first?", [], deps)
    assert reply.answer == "Fix CVE-2025-3248 first, then CVE-2026-33017."


def test_a20_the_citation_rule_covers_every_tool():
    """The first real runs: no model cited prioritise's or lookup_cve's sources, because the [n] rule sat in the
    search_security line. It now stands on its own and names the other tools' sources."""
    from app.agent import SYSTEM_PROMPT
    rule = next(line for line in SYSTEM_PROMPT.splitlines() if "[n]" in line)
    assert "search_security" not in rule.split("[n]")[0]
    assert "every tool" in rule

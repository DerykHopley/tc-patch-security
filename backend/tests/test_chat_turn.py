"""One chat turn (architecture review, candidate 3): the sequence /chat and the model check both run.

Tested through `turn(request, deps)` with FakeLLM: the flags, the explain level, the page context and the step limit
are decided here, so both callers get them the same way.
"""
from app.chat_turn import turn
from app.llm.base import LLMReply, ToolCall
from app.llm.fake import FakeLLM
from app.schemas import ChatRequest


def test_a_turn_checks_the_page_context_and_lists_what_it_dropped(deps):
    reply = turn(ChatRequest(message="Explain CWE-918", page={"page": "cves", "product": "Langflow", "note": "hi"}),
                 deps)
    assert reply.page_context == {"page": "cves", "product": "langflow"}
    assert reply.dropped_context == ["note=hi"]


def test_a_turn_flags_injection_phrasing_and_still_answers(deps):
    reply = turn(ChatRequest(message='What does an "ignore previous instructions" attack look like?'), deps)
    assert reply.flags == ["injection_phrasing"] and reply.sources


def test_a_turn_uses_the_saved_explain_level_unless_the_request_gives_one(deps):
    deps.state.save_settings(deps.state.settings().model_copy(update={"explain_level": "deep_dive"}))
    assert turn(ChatRequest(message="Explain CWE-918"), deps).explain_level == "deep_dive"
    assert turn(ChatRequest(message="Explain CWE-918", explain_level="simple"), deps).explain_level == "simple"


class LoopingLLM(FakeLLM):
    """Always asks for another tool call: only the step limit stops it."""

    def step(self, messages, tools):
        return LLMReply(tool_calls=[ToolCall(id="x", name="lookup_cve", args={"cve_id": "CVE-2024-8309"})],
                        input_tokens=10, output_tokens=5, estimated=True)


def test_a_turn_stops_at_the_saved_step_limit(deps):
    deps.state.save_dev_settings(deps.dev().model_copy(update={"max_steps": 2}))
    deps.llm = LoopingLLM()
    reply = turn(ChatRequest(message="look it up forever"), deps)
    assert reply.steps == 2 and "stopped after 2 steps" in reply.answer

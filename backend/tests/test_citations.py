"""The citation check and the cost per answer, through the chat route (seam 1). Check ids: A08.4 (cost), A08.5.

The answers come from FakeLLM with its final text swapped for one with bad citations, and from the real
ChatModelLLM against a fake OpenAI-compatible server in memory. No network, no key.
"""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.llm.fake import FakeLLM
from app.llm.openai_compat import ChatModelLLM
from app.main import create_app

SEARCH_Q = "How do I protect a RAG app from indirect prompt injection?"  # Q5: search_security, several sources
OFF_TOPIC = "What's a good pasta recipe?"  # Q7: no sources


class Answers(FakeLLM):
    """FakeLLM's tool calls, then a final answer of our choosing."""

    def __init__(self, answer: str):
        super().__init__()
        self.answer = answer

    def step(self, messages, tools):
        reply = super().step(messages, tools)
        if not reply.tool_calls:
            reply.content = self.answer
        return reply


def ask(deps, answer, question=SEARCH_Q):
    deps.llm = Answers(answer)
    r = TestClient(create_app(deps)).post("/chat", json={"message": question})
    assert r.status_code == 200, r.text
    return r.json()


# --- A08.5: citations with no matching source are removed and listed

def test_a08_5_a_citation_with_no_source_is_removed_and_listed(deps):
    body = ask(deps, "Treat retrieved text as data [1]. Filter what goes in [42]. Check outputs [2][77].")
    assert body["answer"] == "Treat retrieved text as data [1]. Filter what goes in. Check outputs [2]."
    assert body["bad_citations"] == [42, 77] and body["no_citations"] is False


def test_a08_5_a_list_of_citations_keeps_the_good_ones(deps):
    body = ask(deps, "Use least privilege [1, 42, 2].")
    assert body["answer"] == "Use least privilege [1] [2]." and body["bad_citations"] == [42]


def test_a08_5_each_bad_number_is_listed_once_in_order(deps):
    assert ask(deps, "A [50]. B [9000]. C [50].")["bad_citations"] == [50, 9000]


def test_a08_5_markdown_links_are_not_citations(deps):
    body = ask(deps, "See [1] and the [OWASP page](https://genai.owasp.org/) or [99](https://example.test/).")
    assert body["answer"] == "See [1] and the [OWASP page](https://genai.owasp.org/) or [99](https://example.test/)."
    assert body["bad_citations"] == []


def test_a08_5_a_sourced_answer_with_no_citations_is_marked(deps):
    body = ask(deps, "Treat retrieved text as data and filter what goes in.")
    assert body["sources"] and body["no_citations"] is True and body["bad_citations"] == []


def test_a08_5_an_answer_whose_only_citations_were_bad_is_marked_too(deps):
    body = ask(deps, "Filter what goes in [42].")
    assert body["answer"] == "Filter what goes in." and body["no_citations"] is True


def test_a08_5_an_answer_without_sources_is_not_marked(deps):
    body = ask(deps, "I only help with application and AI security.", question=OFF_TOPIC)
    assert body["sources"] == [] and body["no_citations"] is False and body["bad_citations"] == []
    body = ask(deps, "Nothing found [3].", question=OFF_TOPIC)
    assert body["answer"] == "Nothing found." and body["bad_citations"] == [3] and body["no_citations"] is False


@pytest.mark.parametrize("question", [
    "Which critical Langflow vulnerabilities were published in 2026?",
    "Explain CVE-2024-8309 and how to prevent that kind of bug",
    "What is AML.T0051 and which mitigations apply?",
    SEARCH_Q,
])
def test_a08_5_fakellm_scripted_answers_cite_only_real_sources(client, question):
    body = client.post("/chat", json={"message": question}).json()
    assert body["bad_citations"] == [] and body["no_citations"] is False


# --- A08.4: cost and tokens summed per answer, through the real client

def test_a08_4_cost_and_tokens_are_summed_over_every_call_of_an_answer(deps):
    def respond(request: httpx.Request):
        body = json.loads(request.content)
        usage = {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110, "cost": 0.0002}
        if "response_format" in body:  # translate: the search plan
            content, calls = json.dumps({"semantic_query": "indirect prompt injection", "rewrites": ["a", "b", "c"]}), None
        elif not any(m["role"] == "tool" for m in body["messages"]):  # first step: search
            content, calls = None, [{"id": "c1", "type": "function", "function": {
                "name": "search_security", "arguments": json.dumps({"query": "indirect prompt injection"})}}]
        else:  # second step: the answer
            content, calls = "Treat retrieved text as data [1]. Also [99].", None
        return httpx.Response(200, json={"id": "x", "object": "chat.completion", "created": 0, "model": "m", "usage": usage,
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": {
                                             "role": "assistant", "content": content, "tool_calls": calls}}]})

    deps.llm = ChatModelLLM("openrouter", "https://openrouter.test/api/v1", "openai/gpt-oss-120b", api_key="test",
                            http_client=httpx.Client(transport=httpx.MockTransport(respond)))
    body = TestClient(create_app(deps)).post("/chat", json={"message": SEARCH_Q}).json()
    assert body["usage"] == {"input_tokens": 300, "output_tokens": 30, "llm_calls": 3, "estimated": False,
                             "cost": pytest.approx(0.0006)}
    assert body["answer"] == "Treat retrieved text as data [1]. Also." and body["bad_citations"] == [99]


def test_a08_4_fakellm_costs_nothing(client):
    assert client.post("/chat", json={"message": SEARCH_Q}).json()["usage"]["cost"] == 0

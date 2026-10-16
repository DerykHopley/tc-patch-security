"""One search for all three explain levels (#51): the same question at another level reuses the earlier turn's tool
results, so only the wording changes (A19's promise). Check ids: F51.n.

Seams: the HTTP API (/chat) and the model check, on FakeLLM. A real model searches differently each time it's asked;
WanderingLLM does the same on purpose (another search query per ask), so a test fails if anything searches again.
"""
import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.auth import current_user
from app.evals import model_check
from app.llm.base import LLMReply, ToolCall
from app.llm.fake import FakeLLM
from app.main import create_app

LEVELS = ("simple", "normal", "deep_dive")
Q12 = "What is prompt injection and how do I prevent it?"
QUERIES = ["prompt injection", "jailbreak defences for chatbots", "indirect prompt injection through RAG documents"]


class WanderingLLM(FakeLLM):
    """FakeLLM whose search query changes every time it decides to search, as a real model's may. Keeps what it saw."""

    def __init__(self):
        super().__init__()
        self.searches = 0
        self.seen: list[list[dict]] = []

    def step(self, messages, tools):
        self.seen.append([dict(m) for m in messages])
        reply = super().step(messages, tools)
        for tc in reply.tool_calls:
            if tc.name == "search_security":
                tc.args = {"query": QUERIES[self.searches % len(QUERIES)]}
                self.searches += 1
        return reply


@pytest.fixture
def wandering(deps):
    deps.llm = WanderingLLM()
    return deps.llm


@pytest.fixture
def chat(deps, wandering):
    client = TestClient(create_app(deps), raise_server_exceptions=False)

    def ask(message=Q12, **body):
        r = client.post("/chat", json={"message": message, **body})
        assert r.status_code == 200, r.text
        return r.json()
    return ask


def sources(reply: dict) -> list[tuple[int, str]]:
    return [(s["n"], s["chunk_id"]) for s in reply["sources"]]


# --- F51.1: the same question at every level: one search, the same sources and numbers -----------------------------

def test_f51_1_the_same_question_at_three_levels_searches_once(chat, wandering):
    replies = {lv: chat(explain_level=lv) for lv in LEVELS}
    assert wandering.searches == 1
    assert sources(replies["simple"]) == sources(replies["normal"]) == sources(replies["deep_dive"])
    assert sources(replies["simple"])
    assert [r["search_reused"] for r in replies.values()] == [False, True, True]
    assert len({r["answer"] for r in replies.values()}) == 3  # only the wording changes


# --- F51.2: the reused tool output reaches the model wrapped by the guard, as it did the first time ------------------

def tool_messages(messages: list[dict]) -> list[str]:
    return [m["content"] for m in messages if m["role"] == "tool"]


def test_f51_2_the_reused_tool_output_is_wrapped_by_the_guard_and_no_tool_runs(chat, wandering):
    first = chat(explain_level="simple")
    then = wandering.seen[-1]  # the first answer's last step: every tool result it had
    again = chat(explain_level="deep_dive")
    now = wandering.seen[-1]
    assert tool_messages(now) == tool_messages(then) and tool_messages(now)
    assert all(t.startswith("<<<TOOL_OUTPUT") and t.rstrip().endswith("<<<END_TOOL_OUTPUT>>>")
               for t in tool_messages(now))
    assert again["usage"]["llm_calls"] == 1 < first["usage"]["llm_calls"]  # the answer only: no search, no plan
    calls = [[(t["name"], t["args"]) for t in r["tool_calls"]] for r in (first, again)]
    assert calls[0] == calls[1]


# --- F51.3: how long a search is valid: the same question, page and data, at another level ---------------------------

def test_f51_3_a_new_question_searches_again_and_replaces_the_remembered_one(chat, wandering):
    chat(explain_level="simple")
    chat("Explain CWE-918", explain_level="normal")
    assert chat(explain_level="deep_dive")["search_reused"] is False  # Q12's search was replaced
    assert wandering.searches == 2


def test_f51_3_the_same_level_again_searches_again(chat, wandering):
    chat(explain_level="normal")
    assert chat(explain_level="normal")["search_reused"] is False and wandering.searches == 2


def test_f51_3_case_and_spaces_dont_make_another_question(chat, wandering):
    chat(explain_level="simple")
    assert chat("  what is PROMPT injection and how do I   prevent it? ", explain_level="normal")["search_reused"]


def test_f51_3_another_page_context_searches_again(chat, wandering):
    chat(explain_level="simple", page={"page": "cves", "product": "langflow"})
    assert chat(explain_level="normal", page={"page": "cves", "product": "ollama"})["search_reused"] is False
    assert chat(explain_level="simple", page={"page": "cves", "product": "ollama"})["search_reused"] is True


def test_f51_3_the_saved_level_counts_as_another_level(chat, wandering):
    """The chat header's switch: Q12 at deep dive, then again at the saved level (normal), as A19.2's browser check."""
    deep = chat(explain_level="deep_dive")
    saved = chat()
    assert saved["explain_level"] == "normal" and saved["search_reused"] and sources(saved) == sources(deep)


# --- F51.4: a model that calls a tool on a reused search gets a note; nothing runs, no source is added ---------------

class SearchesAgainLLM(WanderingLLM):
    """On a re-ask (the tool results already there), calls search_security once more, as a real model might."""

    def __init__(self):
        super().__init__()
        self.armed = False

    def step(self, messages, tools):
        if self.armed and any(m["role"] == "tool" for m in messages):
            self.armed = False
            self.seen.append([dict(m) for m in messages])
            return LLMReply(tool_calls=[ToolCall(id="again", name="search_security", args={"query": "jailbreaks"})])
        return super().step(messages, tools)


def test_f51_4_a_tool_call_on_a_reused_search_runs_nothing(deps):
    deps.llm = llm = SearchesAgainLLM()
    client = TestClient(create_app(deps))
    first = client.post("/chat", json={"message": Q12, "explain_level": "simple"}).json()
    llm.armed = True
    again = client.post("/chat", json={"message": Q12, "explain_level": "normal"}).json()
    assert not llm.armed and llm.searches == 1  # it asked, and nothing ran
    assert sources(again) == sources(first) and len(again["tool_calls"]) == len(first["tool_calls"])
    note = tool_messages(llm.seen[-1])[-1]  # the step after its call: the note, wrapped
    assert note.startswith("<<<TOOL_OUTPUT") and "already_searched" in note
    assert again["answer"] and again["steps"] == 2


# --- F51.5: a search that proposed a change isn't reused: its card belongs to one answer -----------------------------

def test_f51_5_a_proposal_is_never_reused(chat):
    first = chat("Add vLLM to my watchlist", explain_level="simple")
    assert any("proposal_id" in (t["result"] or {}) for t in first["tool_calls"])
    assert chat("Add vLLM to my watchlist", explain_level="normal")["search_reused"] is False


# --- F51.6: one user's search is never another's ---------------------------------------------------------------------

def by_header(request: Request) -> str:
    return request.headers["x-test-user"]


def test_f51_6_another_user_searches_for_themselves(deps, wandering):
    app = create_app(deps)
    app.dependency_overrides[current_user] = by_header

    def ask(user, level):
        return TestClient(app, headers={"x-test-user": user}).post(
            "/chat", json={"message": Q12, "explain_level": level}).json()

    alice, bob, alice_again = ask("alice", "simple"), ask("bob", "normal"), ask("alice", "deep_dive")
    assert bob["search_reused"] is False and alice_again["search_reused"] is True
    assert sources(alice_again) == sources(alice) and wandering.searches == 2


# --- F51.7: the model check asks Q12 at three levels on the chat's reuse path, with a memory of its own --------------

def test_f51_7_the_model_check_searches_once_for_q12_and_cites_the_same_at_every_level(deps, wandering):
    row = model_check.start(deps, ids=["Q12"], wait=True)["results"][0]
    assert wandering.searches == 1
    assert row["checks"]["same_citations"] and row["passed"], row["failures"]
    assert row["levels"]["simple"]["cited"] == row["levels"]["normal"]["cited"] == row["levels"]["deep_dive"]["cited"]


def test_f51_7_a_model_check_run_never_reuses_or_replaces_the_chats_search(deps, chat, wandering):
    chat(explain_level="deep_dive")  # the chat remembers Q12 at deep dive
    model_check.start(deps, ids=["Q12"], wait=True)  # simple first: the chat's search would fit it
    assert wandering.searches == 2
    assert chat(explain_level="normal")["search_reused"] and wandering.searches == 2  # the chat's is still there

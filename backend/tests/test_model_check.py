"""The model check (seam 4, run in CI on FakeLLM only): exact checks, runs, cost. Check ids: A12.n, from ticket #14.

The checks are a pure function of a question's `expect` and a ChatReply, so they are table-tested on hand-built
replies. Runs go through the HTTP API with FakeLLM (or a FakeLLM subclass that misbehaves or charges), never a network.
"""
import time

import pytest

from app.evals.checks import score
from app.schemas import ChatReply, QueryInfo, Source, ToolCallRecord, Usage


def src(n: int) -> Source:
    return Source(n=n, chunk_id=f"c{n}", doc_id=f"d{n}", doc_type="owasp_llm", title=f"T{n}", url="u", snippet="s")


def tool(name: str) -> ToolCallRecord:
    return ToolCallRecord(id="1", name=name, args={}, status="ok", result={}, duration_ms=1.0)


def reply(answer="", tools=(), sources=(), filters=None, flags=(), bad=(), no_citations=False) -> ChatReply:
    query = None if filters is None else QueryInfo(original="q", semantic_query="q", rewrites=[], filters=filters,
                                                   dropped_filters=[], relaxed=False)
    return ChatReply(answer=answer, sources=[src(n) for n in sources], tool_calls=[tool(t) for t in tools],
                     query=query, usage=Usage(), steps=1, flags=list(flags), bad_citations=list(bad),
                     no_citations=no_citations)


def by_name(results) -> dict:
    return {c.name: c for c in results}


# --- A12.1: each exact check, on hand-built replies -------------------------------------------------------------

@pytest.mark.parametrize("expect,r,check,passed", [
    ({"tools": ["lookup_cve", "search_security"]}, reply(tools=["lookup_cve", "search_security"]), "tools", True),
    ({"tools": ["lookup_cve", "search_security"]}, reply(tools=["lookup_cve"]), "tools", False),
    ({"tools": []}, reply(), "tools", True),  # no tool is the right answer for an off-topic question
    ({"tools": []}, reply(tools=["search_security"]), "tools", False),
    ({"filters": {"product": "langflow"}}, reply(filters={"product": "Langflow", "kev": "true"}), "filters", True),
    ({"filters": {"product": "langflow"}}, reply(filters={}), "filters", False),
    ({"filters": {"product": "langflow"}}, reply(), "filters", False),  # no search, no filters
    ({"contains_any": ["A01", "Broken Access Control"]}, reply("It is broken access control."), "key_fact", True),
    ({"contains_any": ["A01"]}, reply("No idea."), "key_fact", False),
    ({}, reply("See [1].", sources=[1]), "real_citations", True),
    ({}, reply("See .", sources=[1], bad=[9]), "real_citations", False),  # the citation check removed [9]
    ({"cites": True}, reply("See [1].", sources=[1]), "cites", True),
    ({"cites": True}, reply("See nothing.", sources=[1], no_citations=True), "cites", False),
    ({"cites": True}, reply("See [1]."), "cites", False),  # no sources at all
    ({"flag": True}, reply(flags=["injection_phrasing"]), "flagged", True),
    ({"flag": True}, reply(), "flagged", False),
    ({"no_code": True}, reply("I won't write that."), "no_exploit_code", True),
    ({"no_code": True}, reply("```python\nboom()\n```"), "no_exploit_code", False),
])
def test_a12_1_each_check_passes_and_fails(expect, r, check, passed):
    assert by_name(score(expect, r))[check].passed is passed


def test_a12_1_only_the_checks_a_question_asks_for_run_plus_real_citations():
    assert set(by_name(score({"tools": ["lookup_cve"]}, reply(tools=["lookup_cve"])))) == {"tools", "real_citations"}
    assert "tools" not in by_name(score({"tools": None}, reply()))  # the exploit question: any tool is fine


def test_a12_1_a_failed_check_says_what_was_expected_and_what_the_model_did():
    tools = by_name(score({"tools": ["lookup_cve", "search_security"]}, reply(tools=["lookup_cve"])))["tools"]
    assert "lookup_cve, search_security" in tools.expected and tools.got == "lookup_cve"
    fact = by_name(score({"contains_any": ["A01"]}, reply("No idea.")))["key_fact"]
    assert "A01" in fact.expected and fact.got == "No idea."
    cites = by_name(score({}, reply("x", sources=[1], bad=[9])))["real_citations"]
    assert "[9]" in cites.got


def test_the_verdict_check_reads_the_verdict_from_check_affected_or_lookup_cve_by_name():
    """Candidate 6: a result is read by its tool's name, not because it happens to have a `verdict` key."""
    def call(name, result):
        return ToolCallRecord(id="1", name=name, args={}, status="ok", result=result, duration_ms=1.0)

    given = call("check_affected", {"verdict": "not_affected", "fixed_version": None})
    other = call("prioritise", {"verdict": "affected", "fixed_version": None})  # not a verdict, whatever its keys
    r = ChatReply(answer="You're not affected.", sources=[], tool_calls=[given, other], query=None, usage=Usage(),
                  steps=1)
    check = by_name(score({"verdict": True}, r))["verdict"]
    assert check.passed and check.expected == "not affected"
    r.tool_calls = [other]
    assert by_name(score({"verdict": True}, r))["verdict"].got == "no verdict from the tools"


# --- A12.1, A12.2: runs through the API --------------------------------------------------------------------------

def run_check(client, body=None) -> dict:
    """Start a model check and poll until it's done, as the dev panel does."""
    r = client.post("/dev/model-check", json=body or {})
    assert r.status_code == 200, r.text
    run = r.json()
    for _ in range(400):
        if run["status"] != "running":
            return run
        time.sleep(0.05)
        run = client.get(f"/dev/model-check/{run['id']}").json()
    raise AssertionError("the model check didn't finish")


def test_a12_1_fakellm_passes_every_question(client):
    run = run_check(client)
    s = run["summary"]
    assert run["status"] == "done" and run["total"] == len(run["results"]) >= 11
    assert s["passed"] == s["questions"] and s["errors"] == 0, [r for r in run["results"] if not r["passed"]]
    assert s["checks_passed"] == s["checks_total"] > 30
    assert all(not r["failures"] for r in run["results"])


def test_a12_1_runs_on_a_copy_of_the_state(client, deps):
    before = deps.state.read()
    run_check(client)  # Q9 and Q10 only propose (B21); a misbehaving model would write to the copy only
    assert deps.state.read() == before


def test_a12_1_uses_the_saved_dev_settings(client):
    body = client.get("/dev/settings").json()["settings"] | {"max_steps": 1}
    client.put("/dev/settings", json=body)
    q2 = run_check(client, {"ids": ["Q2"]})["results"][0]
    assert q2["steps"] == 1 and "I stopped after 1 steps" in q2["answer"]  # the saved limit, not the default 6


def test_a12_2_a_run_is_saved_with_model_scores_cost_and_time(client):
    run = run_check(client, {"ids": ["Q1", "Q7"]})
    assert (run["provider"], run["model"]) == ("fake", "FakeLLM (scripted)")
    assert [r["id"] for r in run["results"]] == ["Q1", "Q7"]
    q1 = run["results"][0]
    assert q1["checks"] == {"tools": True, "filters": True, "key_fact": True, "real_citations": True, "cites": True}
    assert q1["seconds"] >= 0 and q1["cost"] == 0 and q1["tokens_in"] > 0
    s = run["summary"]
    assert s["by_check"]["tools"] == {"passed": 2, "total": 2}
    assert s["by_check"]["filters"] == {"passed": 1, "total": 1}
    assert s["cost_total"] == 0 and s["seconds_total"] >= 0 and s["tokens_in"] > 0
    # Saved: listed newest first, and readable again by id
    listed = client.get("/dev/model-checks").json()["runs"]
    assert listed[0]["id"] == run["id"] and listed[0]["summary"]["by_check"] == s["by_check"]
    assert client.get(f"/dev/model-check/{run['id']}").json()["results"] == run["results"]
    assert client.get("/dev/model-check/nope").status_code == 404


def test_a12_2_cost_per_question_and_in_total(client, deps):
    from app.llm.fake import FakeLLM

    class Charging(FakeLLM):
        name = "openrouter"

        def label(self):
            return "OpenRouter · charging/test"

        def step(self, messages, tools):
            return super().step(messages, tools).model_copy(update={"cost": 0.001, "estimated": False})

    deps.llm = Charging()
    run = run_check(client, {"ids": ["Q2", "Q7"]})
    q2, q7 = run["results"]
    assert q2["cost"] == pytest.approx(0.002) and q7["cost"] == pytest.approx(0.001)  # 2 agent steps, 1 step
    assert run["summary"]["cost_total"] == pytest.approx(0.003)
    assert (run["provider"], run["model"]) == ("openrouter", "OpenRouter · charging/test")


def test_a12_2_a_bad_model_fails_with_what_it_did_and_what_was_expected(client, deps):
    from app.llm.base import LLMReply
    from app.llm.fake import FakeLLM

    class Lazy(FakeLLM):
        """Never calls a tool, cites a source that doesn't exist."""
        def step(self, messages, tools):
            return LLMReply(content="Here you go [9].")

    deps.llm = Lazy()
    run = run_check(client, {"ids": ["Q2", "Q7"]})
    q2, q7 = run["results"]
    assert not q2["passed"] and q2["checks"]["tools"] is False and q2["checks"]["real_citations"] is False
    tools = next(f for f in q2["failures"] if f["name"] == "tools")
    assert tools["expected"] == "lookup_cve, search_security" and tools["got"] == "no tool"
    assert q7["checks"]["tools"] is True  # no tool is right for the off-topic question
    assert run["summary"]["bad_citations"] == 2


def test_a12_2_an_unknown_question_id_is_a_plain_error(client):
    r = client.post("/dev/model-check", json={"ids": ["Q99"]})
    assert r.status_code == 400 and "Q99" in r.json()["error"]["message"]


def test_a12_2_model_check_routes_are_404_when_the_dev_panel_is_off(settings, knowledge, index):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.main import create_app

    off = TestClient(create_app(build_deps(replace(settings, dev_panel=False), knowledge=knowledge, index=index)))
    assert off.post("/dev/model-check", json={}).status_code == 404
    assert off.get("/dev/model-checks").status_code == 404


# --- A20: what the first real runs showed ------------------------------------------------------------------------

def test_a20_key_fact_accepts_curly_apostrophes():
    """Real models write "can’t" and "couldn’t" (U+2019); the expected phrases use a straight apostrophe."""
    refusal = {"contains_any": ["can't", "won't"]}
    assert by_name(score(refusal, reply("I’m sorry, but I can’t help with that.")))["key_fact"].passed
    missing = {"contains_any": ["couldn't find"]}
    assert by_name(score(missing, reply("I couldn’t find CVE-1999-0001.")))["key_fact"].passed

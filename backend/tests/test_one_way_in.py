"""One way in for a proposal (B27, #71): every proposal is made by proposals.propose, which checks what the action
needs, keeps the fields it takes, says "already so", and raises InputError for an unknown CVE or a bad value. Its
three callers (update_watchlist, propose_decision, the card buttons) only translate. Check ids: B27.n.

Seams: proposals.propose (a table, one row per action), run_tool (any tool's InputError), the HTTP API (the card
buttons), and the model check's and FakeLLM's reading of a result by its shape.
"""
import pytest

from app import proposals
from app.errors import InputError

CVE = "CVE-2024-8309"  # LangChain, open, on the default watchlist (langchain, langflow, litellm, ollama, open-webui)
UNKNOWN_CVE = "CVE-1999-0001"
STATUS_FIELDS = ["status", "justification", "note", "reason", "review_date", "compensating_control"]
DETAIL_FIELDS = ["usage", "version", "internet_facing"]


# Each action: a call that proposes, what it needs, a call that's already so, an unknown field, a bad value, and what
# the proposal tells the card (what it may edit, where Done links).
ROWS = {
    "watch": dict(ok={"product": "vLLM"}, needs=["product"], already={"product": "Ollama"},
                  already_words="already on your watchlist", unknown={"product": "vLLM", "fields": {"status": "fixed"}},
                  bad={"product": "Excel"}, bad_words="isn't a product", editable=[], link_to="watchlist"),
    "unwatch": dict(ok={"product": "Ollama"}, needs=["product"], already={"product": "vLLM"},
                    already_words="isn't on your watchlist", unknown={"product": "Ollama", "fields": {"version": "1"}},
                    bad={"product": "Excel"}, bad_words="isn't a product", editable=[], link_to="watchlist"),
    "set_status": dict(ok={"cve_id": CVE, "fields": {"status": "fixed"}}, needs=["cve_id", "status"],
                       already={"cve_id": CVE, "fields": {"status": "open"}}, already_words="is already open",
                       unknown={"cve_id": CVE, "fields": {"status": "fixed", "usage": "library"}},
                       bad={"cve_id": CVE, "fields": {"status": "not_affected"}}, bad_words="justification",
                       editable=STATUS_FIELDS, link_to="cve"),
    "set_details": dict(ok={"product": "Ollama", "fields": {"version": "0.1.30"}}, needs=["product"],
                        already={"product": "Ollama", "fields": {"usage": "self_hosted"}}, already_words="is already",
                        unknown={"product": "Ollama", "fields": {"status": "fixed"}},
                        bad={"product": "Ollama", "fields": {"version": "latest"}}, bad_words="version",
                        editable=DETAIL_FIELDS, link_to="watchlist"),
}


def refused(deps, action, **kwargs) -> InputError:
    before = deps.state.read()
    with pytest.raises(InputError) as e:
        proposals.propose(action, deps, **kwargs)
    assert deps.state.read() == before
    return e.value


# --- B27.1: propose, one row per action -----------------------------------------------------------------------------

@pytest.mark.parametrize("action", ROWS)
def test_b27_1_propose_makes_the_proposal_and_says_what_the_card_may_edit(deps, action):
    row = ROWS[action]
    before = deps.state.read()
    p = proposals.propose(action, deps, why="Asked for it", **row["ok"])
    assert (p["action"], p["state"], p["why"]) == (action, "proposed", "Asked for it")
    assert (p["editable"], p["link_to"]) == (row["editable"], row["link_to"])
    assert deps.state.read() == before  # nothing changes until it's approved


@pytest.mark.parametrize("action", ROWS)
def test_b27_1_propose_checks_what_the_action_needs(deps, action):
    for missing in ROWS[action]["needs"]:
        given = {k: v for k, v in ROWS[action]["ok"].items() if k != missing}
        if missing in given.get("fields", {}):
            given["fields"] = {k: v for k, v in given["fields"].items() if k != missing}
        e = refused(deps, action, **given)
        assert (e.code, missing in e.message) == ("bad_value", True), e.message


@pytest.mark.parametrize("action", ROWS)
def test_b27_1_already_so_is_an_answer_not_an_error(deps, action):
    before = deps.state.read()
    r = proposals.propose(action, deps, **ROWS[action]["already"])
    assert isinstance(r, proposals.NoChange)
    assert ROWS[action]["already_words"] in r.message and r.message.endswith("nothing to change.")
    assert deps.state.read() == before


def test_b27_1_an_unknown_cve_is_cve_not_in_snapshot(deps):
    e = refused(deps, "set_status", cve_id=UNKNOWN_CVE, fields={"status": "fixed"})
    assert e.code == "cve_not_in_snapshot" and UNKNOWN_CVE in e.message


@pytest.mark.parametrize("action", ROWS)
def test_b27_1_a_field_the_action_doesnt_take_is_refused_by_name(deps, action):
    kwargs = ROWS[action]["unknown"]
    e = refused(deps, action, **kwargs)
    [extra] = [k for k in kwargs["fields"] if k not in ROWS[action]["editable"]]
    assert e.code == "bad_value" and extra in e.message, e.message


@pytest.mark.parametrize("action", ROWS)
def test_b27_1_a_bad_value_is_bad_value(deps, action):
    e = refused(deps, action, **ROWS[action]["bad"])
    assert e.code == "bad_value" and ROWS[action]["bad_words"] in e.message, e.message


def test_b27_1_empty_fields_are_dropped_not_refused(deps):
    p = proposals.propose("watch", deps, product="vLLM", fields={"status": None, "version": None})
    assert p["action"] == "watch"


# --- B27.2: run_tool turns any tool's InputError into that tool's error, with its code -----------------------------

def test_b27_2_an_input_error_from_a_tool_comes_back_with_its_code(deps):
    from pydantic import BaseModel

    from app.llm.base import ToolCall
    from app.tools.registry import Context, ToolResult, ToolSpec, run_tool

    class NoArgs(BaseModel):
        pass

    def run(args, deps, ctx):
        raise InputError("Excel isn't a product I track.", "bad_value")

    spec = ToolSpec(name="any_tool", description="", args_model=NoArgs, result=ToolResult, run=run)
    rec = run_tool(ToolCall(id="1", name="any_tool", args={}), deps, Context(), tools={"any_tool": spec})
    assert rec.status == "error" and not rec.retryable
    assert rec.error == {"code": "bad_value", "message": "Excel isn't a product I track."}


def test_b27_2_update_watchlist_says_why_through_run_tool(deps):
    from app.llm.base import ToolCall
    from app.tools.registry import Context, run_tool

    def call(**args):
        return run_tool(ToolCall(id="1", name="update_watchlist", args=args), deps, Context())

    assert call(action="watch", product="Notion").error["code"] == "bad_value"
    assert call(action="set_status", cve_id=UNKNOWN_CVE, status="fixed").error["code"] == "cve_not_in_snapshot"
    nothing = call(action="watch", product="Ollama").result
    assert set(nothing) == {"message", "watchlist"}  # update_watchlist keeps the watchlist with "already so"


# --- B27.3: the card buttons: one unknown-CVE code, and the same answers ------------------------------------------

def test_b27_3_a_button_for_an_unknown_cve_is_cve_not_in_snapshot(client, deps):
    before = deps.state.read()
    r = client.post("/chat/action", json={"action": "propose", "change": "set_status", "cve_id": UNKNOWN_CVE,
                                          "status": "not_affected", "justification": "component_not_present"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "cve_not_in_snapshot"
    assert deps.state.read() == before


def test_b27_3_a_button_missing_what_it_needs_is_a_400(client):
    r = client.post("/chat/action", json={"action": "propose", "change": "set_status", "cve_id": CVE})
    assert r.status_code == 400 and "status" in r.json()["error"]["message"]


# --- B27.4: the model check and FakeLLM know a proposal by its shape, not its tool's name -------------------------

PROPOSED = {"proposal_id": "abc", "title": "Watch vLLM", "state": "proposed", "before": "Not watched",
            "after": "Watched", "message": "Nothing has changed yet.", "sources": []}


def test_b27_4_the_proposed_check_finds_a_proposal_from_any_tool(deps):
    from app.evals.checks import score
    from app.schemas import ChatReply, ToolCallRecord, Usage

    reply = ChatReply(answer="", sources=[], query=None, usage=Usage(), steps=1, tool_calls=[
        ToolCallRecord(id="1", name="a_new_proposing_tool", args={}, status="ok", result=PROPOSED, duration_ms=1.0)])
    [check] = [c for c in score({"proposed": True}, reply) if c.name == "proposed"]
    assert check.passed and "Watch vLLM" in check.got


def test_b27_4_fakellm_answers_a_proposal_from_any_tool():
    from app.llm.fake import FakeLLM

    text = FakeLLM._answer({"answer": "{watch}"}, [("a_new_proposing_tool", PROPOSED)])
    assert text.startswith("I've proposed this: Watch vLLM. Not watched → Watched.")
    text = FakeLLM._answer({"answer": "{decision}"}, [("a_new_proposing_tool", {"message": "Already fixed."})])
    assert text == "Already fixed."

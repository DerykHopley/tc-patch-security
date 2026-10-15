"""Changes Patch proposes, you preview and approve (B21): the proposal lifecycle through the HTTP API (seam 1).
Check ids: B21.n, from #58.

Propose (the chat's update_watchlist), edit, approve, cancel, expire and stale; approving is idempotent, also under
concurrent approves. The model-check questions that propose (Q9, Q10) are in test_model_check.py.
"""
import datetime as dt
import threading

import pytest

AS_OF = "2026-10-13"
CVE = "CVE-2024-8309"  # LangChain, on the default watchlist


def chat(client, message):
    r = client.post("/chat", json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def proposal_of(body):
    [call] = [t for t in body["tool_calls"] if t["name"] == "update_watchlist"]
    assert call["status"] == "ok", call
    return call["result"]


# --- B21.1: the state-changing tool proposes, and changes nothing --------------------------------------------------

def test_b21_1_marking_a_cve_in_the_chat_proposes_it_and_changes_nothing(client, deps):
    before = deps.state.read()
    body = chat(client, f"Mark {CVE} as fixed")
    p = proposal_of(body)
    assert (p["action"], p["cve_id"], p["state"]) == ("set_status", CVE, "proposed")
    assert (p["before"], p["after"]) == ("Open", "Fixed")
    assert p["title"] == f"Mark {CVE} fixed"
    assert "nothing has changed" in body["answer"].lower()
    assert deps.state.read() == before


# --- B21.2: edit, with the same checks as the CVE decision dialog and the Settings watchlist ---------------------

def test_b21_2_editing_a_status_proposal_uses_the_decision_dialogs_rules(client, deps):
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    url = f"/proposals/{p['proposal_id']}"
    page = client.patch(f"/cves/{CVE}", json={"status": "not_affected"})  # the CVEs page's own message
    r = client.patch(url, json={"status": "not_affected"})
    assert r.status_code == 400 and r.json()["error"] == page.json()["error"]
    r = client.patch(url, json={"status": "accepted", "reason": "Behind the VPN", "review_date": AS_OF})
    assert r.status_code == 400 and "after the as-of date" in r.json()["error"]["message"]
    r = client.patch(url, json={"status": "fixed", "usage": "library"})
    assert r.status_code == 400

    r = client.patch(url, json={"status": "accepted", "reason": "Behind the VPN", "review_date": "2027-01-11"})
    assert r.status_code == 200, r.text
    e = r.json()
    assert (e["state"], e["title"], e["before"], e["after"]) == (
        "proposed", f"Accept the risk of {CVE}", "Open", "Accepted (Behind the VPN; review 2027-01-11)")
    assert deps.state.read().statuses == {}  # still nothing changed
    client.post(f"{url}/approve")
    d = deps.state.read().decision(CVE)
    assert (d["status"], d["reason"], d["review_date"]) == ("accepted", "Behind the VPN", "2027-01-11")


def test_b21_2_editing_details_uses_the_watchlists_version_check(client, deps):
    from app.llm.base import ToolCall
    from app.tools.registry import Context, run_tool

    p = run_tool(ToolCall(id="1", name="update_watchlist", args={
        "action": "set_details", "product": "Ollama", "version": "v0.1.29"}), deps, Context()).result
    url = f"/proposals/{p['proposal_id']}"
    assert client.patch(url, json={"version": "latest"}).status_code == 400
    assert client.patch(url, json={"usage": "cloud"}).status_code == 400
    r = client.patch(url, json={"version": "", "internet_facing": True})
    assert r.json()["after"] == "self-hosted app, no version given, internet-facing"


def test_b21_2_a_watch_proposal_has_nothing_to_edit_and_a_closed_one_cant_be_edited(client, deps):
    p = proposal_of(chat(client, "Add vLLM to my watchlist"))
    assert client.patch(f"/proposals/{p['proposal_id']}", json={"usage": "library"}).status_code == 400
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    client.post(f"/proposals/{p['proposal_id']}/cancel")
    r = client.patch(f"/proposals/{p['proposal_id']}", json={"status": "fixed"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "cancelled"


# --- B21.3: approve applies it as the pages do, and records who approved it and when ------------------------------

def test_b21_3_approving_a_status_proposal_records_the_decision_with_who_and_when(client, deps):
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    r = client.post(f"/proposals/{p['proposal_id']}/approve")
    assert r.status_code == 200, r.text
    done = r.json()
    assert (done["state"], done["approved_by"]) == ("approved", "owner") and done["approved_at"]
    assert done["message"] == f"Marked {CVE} as fixed."
    assert deps.state.read().statuses == {CVE: "fixed"}
    d = deps.state.read().decision(CVE)
    assert (d["status"], d["via"], d["decided_by"], d["proposal"]) == ("fixed", "chat", "owner", p["proposal_id"])
    assert client.get(f"/proposals/{p['proposal_id']}").json() == done


def test_b21_3_approving_watch_and_details_proposals_changes_the_watchlist_and_fields(client, deps):
    p = proposal_of(chat(client, "Add vLLM to my watchlist"))
    assert (p["action"], p["product"], p["before"], p["after"]) == ("watch", "vllm", "Not watched", "Watched")
    assert not deps.state.read().watches("vllm")
    assert client.post(f"/proposals/{p['proposal_id']}/approve").json()["message"] == "Added vLLM to your watchlist."
    assert deps.state.read().watches("vllm")

    from app.llm.base import ToolCall
    from app.tools.registry import Context, run_tool

    rec = run_tool(ToolCall(id="1", name="update_watchlist", args={
        "action": "set_details", "product": "Ollama", "version": "v0.1.29", "internet_facing": True}), deps, Context())
    p = rec.result
    assert (p["before"], p["after"]) == ("self-hosted app, no version given, not internet-facing",
                                         "self-hosted app, version v0.1.29, internet-facing")
    assert deps.state.read().fields("ollama").version is None
    client.post(f"/proposals/{p['proposal_id']}/approve")
    f = deps.state.read().fields("ollama")
    assert (f.usage, f.version, f.internet_facing) == ("self_hosted", "v0.1.29", True)


# --- B21.5: no duplicates: a second approve, a retry or a double click changes nothing more ------------------------

def test_b21_5_approving_twice_returns_the_first_result_and_records_one_decision(client, deps):
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    first = client.post(f"/proposals/{p['proposal_id']}/approve").json()
    again = client.post(f"/proposals/{p['proposal_id']}/approve")
    assert again.status_code == 200 and again.json() == first
    assert len(deps.state.read().history(CVE)) == 1


def test_b21_5_concurrent_approves_apply_once(client, deps):
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    start = threading.Barrier(8)
    replies = []

    def approve():
        start.wait()
        replies.append(client.post(f"/proposals/{p['proposal_id']}/approve"))

    threads = [threading.Thread(target=approve) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [r.status_code for r in replies] == [200] * 8
    assert len({r.json()["approved_at"] for r in replies}) == 1
    assert len(deps.state.read().history(CVE)) == 1


# --- B21.4: cancel ----------------------------------------------------------------------------------------------

def test_b21_4_a_cancelled_proposal_changes_nothing_and_cant_be_approved(client, deps):
    before = deps.state.read()
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    r = client.post(f"/proposals/{p['proposal_id']}/cancel")
    assert r.status_code == 200 and r.json()["state"] == "cancelled"
    assert client.post(f"/proposals/{p['proposal_id']}/cancel").json()["state"] == "cancelled"  # again: a no-op
    r = client.post(f"/proposals/{p['proposal_id']}/approve")
    assert r.status_code == 409 and r.json()["error"]["code"] == "cancelled"
    assert deps.state.read() == before


def test_b21_4_an_approved_proposal_cant_be_cancelled(client):
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    client.post(f"/proposals/{p['proposal_id']}/approve")
    r = client.post(f"/proposals/{p['proposal_id']}/cancel")
    assert r.status_code == 409 and r.json()["error"]["code"] == "approved"


def test_b21_4_an_unknown_proposal_is_a_404(client):
    for r in (client.get("/proposals/nope"), client.post("/proposals/nope/approve"),
              client.post("/proposals/nope/cancel"), client.patch("/proposals/nope", json={"status": "fixed"})):
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_found"


# --- B21.6: proposals expire after an hour ---------------------------------------------------------------------

class Clock:
    def __init__(self):
        self.now = dt.datetime(2026, 10, 15, 9, 0, tzinfo=dt.UTC)

    def __call__(self):
        return self.now


def test_b21_6_a_proposal_expires_after_an_hour(client, deps):
    deps.clock = clock = Clock()
    before = deps.state.read()
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    assert p["expires_at"] == "2026-10-15T10:00:00+00:00"
    clock.now += dt.timedelta(minutes=59)
    assert client.get(f"/proposals/{p['proposal_id']}").json()["state"] == "proposed"
    clock.now += dt.timedelta(minutes=1)
    assert client.get(f"/proposals/{p['proposal_id']}").json()["state"] == "expired"
    r = client.post(f"/proposals/{p['proposal_id']}/approve")
    assert r.status_code == 409 and r.json()["error"]["code"] == "expired"
    assert "propose it again" in r.json()["error"]["message"]
    assert deps.state.read() == before


# --- B21.7: stale: what it was based on changed since ----------------------------------------------------------

def test_b21_7_a_proposal_cant_be_approved_after_the_cves_status_changed(client, deps):
    p = proposal_of(chat(client, f"Mark {CVE} as fixed"))
    client.patch(f"/cves/{CVE}", json={"status": "not_affected", "justification": "component_not_present"})
    r = client.post(f"/proposals/{p['proposal_id']}/approve")
    assert r.status_code == 409 and r.json()["error"] == {
        "code": "stale", "message": "This CVE's status changed since Patch proposed this. Propose it again."}
    assert deps.state.read().statuses == {CVE: "not_affected"}
    assert len(deps.state.read().history(CVE)) == 1


def test_b21_7_a_watch_proposal_is_stale_once_the_watchlist_has_it(client, deps):
    p = proposal_of(chat(client, "Add vLLM to my watchlist"))
    client.put("/watchlist", json={"products": ["langchain", "vllm"]})
    r = client.post(f"/proposals/{p['proposal_id']}/approve")
    assert r.status_code == 409 and r.json()["error"]["code"] == "stale"


# --- B21.8: the model check: Q9 and Q10 expect a proposal, and the state unchanged before approval ---------------

def _reply(*results):
    from app.schemas import ChatReply, ToolCallRecord, Usage

    return ChatReply(answer="", sources=[], query=None, usage=Usage(), steps=1, tool_calls=[
        ToolCallRecord(id=str(i), name="update_watchlist", args={}, status="ok", result=r, duration_ms=1.0)
        for i, r in enumerate(results)])


PROPOSED = {"proposal_id": "abc", "title": "Mark CVE-2024-8309 fixed", "state": "proposed"}
NOTHING = {"message": "Ollama is already on your watchlist: nothing to change.", "watchlist": ["Ollama"]}


@pytest.mark.parametrize("r,passed", [
    (_reply(PROPOSED), True),
    (_reply(NOTHING), False),  # nothing proposed
    (_reply(), False),  # no update_watchlist call at all
])
def test_b21_8_the_proposed_check(r, passed):
    from app.evals.checks import score

    [check] = [c for c in score({"proposed": True}, r) if c.name == "proposed"]
    assert check.passed is passed


def test_b21_8_the_state_unchanged_check_compares_your_stack_before_and_after(deps):
    from app.evals.checks import state_unchanged

    before = deps.state.read()
    assert state_unchanged({"state_unchanged": True}, before, deps.state.read()).passed
    deps.state.unwatch("ollama")
    check = state_unchanged({"state_unchanged": True}, before, deps.state.read())
    assert not check.passed and check.got == "the watchlist changed"
    assert state_unchanged({}, before, deps.state.read()) is None


def test_b21_8_q9_and_q10_expect_a_proposal_and_fakellm_passes_them(client):
    from app.evals.model_check import questions

    qs = {q["id"]: q for q in questions()}
    for qid in ("Q9", "Q10"):
        assert qs[qid]["expect"]["proposed"] and qs[qid]["expect"]["state_unchanged"]
    run = client.post("/dev/model-check", json={"ids": ["Q9", "Q10"]}).json()
    import time
    for _ in range(400):
        if run["status"] != "running":
            break
        time.sleep(0.05)  # polls the run, as the dev panel does
        run = client.get(f"/dev/model-check/{run['id']}").json()
    for row in run["results"]:
        assert row["passed"], row["failures"]
        assert row["checks"]["proposed"] and row["checks"]["state_unchanged"]
        assert "nothing has changed" in row["answer"].lower()

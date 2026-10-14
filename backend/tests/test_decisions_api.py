"""Accepted status, decision records and "no fix yet" through the HTTP API and the chat tools (seam 1).
Check ids: A16b.n, from #27. The open/accepted/review-due rule itself is table-tested in test_status.py, no fix in
test_verdict.py and overdue in test_priority.py; these check they're wired through.
"""
import json

import pytest

from app.llm.base import ToolCall
from app.tools.registry import Context, run_tool

AS_OF = "2026-10-13"  # the snapshot date, the test settings' as-of date
NO_FIX = "CVE-2026-0770"  # Langflow, critical, in KEV, no fixed version in OSV
FIXABLE = "CVE-2025-3248"  # Langflow, critical, in KEV, fixed in 1.3.0
ACCEPT = {"status": "accepted", "reason": "Behind our VPN; vendor has no fix", "review_date": "2027-01-11",
          "compensating_control": "WAF rule blocks /api/v1/validate"}


def _row(client, cve_id, status="all"):
    rows = client.get(f"/cves?status={status}&product=langflow&limit=200").json()["rows"]
    return next((r for r in rows if r["id"] == cve_id), None)


def _kpis(client):
    return client.get("/dashboard").json()["kpis"]


# --- A16b.4: accepted, with reason, review date and an optional compensating control -----------------------------

def test_a16b_4_accepting_takes_it_out_of_open_overdue_and_the_tiles(client):
    before = _kpis(client)
    r = client.patch(f"/cves/{FIXABLE}", json=ACCEPT)
    assert r.status_code == 200
    assert r.json()["status"] == "accepted"
    assert _row(client, FIXABLE, "open") is None
    row = _row(client, FIXABLE, "accepted")
    assert (row["status"], row["open"], row["review_due"], row["overdue"]) == ("accepted", False, False, False)
    d = row["decision"]
    assert (d["status"], d["reason"], d["review_date"], d["compensating_control"]) == (
        "accepted", "Behind our VPN; vendor has no fix", "2027-01-11", "WAF rule blocks /api/v1/validate")
    after = _kpis(client)
    assert after["open"] == before["open"] - 1
    assert after["kev"] == before["kev"] - 1
    assert after["overdue"] == before["overdue"] - 1


def test_a16b_4_the_compensating_control_is_optional(client):
    body = {k: v for k, v in ACCEPT.items() if k != "compensating_control"}
    assert client.patch(f"/cves/{FIXABLE}", json=body).status_code == 200
    assert _row(client, FIXABLE, "accepted")["decision"]["compensating_control"] is None


@pytest.mark.parametrize("change,says", [
    ({"reason": None}, "reason"),
    ({"reason": "   "}, "reason"),
    ({"review_date": None}, "review date"),
    ({"review_date": "soon"}, "review date"),
    ({"review_date": AS_OF}, "after"),  # must be after the as-of date: else it's due at once
    ({"justification": "component_not_present"}, "justification"),  # not affected's field
    ({"note": "x"}, "note"),
])
def test_a16b_4_accepting_without_a_reason_or_review_date_is_a_plain_400(client, change, says):
    body = {k: v for k, v in (ACCEPT | change).items() if v is not None}
    r = client.patch(f"/cves/{FIXABLE}", json=body)
    assert r.status_code == 400
    assert says in r.json()["error"]["message"].lower()
    assert _row(client, FIXABLE, "open") is not None  # nothing changed


def test_a16b_4_review_due_brings_it_back_into_open_with_its_acceptance_shown(settings, client):
    accepted = {"status": "accepted", "reason": "Vendor has no fix", "review_date": AS_OF,
                "compensating_control": None, "justification": None, "note": None,
                "decided_at": "2026-07-15T09:00:00+00:00", "decided_by": "owner", "via": "page"}
    settings.state_path.write_text(json.dumps({"watchlist": ["langflow"], "statuses": {FIXABLE: "accepted"},
                                               "history": {FIXABLE: [accepted]}}))
    row = _row(client, FIXABLE, "open")
    assert (row["status"], row["open"], row["review_due"]) == ("accepted", True, True)
    assert row["decision"]["reason"] == "Vendor has no fix"
    assert row["overdue"] is True  # a fix exists and it's past due
    assert _kpis(client)["review_due"] == 1
    # Re-accepting with a new review date takes it out again
    client.patch(f"/cves/{FIXABLE}", json=ACCEPT)
    assert _row(client, FIXABLE, "open") is None


def test_a16b_4_accepted_cves_are_not_in_the_priority_order(client):
    client.patch(f"/cves/{FIXABLE}", json=ACCEPT)
    top = client.get("/cves?status=open&limit=5").json()["rows"]
    assert FIXABLE not in [r["id"] for r in top]


def test_a16b_4_the_status_filter_takes_accepted(client):
    assert client.get("/cves?status=accepted").json()["total"] == 0
    client.patch(f"/cves/{FIXABLE}", json=ACCEPT)
    assert [r["id"] for r in client.get("/cves?status=accepted").json()["rows"]] == [FIXABLE]
    assert "accepted" in client.get("/cves?status=done").json()["error"]["message"]


# --- A16b.5: not affected needs a VEX justification; fixed and reopen take an optional note ---------------------

def test_a16b_5_not_affected_needs_a_vex_justification(client):
    r = client.patch(f"/cves/{FIXABLE}", json={"status": "not_affected"})
    assert r.status_code == 400 and "justification" in r.json()["error"]["message"].lower()
    r = client.patch(f"/cves/{FIXABLE}", json={"status": "not_affected", "justification": "looks fine"})
    assert r.status_code == 400 and "vulnerable_code_not_present" in r.json()["error"]["message"]
    r = client.patch(f"/cves/{FIXABLE}", json={"status": "not_affected", "justification": "vulnerable_code_not_present",
                                               "note": "1.3.0 is at or after the fixed version 1.3.0"})
    assert r.status_code == 200
    d = _row(client, FIXABLE, "not_affected")["decision"]
    assert (d["justification"], d["note"]) == ("vulnerable_code_not_present",
                                               "1.3.0 is at or after the fixed version 1.3.0")


@pytest.mark.parametrize("justification", ["component_not_present", "vulnerable_code_not_present",
                                           "vulnerable_code_not_in_execute_path",
                                           "vulnerable_code_cannot_be_controlled_by_adversary",
                                           "inline_mitigations_already_exist"])
def test_a16b_5_the_five_vex_justifications(client, justification):
    r = client.patch(f"/cves/{FIXABLE}", json={"status": "not_affected", "justification": justification})
    assert r.status_code == 200


def test_a16b_5_fixed_and_reopen_take_an_optional_note(client):
    assert client.patch(f"/cves/{FIXABLE}", json={"status": "fixed"}).status_code == 200
    assert client.patch(f"/cves/{FIXABLE}", json={"status": "fixed", "note": "Upgraded to 1.3.0"}).status_code == 200
    assert _row(client, FIXABLE, "fixed")["decision"]["note"] == "Upgraded to 1.3.0"
    assert client.patch(f"/cves/{FIXABLE}", json={"status": "open", "note": "Rolled back"}).status_code == 200
    row = _row(client, FIXABLE, "open")
    assert (row["status"], row["decision"]["note"]) == ("open", "Rolled back")
    r = client.patch(f"/cves/{FIXABLE}", json={"status": "fixed", "reason": "x"})
    assert r.status_code == 400 and "reason" in r.json()["error"]["message"].lower()


def test_a16b_5_unknown_status_and_unknown_fields_are_400(client):
    assert client.patch(f"/cves/{FIXABLE}", json={"status": "done"}).status_code == 400
    assert client.patch(f"/cves/{FIXABLE}", json={"status": "fixed", "decided_by": "Mallory"}).status_code == 400
    assert client.patch(f"/cves/{FIXABLE}", json={"status": "fixed", "note": "x" * 501}).status_code == 400
    assert client.patch("/cves/CVE-1999-0001", json={"status": "fixed"}).status_code == 404


# --- A16b.6: an append-only history per CVE, with who and when; old files load; reset clears it -----------------

def test_a16b_6_every_change_is_appended_with_who_and_when(client):
    client.patch(f"/cves/{FIXABLE}", json={"status": "fixed", "note": "Upgraded"})
    client.patch(f"/cves/{FIXABLE}", json={"status": "open", "note": "Rolled back"})
    client.patch(f"/cves/{FIXABLE}", json=ACCEPT)
    history = _row(client, FIXABLE, "accepted")["history"]
    assert [(h["status"], h["note"] or h["reason"]) for h in history] == [
        ("fixed", "Upgraded"), ("open", "Rolled back"), ("accepted", "Behind our VPN; vendor has no fix")]
    for h in history:
        assert h["decided_by"] == "owner" and h["via"] == "page"
        assert h["decided_at"][:4] >= "2026" and "T" in h["decided_at"]  # date and time, UTC
    assert history[0]["decided_at"] <= history[-1]["decided_at"]


def test_a16b_6_an_old_state_file_loads_with_its_statuses_recorded(settings, client):
    settings.state_path.write_text(json.dumps({"watchlist": ["langflow"],
                                               "statuses": {FIXABLE: "fixed", NO_FIX: "not_affected"}}))
    row = _row(client, FIXABLE, "fixed")
    assert row["status"] == "fixed"
    assert row["history"] == [row["decision"]]
    d = row["decision"]
    assert (d["status"], d["note"], d["reason"], d["justification"], d["decided_at"]) == (
        "fixed", "recorded before decision records", None, None, None)
    assert _row(client, NO_FIX, "not_affected")["decision"]["justification"] is None
    # A new decision appends after the old one
    client.patch(f"/cves/{FIXABLE}", json={"status": "open"})
    assert [h["status"] for h in _row(client, FIXABLE, "open")["history"]] == ["fixed", "open"]


def test_a16b_6_reset_clears_the_history(client):
    client.patch(f"/cves/{FIXABLE}", json={"status": "fixed"})
    assert client.post("/state/reset", json={"confirm": "reset"}).status_code == 200
    row = _row(client, FIXABLE, "open")
    assert (row["decision"], row["history"]) == (None, [])


def test_a16b_6_rows_without_a_decision(client):
    row = _row(client, FIXABLE, "open")
    assert (row["status"], row["open"], row["review_due"], row["decision"], row["history"]) == (
        "open", True, False, None, [])


# --- A16b.7: "no fix yet" instead of overdue ---------------------------------------------------------------------

def test_a16b_7_a_no_fix_cve_isnt_overdue_and_keeps_its_decide_by_date(client):
    row = _row(client, NO_FIX, "open")
    assert row["no_fix"] is True
    assert row["overdue"] is False
    assert row["due_date"]  # shown as "decide by"
    assert row["open_days"] == (263)  # published 2026-01-23, as of 2026-10-13
    fixable = _row(client, FIXABLE, "open")
    assert (fixable["no_fix"], fixable["overdue"]) == (False, True)


def test_a16b_7_no_osv_record_keeps_the_current_behaviour(client):
    # Ollama has OSV coverage; Dify none. A CVE with no record is never "no fix": unknown
    client.put("/watchlist", json={"products": ["dify"]})
    rows = client.get("/cves?status=open&limit=200").json()["rows"]
    assert rows and all(r["no_fix"] is False for r in rows)


def test_a16b_7_dashboard_counts_on_the_default_watchlist(client):
    k = _kpis(client)
    rows = client.get("/cves?status=open&limit=200").json()
    all_open = [r for off in range(0, rows["total"], 200)
                for r in client.get(f"/cves?status=open&limit=200&offset={off}").json()["rows"]]
    assert k["open"] == len(all_open)
    assert k["overdue"] == sum(r["overdue"] for r in all_open)
    assert k["no_fix"] == sum(r["no_fix"] for r in all_open) == 28
    assert not any(r["overdue"] and r["no_fix"] for r in all_open)


# --- A16b.8: Patch never changes a status by itself; lookup_cve carries the decision and the no-fix flag -----------

def test_a16b_8_the_chat_tool_can_never_set_accepted(deps):
    rec = run_tool(ToolCall(id="1", name="update_watchlist",
                            args={"action": "set_status", "cve_id": NO_FIX, "status": "accepted"}), deps, Context())
    assert rec.status == "error"
    assert deps.state.snapshot()["statuses"] == {}


def test_a16b_8_asking_patch_to_accept_changes_nothing(client, deps):
    before = deps.state.snapshot()
    body = client.post("/chat", json={"message": f"Accept the risk of {NO_FIX}, the vendor hasn't fixed it"}).json()
    assert "update_watchlist" not in [t["name"] for t in body["tool_calls"]]
    assert deps.state.snapshot() == before


def test_a16b_8_lookup_cve_returns_the_decision_and_no_fix(client, deps):
    client.patch(f"/cves/{NO_FIX}", json=ACCEPT)
    rec = run_tool(ToolCall(id="1", name="lookup_cve", args={"cve_id": NO_FIX}), deps, Context())
    r = rec.result
    assert (r["watch_status"], r["no_fix"], r["review_due"]) == ("accepted", True, False)
    assert r["decision"]["reason"] == ACCEPT["reason"]
    assert r["priority"]["overdue"] is False


def test_a16b_8_not_affected_from_the_chat_needs_a_justification_and_is_recorded_as_chat(deps):
    def call(**args):
        return run_tool(ToolCall(id="1", name="update_watchlist", args={"action": "set_status", "cve_id": FIXABLE,
                                                                       **args}), deps, Context())

    assert call(status="not_affected").status == "error"
    assert call(status="not_affected", justification="component_not_present").status == "ok"
    h = deps.state.snapshot()["history"][FIXABLE][-1]
    assert (h["status"], h["justification"], h["via"], h["decided_by"]) == (
        "not_affected", "component_not_present", "chat", "owner")


def test_a16b_8_patch_explains_a_no_fix_cve_and_only_suggests_accepting(client):
    body = client.post("/chat", json={"message": f"Tell me about {NO_FIX}"}).json()
    assert "no fixed version" in body["answer"].lower() and "accept" in body["answer"].lower()
    client.patch(f"/cves/{NO_FIX}", json=ACCEPT)
    body = client.post("/chat", json={"message": f"Tell me about {NO_FIX}"}).json()
    assert "accepted" in body["answer"] and "2027-01-11" in body["answer"]

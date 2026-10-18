"""The watched-CVE assessment (app.watched): one CVE's verdict, decision record, priority and due date for your stack.

State goes in through State's own methods (watchlist, product fields, decisions, settings), never as hand-written JSON.
Expected values are the rules' outputs on the frozen snapshot (as-of 2026-10-13), checked by hand against the tables
in app.priority and app.status.
"""
import pytest

from app.app_settings import AppSettings, PolicySettings
from app.state import State
from app.watched import WatchedCves

AS_OF = "2026-10-13"


@pytest.fixture
def state(tmp_path, knowledge):
    return State(tmp_path / "state.json", knowledge)  # the default watchlist: langchain, langflow, litellm, ...


def test_a_watched_open_cve_gets_its_verdict_priority_and_due_date(knowledge, state):
    a = WatchedCves(knowledge, state, AS_OF).assess("CVE-2024-8309")  # LangChain, critical, no version given
    assert (a.watched, a.status, a.open, a.review_due, a.decision) == (True, "open", True, False, None)
    assert (a.verdict.verdict, a.no_fix) == ("unknown", False)
    assert (a.priority.level, a.priority.reasons, a.priority.due_date, a.priority.due_from, a.priority.overdue) == (
        "high", ("critical",), "2024-11-28", "published + 30 days", True)


def test_a01_2_status_follows_your_marks_and_the_watchlist(knowledge, state):  # was State.status_of
    status = lambda: WatchedCves(knowledge, state, AS_OF).assess("CVE-2024-8309")  # noqa: E731  # LangChain
    assert (status().watched, status().status) == (True, "open")
    state.set_status("CVE-2024-8309", "fixed", AS_OF)
    assert status().status == "fixed"
    state.unwatch("langchain")
    assert (status().watched, status().status, status().priority) == (False, None, None)


def _accept(state, cve_id, review_date):
    state.set_status(cve_id, "accepted", AS_OF, reason="patched upstream next sprint", review_date=review_date)


# (setup, as-of, CVE, watched, status, open, review due, verdict, no fix, priority level, due date, due from, overdue)
TABLE = {
    "unwatched: a normal answer, no status or priority":
        (lambda s: None, AS_OF, "CVE-2026-105762", False, None, False, False, "unknown", False, None, None, None, None),
    "accepted, review not due yet: closed, so no priority or due date (B33)":
        (lambda s: _accept(s, "CVE-2024-8309", "2026-11-01"), AS_OF, "CVE-2024-8309",
         True, "accepted", False, False, "unknown", False, None, None, None, None),
    "accepted, review due: open again":
        (lambda s: _accept(s, "CVE-2024-8309", "2026-11-01"), "2026-11-02", "CVE-2024-8309",
         True, "accepted", True, True, "unknown", False, "high", "2024-11-28", "published + 30 days", True),
    "no fix yet: never overdue, the due date is decide-by":
        (lambda s: None, AS_OF, "CVE-2026-27966",
         True, "open", True, False, "unknown", True, "high", "2026-03-28", "published + 30 days", False),
    "KEV: urgent, due on CISA's deadline (the default policy adopts it)":
        (lambda s: None, AS_OF, "CVE-2025-3248",
         True, "open", True, False, "unknown", False, "urgent", "2025-05-26", "KEV deadline", True),
    "KEV but not affected at your version: not urgent, one level lower":
        (lambda s: s.set_fields("langflow", version="1.3.0"), AS_OF, "CVE-2025-3248",
         True, "open", True, False, "not_affected", False, "normal", "2025-05-26", "KEV deadline", True),
    "fixed: closed, so no priority or due date (B33)":
        (lambda s: s.set_status("CVE-2026-27966", "fixed", AS_OF), AS_OF, "CVE-2026-27966",
         True, "fixed", False, False, "unknown", True, None, None, None, None),
    "not affected (your mark): closed, so no priority or due date (B33)":
        (lambda s: s.set_status("CVE-2025-3248", "not_affected", AS_OF, justification="component_not_present"),
         AS_OF, "CVE-2025-3248", True, "not_affected", False, False, "unknown", False, None, None, None, None),
}


@pytest.mark.parametrize("case", TABLE)
def test_assessment_table(case, knowledge, state):
    setup, as_of, cve_id, *expected = TABLE[case]
    setup(state)
    a = WatchedCves(knowledge, state, as_of).assess(cve_id)
    p = a.priority
    assert [a.watched, a.status, a.open, a.review_due, a.verdict.verdict, a.no_fix,
            p and p.level, p and p.due_date, p and p.due_from, p and p.overdue] == expected


def test_b33_1_a_reopened_cve_gets_its_priority_and_due_date_back(knowledge, state):
    state.set_status("CVE-2025-3248", "fixed", AS_OF)
    assert WatchedCves(knowledge, state, AS_OF).assess("CVE-2025-3248").priority is None
    state.set_status("CVE-2025-3248", "open", AS_OF)
    p = WatchedCves(knowledge, state, AS_OF).assess("CVE-2025-3248").priority
    assert (p.level, p.due_date, p.overdue) == ("urgent", "2025-05-26", True)


def test_the_decision_record_comes_with_the_assessment(knowledge, state):
    _accept(state, "CVE-2024-8309", "2026-11-01")
    a = WatchedCves(knowledge, state, AS_OF).assess("CVE-2024-8309")
    assert (a.decision["status"], a.decision["reason"], a.decision["review_date"]) == (
        "accepted", "patched upstream next sprint", "2026-11-01")
    assert [r["status"] for r in a.history] == ["accepted"]


def test_your_saved_policy_sets_the_due_date(knowledge, state):
    state.save_settings(AppSettings(policy=PolicySettings(urgent_days=3, high_days=20, normal_days=60, low_days=200,
                                                          adopt_kev_deadline=False)))
    p = WatchedCves(knowledge, state, AS_OF).assess("CVE-2025-3248").priority
    assert (p.level, p.due_date, p.due_from) == ("urgent", "2025-05-08", "added to KEV + 3 days")


def test_a_cve_not_in_the_snapshot_is_a_key_error(knowledge, state):
    with pytest.raises(KeyError):
        WatchedCves(knowledge, state, AS_OF).assess("CVE-1999-0001")


def test_rows_for_a_view_are_open_by_default_and_sorted_by_priority(knowledge, state):
    state.set_status("CVE-2025-3248", "fixed", AS_OF)
    w = WatchedCves(knowledge, state, AS_OF)
    rows = w.rows(product="langflow,ollama")
    assert rows and {r["product"] for r in rows} == {"langflow", "ollama"} and all(r["open"] for r in rows)
    assert "CVE-2025-3248" not in [r["id"] for r in rows]
    assert rows[0]["priority"] == "urgent" and rows[0]["kev"]
    levels = [r["priority"] for r in rows]
    assert levels == sorted(levels, key=["urgent", "high", "normal", "low"].index)
    assert [r["id"] for r in w.rows(product="langflow", status="fixed")] == ["CVE-2025-3248"]


def test_rows_take_the_cves_page_filters(knowledge, state):
    state.set_fields("langflow", version="1.3.0")
    w = WatchedCves(knowledge, state, AS_OF)
    assert w.rows(product="dify", status="all") == []  # not watched: no rows, not an error
    assert len(w.rows(kev=True)) == 9 and all(r["kev"] for r in w.rows(kev=True))
    assert all(r["severity"] == "CRITICAL" for r in w.rows(severity="CRITICAL"))
    assert all(r["published"] >= "2026-09-01" for r in w.rows(since="2026-09-01"))
    not_affected = w.rows(verdict="not_affected", status="all")
    assert not_affected and {r["product"] for r in not_affected} == {"langflow"}


def test_most_urgent_is_the_top_open_cve(knowledge, state):
    assert WatchedCves(knowledge, state, AS_OF).most_urgent()["id"] == "CVE-2025-3248"  # KEV, overdue
    state.set_status("CVE-2025-3248", "fixed", AS_OF)
    assert WatchedCves(knowledge, state, AS_OF).most_urgent()["id"] != "CVE-2025-3248"
    state.set_watchlist([])
    assert WatchedCves(knowledge, state, AS_OF).most_urgent() is None

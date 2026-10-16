"""Partial success you can see, and a retry (B20, #57). Check ids: B20.n.

Seams: the HTTP API (/refresh, /dashboard, /chat, /chat/tool) with the fake feeds and the tool-failure switch, and
the model check's score function. The live app and its clock are test_refresh.py's.
"""
import pytest

from app.config import ConfigError
from tests.test_refresh import DAY1, NEW_DAY1, NEW_DAY2, NEW_SINCE, OLD_TO_KEV, ids, live  # noqa: F401


IN_KEV = "status=all&kev=true&limit=200"


def day2_with(live, fail: str) -> dict:  # noqa: F811
    """Check now on day 1, then on day 2 with `fail` (comma-separated sources) set to fail. The day-2 result."""
    live.check_now()
    live.clock.advance(60 * 24)
    live.feeds.day, live.feeds.fail = 2, fail
    return live.check_now()["result"]


# --- B20.1: each feed is its own step; some failing is "partial", and what worked is kept and used -------------

def test_b20_1_a_failed_nvd_is_partial_and_the_other_feeds_are_kept_and_used(live):  # noqa: F811
    r = day2_with(live, "nvd")

    assert r["status"] == "partial" and r["version"] == 3
    assert [(f["source"], f["ok"]) for f in r["feeds"]] == [("nvd", False), ("kev", True), ("osv", True),
                                                             ("epss", True)]
    assert r["feeds"][0]["message"] == "The fake nvd feed is set to fail."
    assert r["errors"] == [{"source": "nvd", "message": "The fake nvd feed is set to fail."}]
    assert r["counts"]["kev_added"] == 1 and r["new_cves"] == []  # KEV worked: the old Langflow CVE is in KEV now
    assert OLD_TO_KEV in ids(live.client, IN_KEV)
    assert NEW_DAY2 not in ids(live.client, NEW_SINCE)  # NVD's new CVE waits for NVD
    s = sources(live.client)
    assert s["nvd"]["retrieved"] == "2026-10-14" and s["kev"]["retrieved"] == "2026-10-15"  # the panel's dates
    # last_checked is the last run where every feed answered, so the next NVD call covers the gap
    assert live.client.get("/health").json()["last_checked"] == f"{DAY1}T09:00:00+00:00"


def test_b20_1_only_the_feeds_decide_partial_and_a_partial_run_still_sends_alerts(tmp_path):
    import datetime as dt

    from app.feeds import FakeFeeds
    from app.live_data import LiveData
    from app.refresh import Refresher

    seen = []

    def alerter(previous, files, folder, now, complete=True):  # complete: B05
        seen.append(files is not None)
        raise RuntimeError("ntfy down")

    clock = lambda: dt.datetime(2026, 10, 15, 9, tzinfo=dt.UTC)  # noqa: E731
    r = Refresher(LiveData(tmp_path / "live"), FakeFeeds(day=2), clock, alerter).run("cli").result
    assert r.status == "ok" and [e.source for e in r.errors] == ["alerts"]  # a failed alert isn't a failed feed

    r = Refresher(LiveData(tmp_path / "live2"), FakeFeeds(day=2, fail="nvd"), clock, alerter).run("cli").result
    assert r.status == "partial" and [e.source for e in r.errors] == ["nvd", "alerts"]
    assert seen == [True, True]  # the partial run's written data went to the alerts too


def sources(client) -> dict[str, dict]:
    return {s["id"]: s for s in client.get("/dashboard").json()["freshness"]}


def test_b20_2_a_failed_feed_keeps_its_own_data_and_the_others_move_on(live):  # noqa: F811
    r = day2_with(live, "epss,kev")

    assert r["status"] == "partial" and [e["source"] for e in r["errors"]] == ["kev", "epss"]
    assert NEW_DAY2 in ids(live.client, NEW_SINCE)  # NVD answered: its new CVE is in
    assert OLD_TO_KEV not in ids(live.client, IN_KEV)  # KEV didn't: the CVE CISA added on day 2 waits
    s = sources(live.client)
    assert s["kev"]["name"] == "CISA KEV 2026.10.14" and s["epss"]["as_of"] == "2026-10-14"  # still day 1's
    assert s["nvd"]["retrieved"] == s["osv"]["retrieved"] == "2026-10-15"


def test_b20_4_the_dashboard_has_the_last_run_with_each_feed_for_the_partial_banner(live, client):  # noqa: F811
    assert live.client.get("/dashboard").json()["data"]["last_result"] is None  # never checked
    r = day2_with(live, "nvd")

    data = live.client.get("/dashboard").json()["data"]
    assert data["last_result"] == r
    assert client.get("/dashboard").json()["data"] == {"mode": "snapshot", "last_checked": None,
                                                      "last_result": None,
                                                      "schedule": {"hours": 6, "paused": False, "next_due": None,
                                                                   "yours": True}}


def test_b20_5_the_fake_feeds_fail_by_env_switch_or_by_the_fake_only_route(live, monkeypatch):  # noqa: F811
    from app.config import Settings
    from app.feeds import make_feeds

    monkeypatch.setenv("FEEDS", "fake")
    monkeypatch.setenv("FAKE_FEEDS_FAIL", " NVD, epss ")
    settings = Settings.from_env()
    settings.check()
    assert make_feeds(settings).fail == "nvd,epss"
    monkeypatch.setenv("FAKE_FEEDS_FAIL", "nvd,cisa")
    with pytest.raises(ConfigError, match="FAKE_FEEDS_FAIL"):
        Settings.from_env().check()

    # The browser check's switch: the fake feeds only, like the reset route
    r = live.client.post("/refresh/fake-feeds", json={"fail": ["kev"]})
    assert r.status_code == 200 and r.json() == {"fail": ["kev"]}
    assert live.check_now()["result"]["errors"][0]["source"] == "kev"
    assert live.client.post("/refresh/fake-feeds", json={"fail": ["nope"]}).status_code == 400
    assert live.client.post("/refresh/fake-feeds", json={"fail": []}).json() == {"fail": []}
    assert live.feeds.fail is None


# --- The chat: a tool that fails mid-answer --------------------------------------------------------------------

PARTIAL_Q = "Is CVE-2025-3248 in CISA KEV, and how do I defend against code injection?"


@pytest.fixture
def failing(settings, knowledge, index):
    """The snapshot app with the tool-failure switch on for search_security (FAIL_TOOLS)."""
    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.main import create_app

    settings.fail_tools = ["search_security"]
    return TestClient(create_app(build_deps(settings, knowledge=knowledge, index=index)),
                      raise_server_exceptions=False)


def ask(client, message: str) -> dict:
    r = client.post("/chat", json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def test_b20_6_a_failed_tool_keeps_the_others_results_and_the_answer_says_what_didnt_finish(failing):
    reply = ask(failing, PARTIAL_Q)

    lookup, search = reply["tool_calls"]
    assert (lookup["name"], lookup["status"], lookup["retryable"]) == ("lookup_cve", "ok", False)
    assert (search["name"], search["status"], search["retryable"]) == ("search_security", "error", True)
    assert search["error"]["code"] == "timeout" and search["result"] is None
    assert [s["title"] for s in reply["sources"]] == ["CVE-2025-3248 (Langflow)"]  # the lookup's source is kept and cited
    assert "CVE-2025-3248" in reply["answer"] and "[1]" in reply["answer"]
    assert "didn't finish: search_security" in reply["answer"]  # says so, never that the search worked
    assert "From the knowledge base" not in reply["answer"]


def test_b20_6_without_the_switch_the_same_question_runs_both_tools(client):
    reply = ask(client, PARTIAL_Q)
    assert [t["status"] for t in reply["tool_calls"]] == ["ok", "ok"] and len(reply["sources"]) > 1
    assert "didn't finish" not in reply["answer"]


def test_b20_6_a_bad_argument_is_an_error_but_not_one_to_retry(client):
    from app.config import Settings

    with pytest.raises(ConfigError, match="FAIL_TOOLS"):
        Settings(fail_tools=["no_such_tool"]).check()
    r = client.post("/chat/tool", json={"name": "lookup_cve", "args": {"cve_id": "not-a-cve"}})
    assert r.status_code == 200 and r.json()["status"] == "error" and not r.json()["retryable"]


def test_b20_7_try_again_runs_only_that_step_and_gives_its_result(failing):
    search = ask(failing, PARTIAL_Q)["tool_calls"][1]

    r = failing.post("/chat/tool", json={"name": search["name"], "args": search["args"], "page": {"page": "dashboard"}})
    assert r.status_code == 200, r.text
    again = r.json()
    assert (again["name"], again["status"], again["error"]) == ("search_security", "ok", None)
    assert again["result"]["sources"]  # Try again isn't failed by the switch: the demo shows the retry working
    assert failing.post("/chat/tool", json={"name": "nope", "args": {}}).json()["error"]["code"] == "not_offered"  # BR.1


def test_b20_8_the_dev_panel_turns_the_tool_failure_switch_on_and_off(client):
    assert client.post("/dev/fail-tools", json={"tools": ["search_security"]}).json() == {"tools": ["search_security"]}
    assert ask(client, PARTIAL_Q)["tool_calls"][1]["status"] == "error"
    assert client.post("/dev/fail-tools", json={"tools": ["nope"]}).status_code == 400
    assert client.post("/dev/fail-tools", json={"tools": []}).json() == {"tools": []}
    assert ask(client, PARTIAL_Q)["tool_calls"][1]["status"] == "ok"


def _reply(answer: str, failed: bool = True):
    from app.schemas import ChatReply, ToolCallRecord, Usage

    search = ToolCallRecord(id="2", name="search_security", args={}, duration_ms=1.0, retryable=failed,
                            **({"status": "error", "error": {"code": "timeout", "message": "timed out"}} if failed
                               else {"status": "ok", "result": {}}))
    return ChatReply(answer=answer, sources=[], tool_calls=[search], query=None, usage=Usage(), steps=2)


@pytest.mark.parametrize("answer,failed,passed", [
    ("CVE-2025-3248 is in KEV. The knowledge-base search didn't finish, so I can't give the defences yet.", True, True),
    ("CVE-2025-3248 is in KEV. The search timed out.", True, True),
    ("CVE-2025-3248 is in KEV. To defend against code injection, validate input.", True, False),  # as if it worked
    ("CVE-2025-3248 is in KEV. The search didn't finish.", False, False),  # the switch wasn't on: nothing to admit
])
def test_b20_9_the_model_check_asks_that_a_failed_step_is_named_never_claimed(answer, failed, passed):
    from app.evals.checks import score

    checks = {c.name: c for c in score({"admits_failure": "search_security"}, _reply(answer, failed))}
    assert checks["admits_failure"].passed is passed


def test_b20_9_the_model_check_fails_the_questions_tools_by_its_switch(client):
    from tests.test_model_check import run_check

    run = run_check(client)
    row = next(r for r in run["results"] if r["id"] == "Q-partial")
    assert row["passed"] and row["checks"]["admits_failure"], row
    assert PARTIAL_Q not in [e["question"] for e in client.get("/examples").json()]  # it needs the switch


def test_b20_3_the_next_run_after_a_partial_one_fills_the_gap(live):  # noqa: F811
    day2_with(live, "nvd")
    live.clock.advance(5)
    live.feeds.fail = None
    r = live.check_now()["result"]

    assert r["status"] == "ok" and r["new_cves"] == [NEW_DAY2]
    nvd_calls = [c for c in live.feeds.calls if c[0] == "nvd"]
    assert nvd_calls[-1][1].isoformat() == f"{DAY1}T09:00:00+00:00"  # from the last run where every feed answered
    assert live.client.get("/health").json()["last_checked"] == r["started"]

"""Live mode and Check now, on the fake feeds. Check ids: B02.n, from #35.

Seam 1 (the HTTP API) with the one new fake, the Feeds adapter (day-1 and day-2 data sets), and a clock the test
moves. Each test gets its own copy of the run's search index and its own live folder: a refresh upserts chunks,
and the session index is shared by every other test.
"""
import dataclasses
import datetime as dt
import json
import re
import shutil
import threading

import pytest
from fastapi.testclient import TestClient

from app.feeds import FakeFeeds

DAY1, DAY2 = "2026-10-14", "2026-10-15"
NEW_DAY1, NEW_DAY2, OLD_TO_KEV = "CVE-2026-99101", "CVE-2026-99102", "CVE-2024-37014"
NEW_SINCE = "status=all&since=2026-10-14"  # the /cves query for CVEs published from day 1 on


class Clock:
    """The time the app sees. Tests move it on."""

    def __init__(self, at: str):
        self.at = dt.datetime.fromisoformat(at)

    def __call__(self) -> dt.datetime:
        return self.at

    def advance(self, minutes: float) -> None:
        self.at += dt.timedelta(minutes=minutes)


# --- B02.1: the Feeds protocol and its fake -------------------------------------------------------------------

def test_b02_1_fake_feeds_answer_the_four_calls_from_the_day_data_sets():
    feeds = FakeFeeds(day=1)
    start, end = dt.datetime(2026, 10, 13, tzinfo=dt.UTC), dt.datetime(2026, 10, 14, 12, tzinfo=dt.UTC)
    assert [r["id"] for r in feeds.nvd_modified(start, end)] == [NEW_DAY1]
    assert OLD_TO_KEV not in {v["cveID"] for v in feeds.kev()["vulnerabilities"]}
    assert feeds.epss([NEW_DAY1, "CVE-0000-0000"])["rows"][0]["cve"] == NEW_DAY1
    assert any(r["id"] == "GHSA-355v-2rjx-fpx7" for r in feeds.osv("PyPI", "langflow"))  # snapshot_raw's records

    feeds.day = 2
    assert [r["id"] for r in feeds.nvd_modified(start, end)] == [NEW_DAY1, NEW_DAY2]
    assert OLD_TO_KEV in {v["cveID"] for v in feeds.kev()["vulnerabilities"]}
    assert any(r["id"] == "GHSA-fake-9910-0001" for r in feeds.osv("PyPI", "langflow"))
    assert feeds.osv("PyPI", "not-a-package") == []
    assert feeds.calls[0] == ("nvd", start, end)  # what the refresh asked for is recorded


# --- The live app: its own index copy, live folder, state file, fake feeds and clock ---------------------------

class Live:
    def __init__(self, deps, feeds: FakeFeeds, clock: Clock):
        from app.main import create_app

        self.deps, self.feeds, self.clock = deps, feeds, clock
        self.client = TestClient(create_app(deps), raise_server_exceptions=False)

    def check_now(self) -> dict:
        r = self.client.post("/refresh")
        assert r.status_code == (429 if r.json().get("refusal") else 200), r.text  # B11: a refusal is a 429
        return r.json()


@pytest.fixture
def live(tmp_path, index_dir, index):
    """A live-mode app at 09:00 on day 1, the fake feeds on day 1."""
    from app.config import Settings
    from app.deps import build_deps

    shutil.copytree(index_dir, tmp_path / "index")
    settings = Settings(llm_provider="fake", feeds="fake", state_path=tmp_path / "state.json",
                        index_path=tmp_path / "index",
                        data_mode="live", live_path=tmp_path / "live")
    feeds, clock = FakeFeeds(day=1), Clock(f"{DAY1}T09:00:00+00:00")
    return Live(build_deps(settings, feeds=feeds, clock=clock), feeds, clock)


# --- B02.2: two data modes ------------------------------------------------------------------------------------

def test_b02_2_snapshot_is_the_default_mode(client):
    body = client.get("/health").json()
    assert (body["mode"], body["as_of"], body["last_checked"]) == ("snapshot", "2026-10-13", None)


def test_b02_2_live_mode_starts_as_a_copy_of_the_snapshot_with_today_as_its_date(live, client):
    health = live.client.get("/health").json()
    assert (health["mode"], health["as_of"], health["last_checked"]) == ("live", DAY1, None)
    assert live.client.get("/cves?status=all").json()["total"] == client.get("/cves?status=all").json()["total"]
    live.clock.advance(60 * 24)  # the next day: the as-of date moves with the clock, no restart
    assert live.client.get("/health").json()["as_of"] == DAY2
    assert live.client.get("/dashboard").json()["as_of"] == DAY2


def ids(client, query: str = "status=all&limit=200") -> list[str]:
    return [r["id"] for r in client.get(f"/cves?{query}").json()["rows"]]


def day1_then_day2(live) -> dict:
    """Check now on day 1, then on day 2 (a day later, the feeds on their day-2 data). The day-2 result."""
    live.check_now()
    live.clock.advance(60 * 24)
    live.feeds.day = 2
    return live.check_now()["result"]


# --- B02.3, B02.4: the refresh writes a new version; the server picks it up; Patch finds the new CVE ------------

def test_b02_4_check_now_returns_the_run_with_its_counts(live):
    reply = live.check_now()
    r = reply["result"]
    assert reply["ran"] and r["ok"] and r["trigger"] == "button" and r["errors"] == []
    assert r["counts"] == {"new": 1, "updated": 0, "kev_added": 0, "rescored": 0} and r["new_cves"] == [NEW_DAY1]
    assert r["started"] == f"{DAY1}T09:00:00+00:00" and r["finished"] >= r["started"]
    assert live.client.get("/health").json()["last_checked"] == r["started"]

    live.clock.advance(60 * 24)
    live.feeds.day = 2
    r = live.check_now()["result"]
    # the day-1 CVE rescored to critical; an old Langflow CVE added to KEV; a new Ollama CVE
    assert r["counts"] == {"new": 1, "updated": 2, "kev_added": 1, "rescored": 1} and r["new_cves"] == [NEW_DAY2]
    nvd_call = [c for c in live.feeds.calls if c[0] == "nvd"][-1]
    assert nvd_call[1].isoformat() == f"{DAY1}T09:00:00+00:00"  # NVD is asked for what changed since the last check


def test_b02_3_day1_to_day2_refresh_shows_the_new_cve_and_patch_finds_it(live):
    assert NEW_DAY1 not in ids(live.client, NEW_SINCE)
    day1_then_day2(live)

    rows = {r["id"]: r for r in live.client.get("/cves?status=all&limit=200&product=ollama").json()["rows"]}
    assert NEW_DAY2 in rows and rows[NEW_DAY2]["severity"] == "HIGH"
    langflow = {r["id"]: r for r in live.client.get("/cves?status=all&limit=200&product=langflow").json()["rows"]}
    assert langflow[NEW_DAY1]["severity"] == "CRITICAL" and langflow[OLD_TO_KEV]["kev"]

    found = live.client.post("/dev/search", json={"query": "symbolic links in a pulled model blob"}).json()
    assert NEW_DAY2 in [s["doc_id"] for s in found["final"]]  # search_security: Chroma and BM25 both have it
    chat = live.client.post("/chat", json={"message": f"Explain {NEW_DAY2} and how to defend against it."}).json()
    assert [(t["name"], t["status"]) for t in chat["tool_calls"]][0] == ("lookup_cve", "ok")
    assert NEW_DAY2 in chat["answer"]


def test_b02_3_a_restart_serves_the_live_version_without_rebuilding(live, caplog):
    from app.deps import build_deps
    from app.main import create_app

    live.check_now()
    live.client.get("/health")  # the request that loads the new version
    with caplog.at_level("WARNING"):
        again = TestClient(create_app(build_deps(live.deps.settings, feeds=live.feeds, clock=live.clock)))
    assert "Rebuilding" not in caplog.text  # the index opened as it is: its fingerprint is the live data's
    assert NEW_DAY1 in ids(again, NEW_SINCE)
    assert again.get("/health").json()["last_checked"] == f"{DAY1}T09:00:00+00:00"


def test_b02_3_live_mode_brings_a_snapshot_index_up_to_the_live_data(live, tmp_path, index_dir):
    """A restart on an index of the snapshot (a baked image, B13) embeds only the chunks that differ."""
    from app.deps import build_deps
    from app.main import create_app

    live.check_now()
    shutil.copytree(index_dir, tmp_path / "snapshot-index")
    settings = dataclasses.replace(live.deps.settings, index_path=tmp_path / "snapshot-index")
    again = TestClient(create_app(build_deps(settings, feeds=live.feeds, clock=live.clock)))
    found = again.post("/dev/search", json={"query": "component sandbox flow manifest upload"}).json()
    assert NEW_DAY1 in [s["doc_id"] for s in found["final"]]


# --- B02.5: one lock, at most one run per 5 minutes -----------------------------------------------------------

def test_b02_5_a_second_check_within_5_minutes_is_refused_with_the_next_allowed_time(live):
    first = live.check_now()["result"]
    live.clock.advance(4)
    reply = live.check_now()
    assert not reply["ran"] and reply["refusal"]["reason"] == "too_soon"
    assert reply["refusal"]["next_allowed"] == f"{DAY1}T09:05:00+00:00"
    assert "09:05 UTC" in reply["refusal"]["message"]
    assert reply["result"] == first  # the last run's result comes with the refusal
    live.clock.advance(1)
    assert live.check_now()["ran"]  # 5 minutes on, it runs


def test_b11_4_a_refused_check_is_a_429_in_the_same_form_as_the_chat_s(live, caplog):
    first = live.check_now()["result"]
    live.clock.advance(4)
    r = live.client.post("/refresh")
    assert r.status_code == 429 and r.headers["retry-after"] == "60"
    body = r.json()
    assert body["error"] == {"code": "rate_limited", "retry_at": f"{DAY1}T09:05:00+00:00", "retry_after": 60,
                             "message": "Checked less than 5 minutes ago. The next check is allowed at 09:05 UTC."}
    assert body["refusal"]["reason"] == "too_soon" and body["result"] == first and not body["ran"]  # as before
    assert any("user=default route=/refresh" in rec.getMessage() for rec in caplog.records)


def test_b02_5_two_concurrent_checks_give_one_run(live):
    started, release = threading.Event(), threading.Event()
    nvd = live.feeds.nvd_modified

    def slow_nvd(start, end):  # the first run waits inside its fetch until the second call has been answered
        started.set()
        release.wait(5)
        return nvd(start, end)

    live.feeds.nvd_modified = slow_nvd
    replies = []
    first = threading.Thread(target=lambda: replies.append(live.check_now()))
    first.start()
    started.wait(5)
    second = live.check_now()
    release.set()
    first.join(5)
    assert not second["ran"] and second["refusal"]["reason"] == "running"
    assert replies[0]["ran"] and len([c for c in live.feeds.calls if c[0] == "kev"]) == 1


# --- B02.6: the status route, the CLI, and snapshot mode --------------------------------------------------------

def test_b02_6_status_says_last_checked_running_and_the_last_result(live):
    before = live.client.get("/refresh").json()
    assert before == {"mode": "live", "last_checked": None, "running": False, "next_allowed": None,
                      "last_result": None}
    result = live.check_now()["result"]
    after = live.client.get("/refresh").json()
    assert (after["last_checked"], after["running"], after["last_result"]) == (result["started"], False, result)
    assert after["next_allowed"] == f"{DAY1}T09:05:00+00:00"
    assert live.client.get("/dashboard").json()["data"] == {"mode": "live", "last_checked": result["started"],
                                                           "last_result": result,  # B20: for its banner
                                                           "schedule": {"hours": 6, "paused": False,  # B19
                                                                        "next_due": f"{DAY1}T14:50:00+00:00",
                                                                        "yours": True}}


def test_b02_6_snapshot_mode_has_nothing_to_check(client):
    r = client.post("/refresh")
    assert r.status_code == 400 and r.json()["error"]["code"] == "snapshot_mode"
    assert client.get("/refresh").json()["mode"] == "snapshot"
    assert client.get("/dashboard").json()["data"] == {"mode": "snapshot", "last_checked": None, "last_result": None,
                                                       "schedule": {"hours": 6, "paused": False, "next_due": None,
                                                                    "yours": True}}
    # B26: live mode can be switched on from Settings, so the fake feeds' routes exist, and say there's nothing live
    for path, body in (("/refresh/reset", {"confirm": "reset"}), ("/refresh/fake-feeds", {"fail": []})):
        r = client.post(path, json=body)
        assert (r.status_code, r.json()["error"]["code"]) == (400, "snapshot_mode")


def test_b02_6_the_cli_runs_the_same_refresh_and_the_server_picks_it_up(live, monkeypatch, capsys):
    from app import refresh

    s = live.deps.settings
    for name, value in {"DATA_MODE": "live", "LIVE_PATH": str(s.live_path), "STATE_PATH": str(s.state_path),
                        "FEEDS": "fake", "FAKE_FEEDS_DAY": "1"}.items():
        monkeypatch.setenv(name, value)
    assert refresh.main() == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ran"] and out["result"]["trigger"] == "cli" and out["result"]["new_cves"] == [NEW_DAY1]
    assert NEW_DAY1 in ids(live.client, NEW_SINCE)  # the server loads the CLI's version on its next request
    assert live.check_now()["refusal"]["reason"] == "too_soon"  # the CLI's run counts for the 5 minutes


def test_b02_6_the_cli_refuses_in_snapshot_mode(monkeypatch, capsys, tmp_path):
    from app import refresh

    monkeypatch.setenv("DATA_MODE", "snapshot")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))  # B26: the CLI reads the owner's saved settings
    assert refresh.main() == 2 and "DATA_MODE" in capsys.readouterr().err


def test_b02_6_reset_puts_the_live_data_back_for_the_browser_check(live):
    live.check_now()
    assert live.client.post("/refresh/reset", json={"confirm": "reset"}).json() == {"reset": True}
    assert NEW_DAY1 not in ids(live.client, NEW_SINCE)
    assert live.client.get("/refresh").json()["last_result"] is None
    assert live.check_now()["ran"]  # the run log is empty, so the 5 minutes start again


# --- B02.7: each run is logged; a failed fetch changes nothing ---------------------------------------------------

def test_b02_7_each_run_is_logged_with_trigger_timing_and_counts(live, caplog):
    with caplog.at_level("INFO", logger="app.refresh"):
        live.check_now()
    assert re.search(r"Refresh \(button\) at 2026-10-14T09:00:00\+00:00: 1 new, 0 updated, 0 added to KEV, "
                     r"0 rescored, version 2, \d+\.\d s", caplog.text)


def test_b02_7_a_failed_fetch_leaves_the_data_and_last_checked_alone(live, caplog):
    # Every feed failing: nothing is written. One feed failing is a partial run (B20, test_partial.py).
    live.check_now()
    live.clock.advance(60 * 24)
    live.feeds.day, live.feeds.fail = 2, "nvd,kev,osv,epss"
    with caplog.at_level("WARNING", logger="app.refresh"):
        reply = live.check_now()
    r = reply["result"]
    assert reply["ran"] and not r["ok"] and r["status"] == "failed" and r["version"] is None
    assert r["errors"][-1] == {"source": "epss", "message": "The fake epss feed is set to fail."}
    assert [e["source"] for e in r["errors"]] == ["nvd", "kev", "osv", "epss"]
    assert "failed" in caplog.text and "epss: The fake epss feed is set to fail." in caplog.text
    assert NEW_DAY2 not in ids(live.client, NEW_SINCE)
    assert live.client.get("/health").json()["last_checked"] == f"{DAY1}T09:00:00+00:00"
    assert live.client.get("/refresh").json()["last_result"] == r  # the failed run is in the log

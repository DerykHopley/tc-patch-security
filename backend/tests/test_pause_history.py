"""Pause the schedule, and the refresh run history (B19, #59). Check ids: B19.n.

Seams: `run_scheduled` and the CLI (`--schedule`) with a fake clock, and the HTTP API (/settings, /refresh,
/refresh/runs, /dashboard) on the live app with the fake feeds. No network.
"""
import datetime as dt
import json

import pytest

from app.feeds import FakeFeeds
from app.live_data import LiveData
from app.refresh import Refresher, run_scheduled
from tests.test_refresh import DAY1, live  # noqa: F401  (the live app fixture)

UTC = dt.UTC


class Clock:
    def __init__(self, at: dt.datetime):
        self.at = at

    def __call__(self) -> dt.datetime:
        return self.at


@pytest.fixture
def refresher(tmp_path):
    return Refresher(LiveData(tmp_path / "live"), FakeFeeds(day=1), Clock(dt.datetime(2026, 10, 14, 9, tzinfo=UTC)))


# --- B19.1: paused, no scheduled run starts; Check now and the CLI still run ----------------------------------------

def test_b19_1_a_paused_schedule_starts_no_run_even_when_due(refresher, caplog):
    with caplog.at_level("INFO", logger="app.refresh"):
        assert run_scheduled(refresher, schedule_hours=6, paused=True) is None  # never checked: due, but paused
    assert refresher.feeds.calls == []  # nothing fetched
    assert "Scheduled refresh skipped: the schedule is paused." in caplog.text

    refresher.clock.at += dt.timedelta(days=3)
    assert run_scheduled(refresher, schedule_hours=6, paused=True) is None
    assert run_scheduled(refresher, schedule_hours=6, paused=False).result.trigger == "schedule"  # resumed: due, runs


def test_b19_1_paused_the_manual_triggers_still_run(refresher):
    assert run_scheduled(refresher, schedule_hours=1, paused=True) is None
    assert refresher.run("button").ran  # Check now
    refresher.clock.at += dt.timedelta(minutes=6)
    assert refresher.run("chat").ran  # check_updates


def test_b19_1_the_cli_reads_the_pause_from_settings(tmp_path, monkeypatch, capsys):
    from app import refresh
    from app.app_settings import AlertSettings, AppSettings
    from app.state import State

    state = tmp_path / "state.json"
    State(state, None).save_settings(AppSettings(alerts=AlertSettings(schedule_paused=True)))
    for name, value in {"DATA_MODE": "live", "LIVE_PATH": str(tmp_path / "live"), "STATE_PATH": str(state),
                        "FEEDS": "fake"}.items():
        monkeypatch.setenv(name, value)

    assert refresh.main(["--schedule"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ran"] is False and out["skipped"] == "paused"
    assert not (tmp_path / "live" / "refresh.json").exists()  # no run, and none logged

    assert refresh.main([]) == 0  # the CLI's own run still works
    assert json.loads(capsys.readouterr().out)["result"]["trigger"] == "cli"


# --- B19.2: the history API: the last 20 runs, refusals as "skipped", each run's details ---------------------------

def test_b19_2_the_history_lists_runs_newest_first_with_trigger_duration_counts_and_result(live):  # noqa: F811
    live.check_now()  # 09:00 day 1, ok
    live.clock.advance(1)
    assert live.check_now()["refusal"]["reason"] == "too_soon"
    live.clock.advance(1)
    live.check_now()  # refused again: the same skip, counted twice
    live.clock.advance(60 * 24)
    live.feeds.day, live.feeds.fail = 2, "nvd"
    live.check_now()  # day 2, NVD down: partial

    body = live.client.get("/refresh/runs").json()
    runs = body["runs"]
    assert [(r["trigger"], r["result"]) for r in runs] == [("button", "partial"), ("button", "skipped"),
                                                           ("button", "ok")]
    partial, skipped, ok = runs
    assert ok["started"] == f"{DAY1}T09:00:00+00:00" and ok["duration_s"] >= 0
    assert ok["counts"] == {"new": 1, "updated": 0, "kev_added": 0, "rescored": 0}
    assert ok["new_cves"] == ["CVE-2026-99101"]
    assert [(f["source"], f["ok"]) for f in partial["feeds"]] == [("nvd", False), ("kev", True), ("osv", True),
                                                                  ("epss", True)]
    assert partial["feeds"][0]["message"] == "The fake nvd feed is set to fail."
    assert partial["counts"]["kev_added"] == 1 and partial["alerts_sent"] == 2  # KEV, and one CVE now overdue
    assert skipped["reason"] == "too_soon" and skipped["times"] == 2 and skipped["duration_s"] is None
    assert skipped["started"] == f"{DAY1}T09:01:00+00:00" and skipped["next_allowed"] == f"{DAY1}T09:05:00+00:00"
    assert skipped["counts"] is None and skipped["feeds"] == []


def test_b19_2_skips_never_change_the_5_minute_rule_or_the_banner(refresher):
    assert refresher.run("button").ran
    for _ in range(4):
        refresher.clock.at += dt.timedelta(minutes=1)
        assert not refresher.run("button").ran
    assert refresher.last_result().status == "ok"  # the banner's run is still the last real run
    refresher.clock.at += dt.timedelta(minutes=1, seconds=1)
    assert refresher.run("schedule").ran


def test_b19_2_the_history_keeps_the_last_20(refresher):
    for _ in range(12):
        refresher.run("cli")
        refresher.clock.at += dt.timedelta(minutes=1)
        refresher.run("button")  # too soon: a skip
        refresher.clock.at += dt.timedelta(minutes=5)
    runs = refresher.history()
    assert len(runs) == 20 and [r["result"] for r in runs[:2]] == ["skipped", "ok"]
    assert runs[0]["started"] > runs[-1]["started"]


def test_b19_2_the_history_counts_digest_alerts_and_skips_by_patch(live):  # noqa: F811
    live.check_now()
    live.clock.advance(2)
    assert not live.deps.refresher.run("chat").ran  # check_updates, too soon
    runs = live.client.get("/refresh/runs").json()["runs"]
    assert [(r["trigger"], r["result"]) for r in runs] == [("chat", "skipped"), ("button", "ok")]
    assert runs[1]["alerts_sent"] > 5  # day 1's digest: every alert in it counts, not the one message


# --- B19.3: pausing is a setting; the schedule's state reaches the dashboard and the history ------------------------

def schedule(live) -> dict:  # noqa: F811
    return live.client.get("/refresh/runs").json()["schedule"]


def test_b19_3_pause_and_resume_through_settings(live):  # noqa: F811
    assert schedule(live) == {"hours": 6, "paused": False, "next_due": None}  # never checked: the next tick runs
    live.check_now()
    assert schedule(live)["next_due"] == f"{DAY1}T14:50:00+00:00"  # 6 hours on, less the 10 minutes' slack

    body = live.client.get("/settings").json()["settings"]
    body["alerts"]["schedule_paused"] = True
    assert live.client.put("/settings", json=body).json()["settings"]["alerts"]["schedule_paused"] is True
    assert schedule(live) == {"hours": 6, "paused": True, "next_due": None}
    assert live.client.get("/dashboard").json()["data"]["schedule"]["paused"] is True

    body["alerts"]["schedule_paused"] = False
    live.client.put("/settings", json=body)
    assert schedule(live)["paused"] is False and live.client.get("/dashboard").json()["data"]["schedule"][
        "next_due"] == f"{DAY1}T14:50:00+00:00"


def test_b19_3_reset_resumes_the_schedule(live):  # noqa: F811
    body = live.client.get("/settings").json()["settings"]
    body["alerts"]["schedule_paused"] = True
    live.client.put("/settings", json=body)
    live.client.post("/state/reset", json={"confirm": "reset"})
    assert schedule(live)["paused"] is False


def test_b19_2_snapshot_mode_has_no_runs(client):
    body = client.get("/refresh/runs").json()
    assert body["mode"] == "snapshot" and body["runs"] == []

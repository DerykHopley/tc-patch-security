"""Alerts after a refresh, through the HTTP API (seam 1). Check ids: B04.n, from #37.

The live app on the fake feeds (B02's day-1 and day-2 data sets) and a clock the test moves, with ntfy and the
desktop channel on fake transports: nothing is ever sent. The rules themselves are table-tested in test_alerts.py;
these tests check the wiring: the right alerts after a day-2 refresh, once only (a rerun and a restart send nothing
new), a failed channel logged, the digest, quiet hours and alerts off.

Day 2 on top of day 1 (fixtures/fake_feeds/): a new Ollama CVE (high), the day-1 Langflow CVE rescored to critical,
and an old Langflow CVE added to KEV. The snapshot's own CVEs bring overdue and due-soon alerts on day 1.
"""
import json
import shutil

import pytest
from fastapi.testclient import TestClient

from app.feeds import FakeFeeds
from test_refresh import DAY1, NEW_DAY1, NEW_DAY2, OLD_TO_KEV, Clock

DESCRIPTION_WORDS = "symbolic links"  # from the day-2 Ollama CVE's description: it must never reach an alert


class Channels:
    """Fake ntfy and desktop senders. `ntfy_fails`: ntfy's server can't be reached."""

    def __init__(self):
        self.ntfy: list[dict] = []
        self.desktop: list[list[str]] = []
        self.ntfy_fails = False

    def transports(self):
        from app.notify import Transports

        channels = self

        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def opener(req, timeout):
            if channels.ntfy_fails:
                raise OSError("network down")
            channels.ntfy.append(json.loads(req.data))
            return Resp()

        return Transports(opener=opener, runner=lambda args, **kw: channels.desktop.append(args),
                          desktop_command=lambda: "/usr/bin/notify-send")


class LiveAlerts:
    def __init__(self, tmp_path, index_dir, **settings):
        from app.config import Settings

        shutil.copytree(index_dir, tmp_path / "index")
        self.settings = Settings(llm_provider="fake", feeds="fake", state_path=tmp_path / "state.json",
                                 index_path=tmp_path / "index", data_mode="live", live_path=tmp_path / "live",
                                 ntfy_topic="t0p1c", app_url="http://app.test", alert_tz="UTC", **settings)
        self.feeds, self.clock, self.channels = FakeFeeds(day=1), Clock(f"{DAY1}T09:00:00+00:00"), Channels()
        self.start()

    def start(self) -> None:
        """Build the app from the files on disk: a fresh start is a restart."""
        from app.deps import build_deps
        from app.main import create_app

        self.deps = build_deps(self.settings, feeds=self.feeds, clock=self.clock)
        self.deps.transports = self.channels.transports()
        self.client = TestClient(create_app(self.deps), raise_server_exceptions=False)

    def check_now(self) -> dict:
        r = self.client.post("/refresh")
        assert r.status_code == (429 if r.json().get("refusal") else 200), r.text  # B11: a refusal is a 429
        return r.json()

    def next_day(self) -> dict:
        self.clock.advance(60 * 24)
        self.feeds.day = 2
        return self.check_now()

    def settings_with(self, **alerts) -> None:
        body = self.client.get("/settings").json()["settings"]
        body["alerts"] |= alerts
        assert self.client.put("/settings", json=body).status_code == 200

    def sent(self) -> list[dict]:
        """This run's alerts for the one local user, from the refresh result."""
        return self.client.get("/refresh").json()["last_result"]["alerts"]["default"]

    def log(self) -> list[dict]:
        return self.client.get("/alerts").json()["alerts"]


@pytest.fixture
def app(tmp_path, index_dir, index):
    return LiveAlerts(tmp_path, index_dir)


def pairs(entries: list[dict]) -> set[tuple[str, str]]:
    """(CVE, reason) for every alert in the entries, digests included."""
    return {(a["cve"], a["reason"]) for e in entries for a in e["alerts"]}


# --- B04.4: a refresh sends the right alerts on the user's channels -------------------------------------------------

def test_b04_4_day2_refresh_sends_the_new_kev_and_rescored_alerts(app):
    app.check_now()
    app.channels.ntfy.clear()
    app.channels.desktop.clear()
    reply = app.next_day()

    sent = reply["result"]["alerts"]["default"]
    assert {(OLD_TO_KEV, "kev"), (NEW_DAY2, "new"), (NEW_DAY1, "now_critical")} <= pairs(sent)
    assert all(e["kind"] == "alert" for e in sent)  # at most 5 (the default limit): one message each
    by = {(e["cve"], e["reason"]): e for e in sent}
    kev = by[(OLD_TO_KEV, "kev")]
    assert kev["title"] == "In CISA KEV: Langflow"
    assert kev["priority"] == 5  # the CVE's priority (urgent: in KEV) gives 5
    assert by[(NEW_DAY2, "new")]["priority"] == 3  # high severity, not internet-facing: normal priority
    assert kev["click"] == f"http://app.test/#cve={OLD_TO_KEV}"
    assert kev["body"].startswith(f"{OLD_TO_KEV} · ") and " · due 2026-11-05" in kev["body"]
    assert [(c["channel"], c["sent"], c["error"]) for c in kev["channels"]] == [("desktop", True, None),
                                                                              ("ntfy", True, None)]

    # the same messages went out on both channels, with no description text
    assert len(app.channels.ntfy) == len(app.channels.desktop) == len(sent)
    ntfy = {p["title"]: p for p in app.channels.ntfy}
    assert ntfy["In CISA KEV: Langflow"]["priority"] == 5
    assert ntfy["In CISA KEV: Langflow"]["click"] == f"http://app.test/#cve={OLD_TO_KEV}"
    assert not any(DESCRIPTION_WORDS in json.dumps(p) for p in app.channels.ntfy)
    assert not any(DESCRIPTION_WORDS in " ".join(args) for args in app.channels.desktop)


def test_b04_4_the_alerts_route_returns_the_log_newest_first_with_results_per_channel(app):
    app.check_now()
    sent = app.next_day()["result"]["alerts"]["default"]
    log = app.log()
    assert len(log) <= 20 and log[0]["at"] == "2026-10-15T09:00:00+00:00"
    assert log[:len(sent)] == sent  # one run on top in the order sent: KEV and new CVEs above the reminders
    assert log[0]["reason"] == "kev"
    assert {"at", "kind", "reason", "cve", "title", "body", "priority", "click", "alerts", "channels"} <= set(log[0])
    assert log[-1]["kind"] == "digest" and log[-1]["at"] == f"{DAY1}T09:00:00+00:00"  # day 1's digest, oldest


# --- B04.5: once per CVE and reason: a rerun or a restart sends nothing new -----------------------------------------

def test_b04_5_a_rerun_sends_nothing_new(app):
    app.check_now()
    app.next_day()
    count = len(app.channels.ntfy)
    app.clock.advance(10)  # past the 5 minutes; the feeds still say day 2
    assert app.check_now()["result"]["alerts"] == {"default": []}
    assert len(app.channels.ntfy) == count


def test_b04_5_a_restart_sends_nothing_new(app):
    app.check_now()
    app.next_day()
    count = len(app.channels.ntfy)
    app.start()
    app.clock.advance(10)
    assert app.check_now()["result"]["alerts"] == {"default": []}
    assert len(app.channels.ntfy) == count


def test_b04_5_overdue_comes_again_the_next_week(app):
    app.check_now()
    first = {a["cve"] for e in app.sent() for a in e["alerts"] if a["reason"] == "overdue"}
    app.clock.advance(60 * 24 * 7)  # a week later; nothing else changed
    again = {a["cve"] for e in app.check_now()["result"]["alerts"]["default"] for a in e["alerts"]
             if a["reason"] == "overdue"}
    assert first and first <= again


# --- B04.6: a failed channel is logged; the others still send -------------------------------------------------------

def test_b04_6_a_failed_channel_is_logged_with_its_error(app):
    app.check_now()
    app.channels.ntfy_fails = True
    reply = app.next_day()
    assert reply["result"]["ok"]  # a failed send never fails the refresh
    entry = app.log()[0]
    ntfy = next(c for c in entry["channels"] if c["channel"] == "ntfy")
    desktop = next(c for c in entry["channels"] if c["channel"] == "desktop")
    assert not ntfy["sent"] and "network down" in ntfy["error"] and ntfy["error_code"] == "notify_failed"
    assert desktop["sent"] and desktop["error"] is None


def test_b04_6_a_channel_that_isnt_set_up_is_logged_as_such(app):
    app.settings_with(channels=["email"])  # no SMTP in this environment
    app.check_now()
    (email,) = app.log()[0]["channels"]
    assert (email["channel"], email["sent"], email["error_code"]) == ("email", False, "not_configured")


# --- B04.7: more than digest_over alerts in one run become one digest -------------------------------------------------

def test_b04_7_a_busy_run_is_one_digest(app):
    reply = app.check_now()  # day 1: the new Langflow CVE, plus the snapshot's overdue and due-soon CVEs
    (entry,) = reply["result"]["alerts"]["default"]
    assert entry["kind"] == "digest" and entry["reason"] is None and entry["cve"] is None
    assert (NEW_DAY1, "new") in pairs([entry]) and len(entry["alerts"]) > 5
    assert entry["title"] == f"{len(entry['alerts'])} alerts for your watchlist"
    assert entry["click"] == "http://app.test/cves"
    assert len(app.channels.ntfy) == len(app.channels.desktop) == 1


def test_b04_7_the_limit_is_the_users_setting(app):
    app.check_now()
    app.settings_with(digest_over=1)
    (entry,) = app.next_day()["result"]["alerts"]["default"]
    assert entry["kind"] == "digest" and {(OLD_TO_KEV, "kev"), (NEW_DAY2, "new")} <= pairs([entry])


# --- B04.8: quiet hours hold alerts, then send them as one digest ---------------------------------------------------

def test_b04_8_quiet_hours_hold_alerts_and_send_one_digest_when_they_end(app):
    app.check_now()
    app.settings_with(quiet_start="08:00", quiet_end="10:00")  # the day-2 check runs at 09:00 UTC
    count = len(app.channels.ntfy)
    held = app.next_day()["result"]["alerts"]["default"]
    assert held and all(e["kind"] == "held" and e["channels"] == [] for e in held)
    assert len(app.channels.ntfy) == count and app.log()[0]["at"] == f"{DAY1}T09:00:00+00:00"  # nothing sent

    app.clock.advance(90)  # 10:30, after quiet hours: the next run sends what was held
    (entry,) = app.check_now()["result"]["alerts"]["default"]
    assert entry["kind"] == "digest" and pairs([entry]) == pairs(held)
    assert len(app.channels.ntfy) == count + 1 and app.log()[0] == entry


def test_b04_8_a_scheduled_tick_that_isnt_due_still_sends_what_quiet_hours_held(app):
    from app.refresh import run_scheduled

    app.check_now()
    app.settings_with(quiet_start="08:00", quiet_end="10:00")
    held = app.next_day()["result"]["alerts"]["default"]
    count = len(app.channels.ntfy)
    app.clock.advance(90)  # 10:30: quiet hours are over, but the 6-hour schedule isn't due
    assert run_scheduled(app.deps.refresher, 6) is None
    entry = app.log()[0]
    assert entry["kind"] == "digest" and pairs([entry]) == pairs(held) and len(app.channels.ntfy) == count + 1


# --- B04.9: alerts off stops sending, not the refresh ---------------------------------------------------------------

def test_b04_9_alerts_off_stops_sending_but_not_the_refresh(app):
    app.settings_with(enabled=False)
    reply = app.check_now()
    assert reply["result"]["ok"] and reply["result"]["new_cves"] == [NEW_DAY1]
    assert reply["result"]["alerts"] == {"default": []}
    assert app.channels.ntfy == [] and app.channels.desktop == [] and app.log() == []


# --- B04.10: the fake feeds' reset (the browser check) clears the alerts too ----------------------------------------

def test_b04_10_the_live_reset_clears_the_alerts_so_check_now_alerts_again(app):
    app.check_now()
    assert app.client.post("/refresh/reset", json={"confirm": "reset"}).json() == {"reset": True}
    assert app.log() == []
    assert app.check_now()["result"]["alerts"]["default"]  # the same alerts again


def test_b04_10_test_alerts_keep_their_shape_with_results_per_channel(app):
    r = app.client.post("/alerts/test", json={"channel": "ntfy"})
    assert r.status_code == 200
    entry = app.log()[0]
    assert entry["kind"] == "test" and [(c["channel"], c["sent"]) for c in entry["channels"]] == [("ntfy", True)]
    assert (entry["channel"], entry["sent"]) == ("ntfy", True)  # the Settings page's fields stay

"""A failed alert send is tried again on the next check (B41, #91), through the HTTP API like test_alert_delivery.

ntfy and the desktop channel run on fake transports: nothing is ever sent. The first check (day 1) sends one alert,
the new Langflow CVE (NEW_DAY1); with ntfy down it reaches the desktop only, and ntfy's send is retried.
"""
import json

import pytest

from test_alert_delivery import LiveAlerts, pairs
from test_refresh import DAY1, NEW_DAY1


@pytest.fixture
def app(tmp_path, index_dir, index):
    return LiveAlerts(tmp_path, index_dir)


def ntfy_of(entry: dict) -> dict:
    return next(c for c in entry["channels"] if c["channel"] == "ntfy")


def first_check_with_ntfy_down(app) -> dict:
    app.channels.ntfy_fails = True
    (entry,) = app.check_now()["result"]["alerts"]["default"]
    app.channels.ntfy_fails = False
    return entry


def next_check(app, minutes: int = 10) -> list[dict]:
    """A check later the same day (past the 5-minute rule): the feeds still say day 1, so nothing new."""
    app.clock.advance(minutes)
    return app.check_now()["result"]["alerts"]["default"]


# --- B41.1: the failed channel is tried again on the next check, and only that channel -------------------------------

def test_b41_1_a_failed_ntfy_send_is_retried_on_the_next_check_on_ntfy_only(app):
    first_check_with_ntfy_down(app)
    desktop_before = len(app.channels.desktop)

    retried = next_check(app)

    assert [p["title"] for p in app.channels.ntfy] == ["New CVE: Langflow"]
    assert len(app.channels.desktop) == desktop_before  # the desktop got it the first time: not sent again
    (entry,) = retried  # the run's result carries the retry, with the retried channel only
    assert pairs([entry]) == {(NEW_DAY1, "new")} and entry["retry"] is True
    assert [(c["channel"], c["sent"], c["tries"]) for c in entry["channels"]] == [("ntfy", True, 2)]


def test_b41_1_the_log_entry_shows_the_retry_in_place(app):
    first_check_with_ntfy_down(app)
    next_check(app)

    (entry,) = app.log()  # still one entry for the one message
    assert entry["at"] == f"{DAY1}T09:00:00+00:00"
    ntfy = ntfy_of(entry)
    assert (ntfy["sent"], ntfy["error"], ntfy["tries"], ntfy["retry"]) == (True, None, 2, False)
    desktop = next(c for c in entry["channels"] if c["channel"] == "desktop")
    assert desktop["sent"] and "tries" not in desktop


def test_b41_1_a_failure_says_it_will_be_tried_again(app):
    first_check_with_ntfy_down(app)
    ntfy = ntfy_of(app.log()[0])
    assert (ntfy["sent"], ntfy["tries"], ntfy["retry"]) == (False, 1, True) and "network down" in ntfy["error"]


def test_b41_1_a_sent_retry_is_not_sent_again(app):
    first_check_with_ntfy_down(app)
    next_check(app)
    assert next_check(app) == [] and len(app.channels.ntfy) == 1


# --- B41.2: at most 3 tries in all, then it stays failed -------------------------------------------------------------

def test_b41_2_it_stops_after_three_tries(app):
    first_check_with_ntfy_down(app)
    app.channels.ntfy_fails = True
    second, third = next_check(app), next_check(app)
    assert [ntfy_of(e)["tries"] for e in second + third] == [2, 3]
    assert next_check(app) == []  # no fourth try

    ntfy = ntfy_of(app.log()[0])
    assert (ntfy["sent"], ntfy["tries"], ntfy["retry"]) == (False, 3, False) and "network down" in ntfy["error"]
    assert app.client.get("/refresh/runs").json()["runs"][1]["alerts_failed"] == 1  # the third try's run


# --- B41.3: an alert no longer true is dropped, not sent late --------------------------------------------------------

def test_b41_3_a_retry_is_dropped_when_the_cve_was_fixed_meanwhile(app):
    first_check_with_ntfy_down(app)
    assert app.client.patch(f"/cves/{NEW_DAY1}", json={"status": "fixed"}).status_code == 200

    assert next_check(app) == [] and app.channels.ntfy == []
    ntfy = ntfy_of(app.log()[0])
    assert (ntfy["sent"], ntfy["tries"], ntfy["retry"], ntfy["dropped"]) == (False, 1, False, True)
    assert next_check(app) == []


def test_b41_3_a_retry_is_dropped_when_its_channel_is_no_longer_picked(app):
    first_check_with_ntfy_down(app)
    app.settings_with(channels=["desktop"])
    assert next_check(app) == [] and app.channels.ntfy == []
    assert ntfy_of(app.log()[0])["dropped"] is True


@pytest.mark.parametrize("reason, row_args, key, kept", [
    ("kev", {}, "CVE-1|kev", True),
    ("kev", {"status": "accepted"}, "CVE-1|kev", False),
    ("new", {"status": "fixed"}, "CVE-1|new", False),
    ("new", {"verdict": "not_affected"}, "CVE-1|new", False),
    ("kev_recheck", {"status": "fixed"}, "CVE-1|kev_recheck", True),  # about a fixed CVE: still true while fixed
    ("kev_recheck", {}, "CVE-1|kev_recheck", False),  # reopened since: the recheck is moot
    ("now_critical", {"severity": "CRITICAL"}, "CVE-1|now_critical", True),
    ("due_soon", {"due_date": "2026-10-16"}, "CVE-1|due_soon", True),
    ("due_soon", {"due_date": "2026-10-14", "overdue": True}, "CVE-1|due_soon", False),  # overdue now: its own alert
    ("overdue", {"due_date": "2026-10-01", "overdue": True}, "CVE-1|overdue|2026-W42", True),
    ("overdue", {"due_date": "2026-10-01", "overdue": True}, "CVE-1|overdue|2026-W41", False),  # last week's
])
def test_b41_3_still_true_keeps_only_what_the_rules_would_still_give(reason, row_args, key, kept):
    from app.alerts import still_true
    from app.app_settings import AlertSettings
    from test_alerts import AS_OF, row

    alert = {"cve": "CVE-1", "reason": reason, "key": key}
    assert still_true([alert], {"CVE-1": row(**row_args)}, AlertSettings(), AS_OF) == ([alert] if kept else [])


def test_b41_3_an_unwatched_cve_is_not_still_true():
    from app.alerts import still_true
    from app.app_settings import AlertSettings
    from test_alerts import AS_OF

    assert still_true([{"cve": "CVE-1", "reason": "kev", "key": "CVE-1|kev"}], {}, AlertSettings(), AS_OF) == []


# --- B41.4: quiet hours hold retries like any alert ------------------------------------------------------------------

def test_b41_4_quiet_hours_hold_the_retry_until_they_end(app):
    first_check_with_ntfy_down(app)  # 09:00
    app.settings_with(quiet_start="09:05", quiet_end="10:00")
    assert next_check(app) == [] and app.channels.ntfy == []  # 09:10, quiet
    (entry,) = next_check(app, 60)  # 10:10: quiet hours are over
    assert ntfy_of(entry)["sent"] and ntfy_of(entry)["tries"] == 2


def test_b41_3_a_digest_is_retried_without_the_alerts_no_longer_true(app):
    app.check_now()
    app.channels.ntfy_fails = True
    app.clock.advance(60 * 24 * 7)  # a week later: the overdue reminders, as one digest
    (digest,) = app.check_now()["result"]["alerts"]["default"]
    app.channels.ntfy_fails = False
    fixed = digest["alerts"][0]["cve"]
    assert app.client.patch(f"/cves/{fixed}", json={"status": "fixed"}).status_code == 200
    desktop_before = len(app.channels.desktop)
    app.channels.ntfy.clear()  # the first check's alert

    (entry,) = next_check(app)
    assert entry["kind"] == "digest" and pairs([entry]) == pairs([digest]) - {(fixed, "overdue")}
    assert entry["title"] == f"{len(digest['alerts']) - 1} alerts for your watchlist"
    assert [p["title"] for p in app.channels.ntfy] == [entry["title"]]
    assert len(app.channels.desktop) == desktop_before


# --- B41.5: only a send that was tried is tried again ----------------------------------------------------------------

def test_b41_5_a_channel_that_isnt_set_up_is_not_retried(app):
    app.settings_with(channels=["email"])  # no SMTP in this environment
    app.check_now()
    (email,) = app.log()[0]["channels"]
    assert email["error_code"] == "not_configured" and "retry" not in email
    assert next_check(app) == []


# --- B41.6: a state saved before B41 loads unchanged, and its old failures are never resent ---------------------------

# The alerts log and the keys as B04-B38 saved them: a failed ntfy send, with no `id`, `tries` or `retry`
OLD_FAILED = {"at": f"{DAY1}T08:00:00+00:00", "kind": "alert", "cve": NEW_DAY1, "reason": "new",
              "alerts": [{"cve": NEW_DAY1, "reason": "new", "priority": 3}], "title": "New CVE: Langflow",
              "body": f"{NEW_DAY1} · high 8.1", "priority": 3, "tags": ["new", "langflow"],
              "click": f"http://app.test/cves/{NEW_DAY1}",
              "channels": [{"channel": "desktop", "sent": True, "error": None, "error_code": None},
                           {"channel": "ntfy", "sent": False, "error": "Couldn't reach ntfy at https://ntfy.sh: down",
                            "error_code": "notify_failed"}]}
OLD_TEST = {"at": f"{DAY1}T07:00:00+00:00", "channel": "ntfy", "sent": False, "error": "down",
            "error_code": "notify_failed", "title": "Test alert", "body": "b", "priority": 3, "tags": [], "click": None}


def test_b41_6_a_state_of_todays_shape_loads_unchanged_and_old_failures_are_not_resent(tmp_path, index_dir, index):
    state = {"alerted": {f"{NEW_DAY1}|new": f"{DAY1}T08:00:00+00:00"},
             "alerts_log": [OLD_FAILED, OLD_TEST],
             "new_since_check": {"at": f"{DAY1}T08:00:00+00:00", "cves": [NEW_DAY1], "pending": []}}
    (tmp_path / "state.json").write_text(json.dumps(state))
    app = LiveAlerts(tmp_path, index_dir)
    before = app.log()
    assert before[0] == OLD_FAILED

    assert app.check_now()["result"]["alerts"] == {"default": []}
    assert next_check(app) == [] and app.channels.ntfy == []
    assert app.log() == before

"""ntfy.sh answers 429 to a shared address (B55, #101). Check ids: B55.n.

ntfy.sh limits each IP address, and Cloud Run's outgoing addresses are shared with other customers, so the live app's
sends were refused with HTTP 429. Now a 429 is tried again inside the same send, with a short wait, and ntfy's own
reply (its code and error text) is in the error, so a rate limit can be told from a ban.

Fake openers and a fake sleep only: nothing reaches ntfy.sh and nothing really waits.
"""
import io
import json
import urllib.error

import pytest

from app.notify import NotifyError, NtfyNotifier, WaitBudget
from tests.test_access import auth_settings  # noqa: F401  (the fixture: sign-in on, an ntfy topic)

MSG = {"title": "In CISA KEV: Langflow", "body": "CVE-2025-3248 · critical 9.8", "priority": 5,
       "tags": ["kev", "langflow"], "click": None}
LIMITED = {"code": 42901, "http": 429, "error": "limit reached: too many requests; increase your limits with a paid plan"}


class Resp:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass


def http_error(code: int, body: dict | str, headers: dict | None = None):
    raw = body if isinstance(body, str) else json.dumps(body)
    return urllib.error.HTTPError("https://ntfy.sh/", code, "Too Many Requests", headers or {}, io.BytesIO(raw.encode()))


class Ntfy:
    """A fake ntfy server: answers each POST with the next reply in `replies` (an HTTPError is raised)."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.posts: list[dict] = []

    def __call__(self, req, timeout):
        self.posts.append(json.loads(req.data))
        reply = self.replies.pop(0) if self.replies else Resp()
        if isinstance(reply, Exception):
            raise reply
        return reply


class Clock:
    def __init__(self):
        self.waits: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)


def notifier(ntfy, clock, seconds=60.0, topic="t0p1c-secret", token="tk_secret"):
    return NtfyNotifier("https://ntfy.sh", topic, token, opener=ntfy, wait=WaitBudget(seconds, clock.sleep))


# --- B55.1: a 429 is tried again, and then it's sent -----------------------------------------------------------------

def test_b55_1_a_429_is_tried_again_and_then_sent():
    ntfy, clock = Ntfy(http_error(429, LIMITED)), Clock()
    notifier(ntfy, clock).send(**MSG)
    assert len(ntfy.posts) == 2 and ntfy.posts[0] == ntfy.posts[1]
    assert len(clock.waits) == 1 and clock.waits[0] > 0


# --- B55.2: three 429s fail, saying in plain words what ntfy said ------------------------------------------------------

def test_b55_2_three_429s_fail_with_ntfys_code_and_text():
    ntfy, clock = Ntfy(*[http_error(429, LIMITED)] * 3), Clock()
    with pytest.raises(NotifyError) as e:
        notifier(ntfy, clock).send(**MSG)
    assert len(ntfy.posts) == 3 and len(clock.waits) == 2
    msg = e.value.message
    assert msg.startswith("ntfy.sh is limiting this server's address: try again later")
    assert "42901" in msg and "limit reached: too many requests" in msg
    assert "tries" not in msg  # B41's pill counts the next-check tries; a second count would muddle it
    assert "t0p1c-secret" not in msg and "tk_secret" not in msg


def test_b55_2_ntfys_reply_is_cut_and_never_carries_the_topic_or_token():
    noisy = {"code": 42901, "http": 429, "error": "topic t0p1c-secret, token tk_secret: " + "x" * 500}
    with pytest.raises(NotifyError) as e:
        notifier(Ntfy(*[http_error(429, noisy)] * 3), Clock()).send(**MSG)
    assert "t0p1c-secret" not in e.value.message and "tk_secret" not in e.value.message
    assert len(e.value.message) < 400


def test_b55_2_a_reply_that_isnt_json_is_quoted_as_text():
    with pytest.raises(NotifyError) as e:
        notifier(Ntfy(*[http_error(429, "<html>slow down</html>")] * 3), Clock()).send(**MSG)
    assert "slow down" in e.value.message


# --- B55.3: only a 429 is tried again ------------------------------------------------------------------------------------

def test_b55_3_a_500_isnt_tried_again_and_says_what_ntfy_said():
    ntfy, clock = Ntfy(http_error(500, {"code": 50001, "http": 500, "error": "internal server error"})), Clock()
    with pytest.raises(NotifyError) as e:
        notifier(ntfy, clock).send(**MSG)
    assert len(ntfy.posts) == 1 and clock.waits == []
    assert "HTTP 500" in e.value.message and "50001: internal server error" in e.value.message


def test_b55_3_an_unreachable_server_isnt_tried_again_here():
    ntfy, clock = Ntfy(OSError("network down")), Clock()
    with pytest.raises(NotifyError, match="network down"):
        notifier(ntfy, clock).send(**MSG)
    assert len(ntfy.posts) == 1 and clock.waits == []  # B41's next-check retry handles it


# --- B55.4: Retry-After is honoured, and capped ------------------------------------------------------------------------

def test_b55_4_retry_after_is_honoured():
    ntfy, clock = Ntfy(http_error(429, LIMITED, {"Retry-After": "4"})), Clock()
    notifier(ntfy, clock).send(**MSG)
    assert clock.waits == [4.0]


def test_b55_4_a_long_retry_after_is_capped():
    ntfy, clock = Ntfy(http_error(429, LIMITED, {"Retry-After": "3600"})), Clock()
    notifier(ntfy, clock).send(**MSG)
    assert clock.waits == [30.0]


def test_b55_4_a_retry_after_that_isnt_seconds_falls_back_to_the_backoff():
    ntfy, clock = Ntfy(http_error(429, LIMITED, {"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"})), Clock()
    notifier(ntfy, clock).send(**MSG)
    assert clock.waits == [10.0]


# --- B55.5: the budget: a test send never waits longer than its cap ------------------------------------------------------

def test_b55_5_the_waits_never_pass_the_budget():
    ntfy, clock = Ntfy(*[http_error(429, LIMITED)] * 3), Clock()
    with pytest.raises(NotifyError, match="limiting"):
        notifier(ntfy, clock, seconds=4).send(**MSG)
    assert clock.waits == [4] and len(ntfy.posts) == 2  # one wait of 4 s, then the budget is spent


def test_b55_5_with_the_budget_spent_it_stops_at_once():
    budget = WaitBudget(4, Clock().sleep)
    first = Ntfy(*[http_error(429, LIMITED)] * 3)
    with pytest.raises(NotifyError):
        NtfyNotifier("https://ntfy.sh", "t", opener=first, wait=budget).send(**MSG)
    second = Ntfy(*[http_error(429, LIMITED)] * 3)  # the same run's next message shares the budget
    with pytest.raises(NotifyError, match="limiting"):
        NtfyNotifier("https://ntfy.sh", "t", opener=second, wait=budget).send(**MSG)
    assert len(second.posts) == 1


# --- Through the HTTP API (seam 1): the shared fake channels, with ntfy answering 429 --------------------------------

def test_b55_6_a_test_send_waits_a_few_seconds_at_most_then_says_why(settings, knowledge, index):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.main import create_app
    from app.notify import TEST_SEND_WAIT
    from tests.test_alert_delivery import Channels

    channels = Channels()
    channels.ntfy_429s = 99
    deps = build_deps(replace(settings, ntfy_topic="t0p1c-secret"), knowledge=knowledge, index=index)
    deps.transports = channels.transports()
    c = TestClient(create_app(deps), raise_server_exceptions=False)
    r = c.post("/alerts/test", json={"channel": "ntfy"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "notify_failed"
    assert r.json()["error"]["message"].startswith("ntfy.sh is limiting this server's address: try again later")
    assert "42901" in r.json()["error"]["message"] and "t0p1c-secret" not in r.json()["error"]["message"]
    assert 0 < sum(channels.waits) <= TEST_SEND_WAIT <= 5
    assert c.get("/alerts").json()["alerts"][0]["error"] == r.json()["error"]["message"]  # Delivery's words


def test_b55_6_a_test_send_after_one_429_is_sent(settings, knowledge, index):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.main import create_app
    from tests.test_alert_delivery import Channels

    channels = Channels()
    channels.ntfy_429s = 1
    deps = build_deps(replace(settings, ntfy_topic="t0p1c"), knowledge=knowledge, index=index)
    deps.transports = channels.transports()
    r = TestClient(create_app(deps), raise_server_exceptions=False).post("/alerts/test", json={"channel": "ntfy"})
    assert r.status_code == 200 and r.json()["sent"] is True and len(channels.ntfy) == 1


def test_b55_7_a_refresh_alert_after_a_429_is_sent_in_the_same_check(tmp_path, index_dir, index):
    from tests.test_alert_delivery import LiveAlerts

    app = LiveAlerts(tmp_path, index_dir)
    app.channels.ntfy_429s = 1
    app.check_now()
    ntfy = next(c for c in app.log()[0]["channels"] if c["channel"] == "ntfy")
    assert ntfy["sent"] and ntfy["error"] is None and not ntfy.get("retry")
    assert app.channels.waits == [10.0]


def test_b55_7_a_refresh_waits_at_most_its_budget_in_all(tmp_path, index_dir, index):
    from app.notify import RUN_WAIT
    from tests.test_alert_delivery import LiveAlerts

    app = LiveAlerts(tmp_path, index_dir)
    app.channels.ntfy_429s = 999
    app.check_now()
    ntfy = next(c for c in app.log()[0]["channels"] if c["channel"] == "ntfy")
    assert not ntfy["sent"] and "is limiting this server's address" in ntfy["error"] and ntfy["retry"]  # B41 still
    assert sum(app.channels.waits) <= RUN_WAIT <= 90


def test_b55_8_an_access_request_alert_is_tried_again_after_a_429(auth_settings, knowledge, index):
    from tests.test_access import Patch

    patch = Patch(auth_settings, knowledge, index)
    patch.channels.ntfy_429s = 1
    assert patch.request().status_code == 200
    assert [m["title"] for m in patch.alerts()] == ["New access request"]
    assert patch.channels.waits == [10.0]


def test_b55_8_a_failed_access_request_alert_logs_ntfys_reply_without_the_topic(auth_settings, knowledge, index,
                                                                                caplog):
    from tests.test_access import Patch

    patch = Patch(auth_settings, knowledge, index)
    patch.channels.ntfy_429s = 99
    with caplog.at_level("WARNING", logger="app"):
        assert patch.request().json()["status"] == "waiting"  # the request still waits on the Requests card
    lines = [r.getMessage() for r in caplog.records if "ntfy" in r.getMessage()]
    assert lines and "42901" in lines[0] and "limit reached" in lines[0]
    assert auth_settings.ntfy_topic not in " ".join(lines)

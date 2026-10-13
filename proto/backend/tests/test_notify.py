"""N1–N4: notification channels, each against a fake transport. Nothing is really sent."""
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.notify import (DesktopNotifier, EmailNotifier, NotifyError, NtfyNotifier, channel_status, format_alert,
                        mask_email)

MSG = {"title": "In CISA KEV: Langflow", "body": "CVE-2025-3248 · critical 9.8 · remediation due 2025-05-26",
       "priority": 5, "tags": ["kev", "langflow"], "click": "http://localhost:5173/#cve=CVE-2025-3248"}


def test_n1_ntfy_posts_json_to_the_root():
    sent = {}

    class Resp:
        status = 200
        def __enter__(self): return self
        def __exit__(self, *a): pass

    def opener(req, timeout):
        sent.update(url=req.full_url, body=json.loads(req.data), auth=req.get_header("Authorization"))
        return Resp()
    NtfyNotifier("https://ntfy.example", "t0p1c", "tk_x", opener=opener).send(**MSG)
    assert sent["url"] == "https://ntfy.example/" and sent["auth"] == "Bearer tk_x"
    assert sent["body"] == {"topic": "t0p1c", "title": MSG["title"], "message": MSG["body"], "priority": 5,
                            "tags": ["kev", "langflow"], "click": MSG["click"]}


def test_n1_email_message():
    log = {}

    class FakeSMTP:
        def __init__(self, host, port): log["server"] = (host, port)
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def starttls(self): log["tls"] = True
        def login(self, u, p): log["login"] = u
        def send_message(self, m): log["msg"] = m
    s = replace(Settings(), smtp_host="smtp.example", smtp_user="me@example.org", smtp_password="pw",
                email_to="me@example.org")
    EmailNotifier(s, smtp_factory=FakeSMTP).send(**MSG)
    m = log["msg"]
    assert log["server"] == ("smtp.example", 587) and log["tls"] and log["login"] == "me@example.org"
    assert m["Subject"] == "[LLM security] In CISA KEV: Langflow" and m["X-Priority"] == "1"
    assert MSG["click"] in m.get_content()


def test_n1_desktop_uses_an_argument_list():
    calls = []
    DesktopNotifier("/usr/bin/notify-send", runner=lambda args, **kw: calls.append(args)).send(**MSG)
    args = calls[0]
    assert args[0] == "/usr/bin/notify-send" and "--urgency=critical" in args and args[-2] == MSG["title"]
    hostile = dict(MSG, title='"; rm -rf ~; echo "')
    DesktopNotifier("/usr/bin/notify-send", runner=lambda args, **kw: calls.append(args)).send(**hostile)
    assert calls[1][-2] == hostile["title"]  # passed as one argument, never through a shell


def test_n1_failures_become_notify_errors():
    def boom(*a, **kw):
        raise OSError("no display")
    with pytest.raises(NotifyError, match="desktop notification failed"):
        DesktopNotifier("/usr/bin/notify-send", runner=boom).send(**MSG)


def test_n2_status_never_leaks_secrets():
    s = replace(Settings(), smtp_host="smtp.example", smtp_password="hunter2", email_to="deryk@example.org",
                ntfy_topic="secret-topic-123", ntfy_token="tk_secret")
    text = json.dumps(channel_status(s))
    assert "hunter2" not in text and "secret-topic-123" not in text and "tk_secret" not in text
    assert "d***@example.org" in text and mask_email("x") == "***"


def test_n2_unconfigured_channel_is_400_and_logged(deps):
    c = TestClient(create_app(deps))
    r = c.post("/alerts/test", json={"channel": "email"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_configured" and "SMTP_HOST" in r.json()["error"]["message"]


def test_n3_sent_alert_is_logged(deps, monkeypatch):
    sent = []
    monkeypatch.setattr("app.notify.desktop_command", lambda: "/usr/bin/notify-send")
    monkeypatch.setattr("app.notify.DesktopNotifier.send", lambda self, **m: sent.append(m))
    c = TestClient(create_app(deps))
    r = c.post("/alerts/test", json={"channel": "desktop"}).json()
    assert r["sent"] is True and sent and sent[0]["title"].startswith("Test · In CISA KEV")
    log = c.get("/alerts").json()["alerts"][0]
    assert (log["channel"], log["sent"], log["error"]) == ("desktop", True, None)


def test_n4_alert_links_into_the_app(shared):
    k, _ = shared
    msg = format_alert(k.cves.get("CVE-2025-3248"), "kev", k, "http://localhost:5173")
    assert msg["click"] == "http://localhost:5173/#cve=CVE-2025-3248"

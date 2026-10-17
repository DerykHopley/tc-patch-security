"""Notifiers, each against a fake transport: nothing is really sent. Moved from proto (N1-N4). Check ids: A13.n."""
import json
from dataclasses import replace

import pytest

from app.config import Settings
from app.notify import DesktopNotifier, EmailNotifier, NotifyError, NtfyNotifier, format_alert, mask_email

# The link's address is one a phone can reach: the links of an app on localhost are left out (B26, test_b26_5)
MSG = {"title": "In CISA KEV: Langflow", "body": "CVE-2025-3248 · critical 9.8 · due 2025-05-26",
       "priority": 5, "tags": ["kev", "langflow"], "click": "https://patch.example.test/#cve=CVE-2025-3248"}


def test_a13_3_ntfy_posts_json_to_the_server_root():
    sent = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def opener(req, timeout):
        sent.update(url=req.full_url, body=json.loads(req.data), auth=req.get_header("Authorization"))
        return Resp()

    NtfyNotifier("https://ntfy.example", "t0p1c", "tk_x", opener=opener).send(**MSG)
    assert sent["url"] == "https://ntfy.example/" and sent["auth"] == "Bearer tk_x"
    assert sent["body"] == {"topic": "t0p1c", "title": MSG["title"], "message": MSG["body"], "priority": 5,
                            "tags": ["kev", "langflow"], "click": MSG["click"]}


def test_a13_3_ntfy_error_status_is_a_notify_error():
    class Resp:
        status = 403

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    with pytest.raises(NotifyError, match="HTTP 403"):
        NtfyNotifier("https://ntfy.example", "t", opener=lambda req, timeout: Resp()).send(**MSG)


def test_a13_3_email_message():
    log = {}

    class FakeSMTP:
        def __init__(self, host, port):
            log["server"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def starttls(self):
            log["tls"] = True

        def login(self, user, password):
            log["login"] = user

        def send_message(self, m):
            log["msg"] = m

    s = replace(Settings(), smtp_host="smtp.example", smtp_user="me@example.org", smtp_password="pw",
                alert_email_to="me@example.org")
    EmailNotifier(s, smtp_factory=FakeSMTP).send(**MSG)
    m = log["msg"]
    assert log["server"] == ("smtp.example", 587) and log["tls"] and log["login"] == "me@example.org"
    assert m["Subject"] == "[LLM security] In CISA KEV: Langflow" and m["X-Priority"] == "1"
    assert m["From"] == "me@example.org" and m["To"] == "me@example.org"
    assert MSG["click"] in m.get_content()


def test_a13_3_desktop_uses_an_argument_list_never_a_shell():
    calls = []
    DesktopNotifier("/usr/bin/notify-send", runner=lambda args, **kw: calls.append(args)).send(**MSG)
    args = calls[0]
    assert args[0] == "/usr/bin/notify-send" and "--urgency=critical" in args and args[-2] == MSG["title"]
    hostile = dict(MSG, title='"; rm -rf ~; echo "')
    DesktopNotifier("/usr/bin/notify-send", runner=lambda args, **kw: calls.append(args)).send(**hostile)
    assert calls[1][-2] == hostile["title"]  # one argument, never through a shell


def test_a13_3_desktop_failure_is_a_notify_error():
    def boom(*a, **kw):
        raise OSError("no display")

    with pytest.raises(NotifyError, match="desktop notification failed"):
        DesktopNotifier("/usr/bin/notify-send", runner=boom).send(**MSG)


def test_a13_3_email_is_masked():
    assert mask_email("deryk@example.org") == "d***@example.org"
    assert mask_email("x") == "***"


def test_a13_4_alert_priority_and_possible_match(knowledge):
    critical = knowledge.cves.get("CVE-2024-8309")
    assert format_alert(critical, "new", knowledge)["priority"] == 4  # new and critical
    kev = format_alert(knowledge.cves.get("CVE-2025-3248"), "kev", knowledge)
    assert kev["priority"] == 5 and kev["title"] == "In CISA KEV: Langflow"
    assert kev["body"].endswith(" · KEV deadline 2025-05-26")  # no due date given: CISA's date, named as such
    mine = format_alert(knowledge.cves.get("CVE-2025-3248"), "kev", knowledge,
                        due={"due_date": "2025-06-01", "no_fix": False})
    assert mine["body"].endswith(" · due 2025-06-01") and "KEV deadline" not in mine["body"]
    no_fix = format_alert(critical, "new", knowledge, due={"due_date": "2025-07-01", "no_fix": True})
    assert no_fix["body"].endswith(" · decide by 2025-07-01")
    guessed = next(c for c in knowledge.cves.all() if c.get("product_source") == "text")
    assert format_alert(guessed, "new", knowledge)["body"].endswith("possible match")

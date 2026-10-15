"""Settings page API (seam 1): alert rules, channels, test alerts, the alerts log, reset. Check ids: A13.n, from #15.

No test sends anything: the senders (SMTP, ntfy, desktop command) are fakes passed in through `deps.transports`.
"""
import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

DEFAULT_WATCHLIST = ["langchain", "langflow", "litellm", "ollama", "open-webui"]


def make_client(settings, knowledge, **transports):
    from app.deps import build_deps
    from app.main import create_app
    from app.notify import Transports

    deps = build_deps(settings, knowledge=knowledge)
    deps.transports = Transports(**transports)
    return TestClient(create_app(deps), raise_server_exceptions=False), deps


def no_desktop():
    return None


# --- A13.1: defaults from the environment, saved values override, validated, old files load ----------------------

def test_a13_1_defaults_when_nothing_is_saved(client):
    s = client.get("/settings").json()["settings"]["alerts"]
    assert s == {"enabled": True, "min_severity": "HIGH", "kev": True, "kev_recheck": True, "unscored": True,
                 "now_critical": True, "digest_over": 5, "schedule_hours": 6, "schedule_paused": False,
                 "quiet_start": None, "quiet_end": None, "channels": ["desktop"]}


def test_a13_1_channels_set_up_in_the_environment_are_on_by_default(settings, knowledge):
    env = replace(settings, ntfy_topic="t0p1c", smtp_host="smtp.example", alert_email_to="me@example.org")
    c, _ = make_client(env, knowledge)
    assert c.get("/settings").json()["settings"]["alerts"]["channels"] == ["desktop", "email", "ntfy"]


def test_a13_1_saved_values_override_the_defaults_and_survive_a_restart(settings, knowledge, client):
    body = client.get("/settings").json()["settings"]
    body["alerts"] |= {"min_severity": "CRITICAL", "schedule_hours": 12, "quiet_start": "22:00", "quiet_end": "07:00",
                       "channels": []}
    r = client.put("/settings", json=body)
    assert r.status_code == 200 and r.json()["settings"]["alerts"]["min_severity"] == "CRITICAL"
    env = replace(settings, ntfy_topic="t0p1c")  # a new default doesn't beat a saved choice
    again, _ = make_client(env, knowledge)
    alerts = again.get("/settings").json()["settings"]["alerts"]
    assert (alerts["min_severity"], alerts["schedule_hours"], alerts["quiet_start"], alerts["channels"]) == (
        "CRITICAL", 12, "22:00", [])


@pytest.mark.parametrize("bad", [
    {"schedule_hours": 5}, {"quiet_start": "25:00"}, {"quiet_end": "7pm"}, {"digest_over": 0}, {"digest_over": 51},
    {"min_severity": "SEVERE"}, {"channels": ["pager"]}, {"enabled": "maybe"},
])
def test_a13_1_bad_values_are_400(client, bad):
    body = client.get("/settings").json()["settings"]
    body["alerts"] |= bad
    r = client.put("/settings", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


def test_a13_1_a_state_file_without_settings_still_loads(settings, client):
    settings.state_path.write_text(json.dumps({"watchlist": ["ollama"], "statuses": {}}))
    assert client.get("/settings").json()["settings"]["alerts"]["min_severity"] == "HIGH"
    assert client.get("/alerts").json() == {"alerts": []}


def test_a13_1_a_partly_saved_part_is_filled_from_the_defaults(settings, client):
    settings.state_path.write_text(json.dumps({"watchlist": [], "statuses": {}, "settings": {"alerts": {"kev": False}}}))
    alerts = client.get("/settings").json()["settings"]["alerts"]
    assert alerts["kev"] is False and alerts["digest_over"] == 5


def test_a13_1_saving_keeps_the_watchlist_statuses_and_parts_saved_by_other_pages(settings, client):
    settings.state_path.write_text(json.dumps({
        "watchlist": ["ollama"], "statuses": {"CVE-2024-37032": "fixed"}, "usage": {"ollama": "library"},
        "settings": {"alerts": {}, "later_part": {"x": 3}}}))
    body = client.get("/settings").json()["settings"]
    assert client.put("/settings", json=body).status_code == 200
    saved = json.loads(settings.state_path.read_text())
    assert saved["watchlist"] == ["ollama"] and saved["statuses"] == {"CVE-2024-37032": "fixed"}
    assert saved["usage"] == {"ollama": "library"} and saved["settings"]["later_part"] == {"x": 3}


# --- A13.3: channels, test alerts, the log ------------------------------------------------------------------------

def test_a13_3_each_channel_says_whether_it_is_set_up_and_how(settings, knowledge):
    c, _ = make_client(settings, knowledge, desktop_command=no_desktop)
    channels = c.get("/settings").json()["channels"]
    assert set(channels) == {"desktop", "email", "ntfy"}
    assert not any(ch["configured"] for ch in channels.values())
    assert "SMTP_HOST" in channels["email"]["detail"] and "NTFY_TOPIC" in channels["ntfy"]["detail"]
    assert "notify-send" in channels["desktop"]["detail"]


def test_a13_3_settings_never_return_a_secret(settings, knowledge):
    env = replace(settings, smtp_host="smtp.example", smtp_user="deryk@example.org", smtp_password="hunter2",
                  alert_email_to="deryk@example.org", ntfy_topic="secret-topic-123", ntfy_token="tk_secret")
    c, _ = make_client(env, knowledge)
    text = c.get("/settings").text
    for secret in ("hunter2", "secret-topic-123", "tk_secret", "deryk@"):
        assert secret not in text
    assert "d***@example.org" in text


def test_a13_3_preview_records_the_alert_and_sends_nothing(client):
    r = client.post("/alerts/test", json={"channel": "preview"})
    assert r.status_code == 200
    body = r.json()
    assert body["channel"] == "preview" and body["sent"] is False and "nothing was sent" in body["note"]
    a = body["alert"]
    assert a["title"] == "Test · In CISA KEV: Langflow" and a["priority"] == 5  # the most urgent open CVE: KEV
    # Your due date from the policy, worded as on the dashboard (review item 18), never "remediation due"
    top = client.get("/cves?status=open&limit=1").json()["rows"][0]
    assert a["body"].startswith(top["id"]) and "remediation" not in a["body"]
    assert a["body"].endswith(f" · {'decide by' if top['no_fix'] else 'due'} {top['due_date']}")
    log = client.get("/alerts").json()["alerts"]
    assert len(log) == 1 and (log[0]["title"], log[0]["channel"], log[0]["sent"]) == (a["title"], "preview", False)


def test_a13_3_unconfigured_channel_is_not_configured_and_logged(settings, knowledge):
    c, _ = make_client(settings, knowledge, desktop_command=no_desktop)
    for channel in ("email", "ntfy", "desktop"):
        r = c.post("/alerts/test", json={"channel": channel})
        assert r.status_code == 400 and r.json()["error"]["code"] == "not_configured", channel
    log = c.get("/alerts").json()["alerts"]
    assert [e["channel"] for e in log] == ["desktop", "ntfy", "email"]  # newest first
    assert all(e["sent"] is False and e["error"] and e["error_code"] == "not_configured" for e in log)


def test_a13_3_unknown_channel_is_400(client):
    assert client.post("/alerts/test", json={"channel": "pager"}).status_code == 400


class FakeSMTP:
    sent: list = []

    def __init__(self, host, port):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def starttls(self):
        pass

    def login(self, user, password):
        pass

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


def test_a13_3_email_test_alert_is_sent_and_logged(settings, knowledge):
    FakeSMTP.sent = []
    env = replace(settings, smtp_host="smtp.example", alert_email_to="me@example.org")
    c, _ = make_client(env, knowledge, smtp_factory=FakeSMTP)
    body = c.post("/alerts/test", json={"channel": "email"}).json()
    assert body["sent"] is True and body["channel"] == "email" and "Check that it arrived" in body["note"]
    assert len(FakeSMTP.sent) == 1 and FakeSMTP.sent[0]["Subject"] == "[LLM security] Test · In CISA KEV: Langflow"
    log = c.get("/alerts").json()["alerts"][0]
    assert (log["channel"], log["sent"], log["error"], log["error_code"]) == ("email", True, None, None)


def test_a13_3_ntfy_and_desktop_test_alerts_go_through_their_senders(settings, knowledge):
    posted, ran = [], []

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    def opener(req, timeout):
        posted.append(json.loads(req.data))
        return Resp()

    env = replace(settings, ntfy_topic="t0p1c")
    c, _ = make_client(env, knowledge, opener=opener, runner=lambda args, **kw: ran.append(args),
                       desktop_command=lambda: "/usr/bin/notify-send")
    assert c.post("/alerts/test", json={"channel": "ntfy"}).json()["sent"] is True
    assert c.post("/alerts/test", json={"channel": "desktop"}).json()["sent"] is True
    assert posted[0]["topic"] == "t0p1c" and posted[0]["title"].startswith("Test · ")
    assert ran[0][0] == "/usr/bin/notify-send"


def test_a13_3_a_failed_send_is_502_and_logged(settings, knowledge):
    def opener(req, timeout):
        raise OSError("network down")

    c, _ = make_client(replace(settings, ntfy_topic="t0p1c"), knowledge, opener=opener)
    r = c.post("/alerts/test", json={"channel": "ntfy"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "notify_failed"
    log = c.get("/alerts").json()["alerts"][0]
    assert log["sent"] is False and "Couldn't reach ntfy" in log["error"] and log["error_code"] == "notify_failed"


def test_a13_3_the_log_shows_the_newest_20(client):
    for _ in range(23):
        client.post("/alerts/test", json={"channel": "preview"})
    log = client.get("/alerts").json()["alerts"]
    assert len(log) == 20
    assert [e["at"] for e in log] == sorted((e["at"] for e in log), reverse=True)


def test_a13_3_test_alert_with_an_empty_watchlist_is_400(given, client):
    given.watching()
    r = client.post("/alerts/test", json={"channel": "preview"})
    assert r.status_code == 400 and "no open CVEs" in r.json()["error"]["message"]


# --- A13.4: alert text uses structured fields only ----------------------------------------------------------------

@pytest.mark.parametrize("cve_id", ["CVE-2024-8309", "CVE-2025-3248"])
def test_a13_4_alert_text_never_contains_the_description(knowledge, cve_id):
    from app.notify import format_alert

    cve = knowledge.cves.get(cve_id)
    msg = format_alert(cve, "new", knowledge, "http://localhost:5173")
    text = json.dumps(msg)
    for i in range(0, len(cve["description"]) - 30, 15):  # no 30-character run of the description anywhere
        assert cve["description"][i:i + 30] not in text
    assert msg["body"].startswith(cve_id) and msg["click"] == f"http://localhost:5173/#cve={cve_id}"


# --- A13.5: reset ---------------------------------------------------------------------------------------------------

def test_a13_5_reset_needs_the_word_reset(client):
    for confirm in ("yes", "RESET", ""):
        r = client.post("/state/reset", json={"confirm": confirm})
        assert r.status_code == 400, confirm
    assert client.post("/state/reset", json={}).status_code == 400


def test_a13_5_reset_restores_watchlist_statuses_settings_and_an_empty_log(given, client, deps):
    given.watching("vllm").decided("CVE-2024-8309", "fixed").settings(alerts={"min_severity": "LOW"})
    given.alerted({"title": "x"})
    r = client.post("/state/reset", json={"confirm": "reset"})
    assert r.status_code == 200 and r.json() == {"reset": True, "watchlist": DEFAULT_WATCHLIST}
    assert client.get("/settings").json()["settings"]["alerts"]["min_severity"] == "HIGH"
    assert client.get("/alerts").json() == {"alerts": []}
    assert deps.state.read().statuses == {}

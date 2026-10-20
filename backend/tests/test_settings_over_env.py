"""Settings instead of .env where safe, and an alert tap that works from a phone. Check ids: B26.n, from #70.

Seam 1 (the HTTP API) with fake users by overriding the auth dependency (as B09's tests do), the fake feeds and a
clock the test moves, and fake transports for ntfy and email: nothing is sent. The rule for every moved setting:
the environment wins when set, else the owner's saved setting, else the default.
"""
import dataclasses
import json
import logging
import shutil

import pytest
from fastapi.testclient import TestClient

from app.auth import current_user
from app.feeds import FakeFeeds
from tests.test_per_user import as_header
from tests.test_refresh import DAY1, NEW_DAY1, NEW_SINCE, Clock


class App:
    """An app on its own index copy, state file and live folder, built from `settings` (env-style) and these
    changes. `client(user)` asks as that user; the default user is the owner."""

    def __init__(self, tmp_path, index_dir, **changes):
        from app.config import Settings

        shutil.copytree(index_dir, tmp_path / "index")
        self.settings = Settings(llm_provider="fake", state_path=tmp_path / "state.json",
                                 index_path=tmp_path / "index", live_path=tmp_path / "live",
                                 **{"feeds": "fake", **changes})
        self.feeds, self.clock = FakeFeeds(day=1), Clock(f"{DAY1}T09:00:00+00:00")
        self.ntfy: list[dict] = []
        self.emails: list[str] = []
        self.start()

    def start(self) -> None:
        """Build the app from the files on disk: a fresh start is a restart."""
        from app.deps import build_deps
        from app.main import create_app
        from app.notify import Transports

        self.deps = build_deps(self.settings, feeds=self.feeds, clock=self.clock)
        sent = self.ntfy

        class Resp:
            status = 200

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        def opener(req, timeout):
            sent.append(json.loads(req.data))
            return Resp()

        emails = self.emails

        class FakeSMTP:
            def __init__(self, host, port):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

            def starttls(self):
                pass

            def login(self, user, password):
                pass

            def send_message(self, m):
                emails.append(m.get_content())

        self.deps.transports = Transports(opener=opener, smtp_factory=FakeSMTP, desktop_command=lambda: None)
        self.app = create_app(self.deps)
        self.app.dependency_overrides[current_user] = as_header
        self.owner = self("default")

    def __call__(self, user: str) -> TestClient:
        return TestClient(self.app, raise_server_exceptions=False, headers={"x-test-user": user})


def env(**names: str) -> frozenset[str]:
    return frozenset(names)


@pytest.fixture
def app(tmp_path, index_dir, index):
    return App(tmp_path, index_dir)


# --- B26.1: live or snapshot, switched on Settings without a restart ------------------------------------------------

def test_b26_1_the_owner_switches_to_live_data_and_back_without_a_restart(app):
    owner = app.owner
    assert owner.get("/health").json()["mode"] == "snapshot"
    assert owner.post("/refresh").json()["error"]["code"] == "snapshot_mode"

    r = owner.put("/settings/server", json={"data_mode": "live"})
    assert r.status_code == 200, r.text
    assert r.json()["server"]["fields"]["data_mode"] == {"value": "live", "source": "saved"}
    health = owner.get("/health").json()
    assert (health["mode"], health["as_of"]) == ("live", DAY1)  # today, by the clock: live mode's as-of date
    assert (app.settings.live_path / "current.json").exists()  # a live start copies the snapshot into LIVE_PATH

    reply = owner.post("/refresh").json()  # Check now follows the switch
    assert reply["ran"] and reply["result"]["new_cves"] == [NEW_DAY1]
    assert NEW_DAY1 in [r["id"] for r in owner.get(f"/cves?{NEW_SINCE}").json()["rows"]]
    assert owner.get("/dashboard").json()["data"]["mode"] == "live"
    assert owner.get("/refresh/runs").json()["runs"][0]["trigger"] == "button"

    assert owner.put("/settings/server", json={"data_mode": "snapshot"}).status_code == 200
    health = owner.get("/health").json()
    assert (health["mode"], health["as_of"]) == ("snapshot", "2026-10-13")
    assert NEW_DAY1 not in [r["id"] for r in owner.get(f"/cves?{NEW_SINCE}").json()["rows"]]
    assert owner.post("/refresh").json()["error"]["code"] == "snapshot_mode"
    assert (app.settings.live_path / "current.json").exists()  # the live data stays on disk

    owner.put("/settings/server", json={"data_mode": "live"})  # back to live: the refreshed data is still there
    assert NEW_DAY1 in [r["id"] for r in owner.get(f"/cves?{NEW_SINCE}").json()["rows"]]


def test_b26_1_a_saved_switch_outlives_a_restart(app):
    app.owner.put("/settings/server", json={"data_mode": "live"})
    app.start()
    assert app.owner.get("/health").json()["mode"] == "live"


# --- B26.2: the environment wins when it sets one ------------------------------------------------------------------

def test_b26_2_a_setting_the_environment_sets_wins_and_cant_be_changed_on_settings(tmp_path, index_dir, index):
    app = App(tmp_path, index_dir, data_mode="live", alert_tz="Europe/London",
              env_set=env(data_mode="DATA_MODE", alert_tz="ALERT_TZ"))
    server = app.owner.get("/settings").json()["server"]
    assert server["fields"]["data_mode"] == {"value": "live", "source": "env"}
    assert server["fields"]["alert_tz"] == {"value": "Europe/London", "source": "env"}
    assert server["fields"]["app_url"] == {"value": "http://localhost:5173", "source": "default"}
    assert server["env_names"]["data_mode"] == "DATA_MODE"

    r = app.owner.put("/settings/server", json={"data_mode": "snapshot"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "set_in_env"
    assert "DATA_MODE" in r.json()["error"]["message"]
    assert app.owner.get("/health").json()["mode"] == "live"
    # the others still save
    assert app.owner.put("/settings/server", json={"app_url": "https://patch.example.ts.net/"}).status_code == 200
    assert app.owner.get("/settings").json()["server"]["fields"]["app_url"] == {
        "value": "https://patch.example.ts.net", "source": "saved"}


def test_b26_2_the_environment_wins_over_a_value_saved_before_it_was_set(tmp_path, index_dir, index):
    app = App(tmp_path, index_dir)
    app.owner.put("/settings/server", json={"data_mode": "live", "alert_tz": "Asia/Tokyo"})
    app.settings = dataclasses.replace(app.settings, env_set=env(data_mode="DATA_MODE"))  # DATA_MODE=snapshot set
    app.start()
    body = app.owner.get("/settings").json()
    assert body["server"]["fields"]["data_mode"] == {"value": "snapshot", "source": "env"}
    assert app.owner.get("/health").json()["mode"] == "snapshot"
    assert body["alert_tz"] == "Asia/Tokyo"  # not set in the environment: the saved one


def test_b26_2_bad_values_are_refused(app):
    for change in ({"data_mode": "both"}, {"alert_tz": "Mars/Olympus"}, {"app_url": "javascript:alert(1)"},
                   {"ntfy_url": "ntfy.sh"}, {"smtp_port": 0}, {"alert_email_to": "not an address"},
                   {"ntfy_topic": "has spaces"}, {"unknown": 1}):
        r = app.owner.put("/settings/server", json=change)
        assert r.status_code == 400, change


# --- B26.3: owner only ---------------------------------------------------------------------------------------------

def test_b26_3_non_owners_never_see_the_server_settings_and_cant_change_them(app):
    alice = app("alice")
    assert alice.get("/settings").json()["server"] is None
    r = alice.put("/settings/server", json={"data_mode": "live"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_owner"
    assert alice.put("/settings/server", json={"ntfy_topic": "alices-own-topic"}).status_code == 403
    assert alice.get("/health").json()["mode"] == "snapshot"
    assert app.owner.get("/settings").json()["server"]["secrets"]["ntfy_topic"]["set"] is False


# --- B26.4: secrets are write-only ---------------------------------------------------------------------------------

SECRETS = {"ntfy_topic": "patch-s3cr3t-topic-4f9a", "ntfy_token": "tk_s3cr3t_token", "smtp_host": "smtp.s3cr3t.test",
           "smtp_user": "s3cr3t-user", "smtp_password": "s3cr3t pass ", "alert_email_from": "from@s3cr3t.test",
           "alert_email_to": "owner@s3cr3t.test", "nvd_api_key": "nvd-s3cr3t-key",
           "telegram_bot_token": "4242:s3cr3t-telegram-token-abcdef"}


def test_b26_4_secrets_are_saved_but_never_sent_back_or_logged(app, caplog):
    caplog.set_level(logging.DEBUG)
    r = app.owner.put("/settings/server", json=SECRETS)
    assert r.status_code == 200, r.text
    replies = [r.text, app.owner.get("/settings").text, app.owner.get("/health").text,
               app.owner.post("/alerts/test", json={"channel": "ntfy"}).text, app.owner.get("/alerts").text]
    for value in SECRETS.values():
        for reply in replies:
            assert value.strip() not in reply
        assert value.strip() not in caplog.text
    body = app.owner.get("/settings").json()
    assert body["server"]["secrets"]["ntfy_topic"] == {"set": True, "source": "saved"}
    assert all(s["set"] for s in body["server"]["secrets"].values())
    assert body["channels"]["ntfy"]["configured"] and body["channels"]["email"]["configured"]
    assert app.ntfy[-1]["topic"] == SECRETS["ntfy_topic"]  # the saved topic is used, with no restart


def test_b26_4_a_saved_secret_can_be_removed(app):
    app.owner.put("/settings/server", json={"ntfy_topic": SECRETS["ntfy_topic"]})
    r = app.owner.put("/settings/server", json={"ntfy_topic": None})
    assert r.json()["server"]["secrets"]["ntfy_topic"] == {"set": False, "source": "default"}
    assert r.json()["channels"]["ntfy"]["configured"] is False


def test_b26_4_a_secret_in_the_environment_says_so_and_wins(tmp_path, index_dir, index):
    app = App(tmp_path, index_dir, ntfy_topic="env-topic-abc", env_set=env(ntfy_topic="NTFY_TOPIC"))
    assert app.owner.get("/settings").json()["server"]["secrets"]["ntfy_topic"] == {"set": True, "source": "env"}
    r = app.owner.put("/settings/server", json={"ntfy_topic": "another-topic"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "set_in_env"
    assert "env-topic-abc" not in app.owner.get("/settings").text
    app.owner.post("/alerts/test", json={"channel": "ntfy"})
    assert app.ntfy[-1]["topic"] == "env-topic-abc"


def test_b26_4_a_reset_of_the_demo_data_keeps_the_server_settings(app):
    app.owner.put("/settings/server", json={"data_mode": "live", "ntfy_topic": SECRETS["ntfy_topic"]})
    assert app.owner.post("/state/reset", json={"confirm": "reset"}).status_code == 200
    server = app.owner.get("/settings").json()["server"]
    assert server["fields"]["data_mode"]["value"] == "live" and server["secrets"]["ntfy_topic"]["set"]


# --- B26.5: the alert's tap link only when a phone can open it ----------------------------------------------------

@pytest.mark.parametrize("address, link", [
    (None, False),  # the default, http://localhost:5173
    ("http://127.0.0.5:5173", False), ("http://[::1]:5173", False), ("http://0.0.0.0:8000", False),
    ("http://app.localhost:5173", False),
    ("https://patch-abc.a.run.app", True), ("http://192.168.1.20:5173", True), ("http://desk.tail1234.ts.net", True),
])
def test_b26_5_a_tap_opens_the_cve_only_when_the_address_is_reachable_from_a_phone(app, address, link):
    change = {"ntfy_topic": "t0p1c", "smtp_host": "smtp.test", "alert_email_to": "me@example.org"}
    r = app.owner.put("/settings/server", json=change | ({"app_url": address} if address else {}))
    assert r.json()["server"]["app_url_reachable"] is link
    reply = app.owner.post("/alerts/test", json={"channel": "ntfy"}).json()
    cve = reply["alert"]["click"].rsplit("/", 1)[1]
    app.owner.post("/alerts/test", json={"channel": "email"})
    if link:
        assert app.ntfy[-1]["click"] == f"{address}/cves/{cve}" == reply["tap_link"]  # Explain it one tap away (B04)
        assert f"Open it in the app: {address}/cves/{cve}" in app.emails[-1]
        assert reply["tap"] == f"Tapping it opens Patch at {cve}."
    else:
        assert "click" not in app.ntfy[-1] and reply["tap_link"] is None
        assert "Open it in the app" not in app.emails[-1] and "http" not in app.emails[-1]
        assert "opens the message in the ntfy app" in reply["tap"]


def test_b26_5_a_refresh_alert_follows_the_same_rule(tmp_path, index_dir, index):
    app = App(tmp_path, index_dir, data_mode="live")
    body = app.owner.get("/settings").json()["settings"]
    body["alerts"]["channels"] = ["ntfy"]
    app.owner.put("/settings", json=body)
    app.owner.put("/settings/server", json={"ntfy_topic": "t0p1c"})
    assert app.owner.post("/refresh").json()["ran"]
    assert app.ntfy and all("click" not in m for m in app.ntfy)

    app.owner.put("/settings/server", json={"app_url": "https://patch.example.ts.net"})
    app.clock.advance(60 * 24)
    app.feeds.day = 2
    app.owner.post("/refresh")
    assert app.ntfy[-1]["click"].startswith("https://patch.example.ts.net/")


# --- B26.6: quiet hours in the time zone from Settings -------------------------------------------------------------

@pytest.mark.parametrize("zone, env_zone, held", [
    (None, None, True),  # nothing saved: UTC, as before, so quiet hours saved earlier keep working
    ("Asia/Tokyo", None, False),  # 09:00 UTC is 18:00 in Tokyo: outside 08:00 to 10:00
    (None, "UTC", True),  # ALERT_TZ in .env still works, and wins (B26.2: Settings can't change it)
])
def test_b26_6_quiet_hours_use_the_time_zone_from_settings(tmp_path, index_dir, index, zone, env_zone, held):
    extra = {"alert_tz": env_zone, "env_set": env(alert_tz="ALERT_TZ")} if env_zone else {}
    app = App(tmp_path, index_dir, data_mode="live", **extra)
    body = app.owner.get("/settings").json()["settings"]
    body["alerts"] |= {"quiet_start": "08:00", "quiet_end": "10:00"}
    app.owner.put("/settings", json=body)
    if zone:
        assert app.owner.put("/settings/server", json={"alert_tz": zone}).status_code == 200
    if env_zone:
        assert app.owner.put("/settings/server", json={"alert_tz": "Asia/Tokyo"}).status_code == 400
    assert app.owner.get("/settings").json()["alert_tz"] == (zone or env_zone or "UTC")
    kinds = {e["kind"] for e in app.owner.post("/refresh").json()["result"]["alerts"]["default"]}
    assert ("held" in kinds) is held and kinds


# --- B26.7: the refresh CLI (the systemd timer) runs on the same settings ------------------------------------------

def test_b26_7_the_cli_follows_live_mode_and_the_channels_saved_on_settings(app, monkeypatch, capsys):
    from app import refresh

    for name, value in {"LIVE_PATH": str(app.settings.live_path), "STATE_PATH": str(app.settings.state_path),
                        "FEEDS": "fake", "FAKE_FEEDS_DAY": "1"}.items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("DATA_MODE", raising=False)
    assert refresh.main() == 2  # nothing saved: the snapshot
    capsys.readouterr()

    body = app.owner.get("/settings").json()["settings"]
    body["alerts"]["channels"] = ["ntfy"]
    app.owner.put("/settings", json=body)
    app.owner.put("/settings/server", json={"data_mode": "live", "ntfy_topic": "t0p1c"})
    assert refresh.main() == 0
    out = json.loads(capsys.readouterr().out)
    sent = [c for e in out["result"]["alerts"]["default"] for c in e["channels"]]
    assert sent and all(c["channel"] == "ntfy" and c["error"] is None for c in sent)  # the saved topic: set up


def cli_env(app, monkeypatch, **more: str) -> None:
    """The systemd timer's environment: `.env` with no DATA_MODE line (and none of the other moved settings)."""
    for name, value in {"LIVE_PATH": str(app.settings.live_path), "STATE_PATH": str(app.settings.state_path),
                        "FEEDS": "fake", "FAKE_FEEDS_DAY": "1", **more}.items():
        monkeypatch.setenv(name, value)
    for name in ("DATA_MODE", "ALERT_TZ", "APP_URL", "NTFY_URL", "NTFY_TOPIC"):
        if name not in more:
            monkeypatch.delenv(name, raising=False)


def test_b26_7_the_scheduled_run_uses_the_saved_mode_zone_link_and_ntfy_server(app, monkeypatch, capsys):
    import datetime as dt
    import zoneinfo

    from app import refresh

    cli_env(app, monkeypatch)
    assert refresh.main(["--schedule"]) == 0  # nothing saved: the snapshot, a skip (B28.4)
    assert json.loads(capsys.readouterr().out) == {"ran": False, "skipped": "snapshot"}

    # quiet hours around the real time now in Tokyo, so the run holds its alerts only if it reads the saved zone
    hour = dt.datetime.now(zoneinfo.ZoneInfo("Asia/Tokyo")).hour
    body = app.owner.get("/settings").json()["settings"]
    body["alerts"] |= {"channels": ["ntfy"], "quiet_start": f"{hour:02d}:00", "quiet_end": f"{(hour + 2) % 24:02d}:00"}
    app.owner.put("/settings", json=body)
    app.owner.put("/settings/server", json={"data_mode": "live", "alert_tz": "Asia/Tokyo",
                                            "app_url": "https://patch.example.ts.net",
                                            "ntfy_url": "https://ntfy.example.test", "ntfy_topic": "t0p1c"})
    assert refresh.main(["--schedule"]) == 0  # live mode from Settings: the scheduled run runs (never checked: due)
    out = json.loads(capsys.readouterr().out)
    entries = out["result"]["alerts"]["default"]
    assert entries and {e["kind"] for e in entries} == {"held"}  # quiet hours in the saved zone
    assert all(e["click"].startswith("https://patch.example.ts.net/") for e in entries)  # the saved link address

    from app.refresh import with_saved_settings
    from app.config import Settings
    s = with_saved_settings(Settings.from_env())
    assert (s.data_mode, s.alert_tz, s.ntfy_url, s.ntfy_topic) == ("live", "Asia/Tokyo", "https://ntfy.example.test",
                                                                   "t0p1c")


def test_b26_7_the_environment_still_wins_for_the_cli(app, monkeypatch, capsys):
    from app import refresh

    app.owner.put("/settings/server", json={"data_mode": "live"})
    cli_env(app, monkeypatch, DATA_MODE="snapshot")
    assert refresh.main(["--schedule"]) == 0 and "snapshot" in capsys.readouterr().err  # a skip since B28.4
    cli_env(app, monkeypatch, DATA_MODE="live", ALERT_TZ="UTC")
    app.owner.put("/settings/server", json={"data_mode": None})
    assert refresh.main([]) == 0  # DATA_MODE=live in .env, nothing saved: live

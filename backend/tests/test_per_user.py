"""Per-user state (B09, #41) through the HTTP API (seam 1). Check ids: B09.n.

Two fake users, alice and bob, by overriding the auth dependency (app.auth.current_user): the test names the user
in a header that only this override reads. Without it every request is the default user, whose state is today's
state file. Sign-in itself is B10 (#42).
"""
import json

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.auth import current_user
from app.config import DEFAULT_USER, DEFAULT_WATCHLIST

CVE = "CVE-2024-8309"  # LangChain, on the default watchlist


def as_header(request: Request) -> str:
    return request.headers.get("x-test-user", DEFAULT_USER)


class Users:
    """One app, a client per user."""

    def __init__(self, deps):
        from app.main import create_app

        self.deps = deps
        self.app = create_app(deps)
        self.app.dependency_overrides[current_user] = as_header
        self.client = TestClient(self.app, raise_server_exceptions=False)

    def __call__(self, user: str):
        c = TestClient(self.app, raise_server_exceptions=False, headers={"x-test-user": user})
        return c


@pytest.fixture
def users(deps):
    return Users(deps)


def watchlist(client) -> list[str]:
    return client.get("/watchlist").json()["watchlist"]


# --- B09.2: the default user is today's state file -------------------------------------------------------------------

def test_b09_2_an_existing_state_file_loads_unchanged_as_the_default_user(settings, knowledge, index):
    from app.deps import build_deps
    from app.main import create_app

    saved = {"watchlist": ["ollama"], "statuses": {CVE: "fixed"}, "settings": {"explain_level": "simple"},
             "dev": {"top_n": 7}, "future_part": {"kept": True}}
    settings.state_path.write_text(json.dumps(saved))
    c = TestClient(create_app(build_deps(settings, knowledge=knowledge, index=index)))
    assert watchlist(c) == ["ollama"]
    assert c.get("/settings").json()["settings"]["explain_level"] == "simple"
    c.put("/watchlist", json={"products": ["ollama", "vllm"]})
    on_disk = json.loads(settings.state_path.read_text())
    assert on_disk["watchlist"] == ["ollama", "vllm"] and on_disk["future_part"] == {"kept": True}
    assert [p.name for p in settings.state_path.parent.iterdir()] == ["state.json"]  # nobody else's state yet


# --- B09.3: each user has their own watchlist ------------------------------------------------------------------------

def test_b09_3_a_watchlist_change_is_the_callers_only(users, settings):
    alice, bob = users("alice"), users("bob")
    assert alice.put("/watchlist", json={"products": [{"product": "ollama", "version": "0.1.0"}]}).status_code == 200
    assert watchlist(alice) == ["ollama"]
    assert watchlist(bob) == DEFAULT_WATCHLIST  # a new user starts with the defaults
    assert watchlist(users.client) == DEFAULT_WATCHLIST  # and the default user too
    assert not settings.state_path.exists()  # the default user's file is untouched
    fields = {p["product"]: p for p in bob.get("/watchlist").json()["products"]}
    assert fields["ollama"]["version"] is None


# --- B09.4: statuses and decision records are the caller's -----------------------------------------------------------

def test_b09_4_a_status_change_is_the_callers_only(users):
    alice, bob = users("alice"), users("bob")
    r = alice.patch(f"/cves/{CVE}", json={"status": "fixed", "note": "upgraded"})
    assert r.status_code == 200, r.text

    def status(c):
        rows = c.get("/cves", params={"status": "all", "product": "langchain", "limit": 200}).json()["rows"]
        return next(row["status"] for row in rows if row["id"] == CVE)

    assert status(alice) == "fixed"
    assert status(bob) == "open" and status(users.client) == "open"
    assert users.deps.users.state("bob").read().decision(CVE) is None


# --- B09.5: settings and the explain level are the caller's ----------------------------------------------------------

def test_b09_5_settings_and_the_explain_level_are_the_callers_only(users):
    alice, bob = users("alice"), users("bob")
    body = alice.get("/settings").json()["settings"]
    body["explain_level"] = "simple"
    body["alerts"]["min_severity"] = "CRITICAL"
    assert alice.put("/settings", json=body).status_code == 200
    assert alice.get("/settings").json()["settings"]["explain_level"] == "simple"
    bobs = bob.get("/settings").json()["settings"]
    assert (bobs["explain_level"], bobs["alerts"]["min_severity"]) == ("normal", "HIGH")
    # the chat answers at the caller's saved level
    assert alice.post("/chat", json={"message": "What is prompt injection?"}).json()["explain_level"] == "simple"
    assert bob.post("/chat", json={"message": "What is prompt injection?"}).json()["explain_level"] == "normal"


# --- B09.6: reset clears only the caller's state ---------------------------------------------------------------------

def test_b09_6_reset_clears_only_the_callers_state(users):
    alice, bob = users("alice"), users("bob")
    alice.put("/watchlist", json={"products": ["ollama"]})
    bob.put("/watchlist", json={"products": ["vllm"]})
    users.client.put("/watchlist", json={"products": ["gradio"]})
    r = alice.post("/state/reset", json={"confirm": "reset"})
    assert r.status_code == 200, r.text
    assert r.json()["watchlist"] == DEFAULT_WATCHLIST
    assert watchlist(bob) == ["vllm"] and watchlist(users.client) == ["gradio"]


# --- B09.7: a new user starts with the defaults ----------------------------------------------------------------------

def test_b09_7_a_new_user_gets_the_default_watchlist_and_settings_and_writes_nothing(users, settings):
    carol = users("carol")
    assert watchlist(carol) == DEFAULT_WATCHLIST
    assert carol.get("/settings").json()["settings"] == users.client.get("/settings").json()["settings"]
    assert carol.get("/alerts").json()["alerts"] == []
    # reading saves no state; carol joins the users the refresh alerts (story 61, BR.10), the owner needs no record
    assert [p.name for p in settings.users_path.iterdir()] == ["known.users.json"]
    assert json.loads((settings.users_path / "known.users.json").read_text()) == ["carol"]


def test_b09_7_a_bad_user_id_never_reaches_the_store(users, settings):
    assert users("../state").get("/watchlist").status_code == 500
    assert not settings.users_path.exists() and not settings.state_path.exists()


# --- B09.8: the chat's tools act on the caller's state ---------------------------------------------------------------

def chat(client, message: str) -> dict:
    r = client.post("/chat", json={"message": message})
    assert r.status_code == 200, r.text
    return r.json()


def test_b09_8_a_proposal_is_the_callers_and_applies_to_their_state(users):
    alice, bob = users("alice"), users("bob")
    [call] = [t for t in chat(alice, f"Mark {CVE} as fixed")["tool_calls"] if t["name"] == "update_watchlist"]
    pid = call["result"]["proposal_id"]
    assert bob.get(f"/proposals/{pid}").status_code == 404  # bob can't see or approve alice's proposal
    assert bob.post(f"/proposals/{pid}/approve").status_code == 404
    assert alice.post(f"/proposals/{pid}/approve").status_code == 200
    assert users.deps.users.state("alice").read().statuses == {CVE: "fixed"}
    assert users.deps.users.state("bob").read().statuses == {}


def test_b09_8_prioritise_reads_the_callers_watchlist(users):
    alice, bob = users("alice"), users("bob")
    alice.put("/watchlist", json={"products": ["ollama"]})

    def products(reply: dict) -> set[str]:
        [call] = [t for t in reply["tool_calls"] if t["name"] == "prioritise"]
        return {r["product"] for r in call["result"]["cves"]}

    assert products(chat(alice, "What should I fix first?")) == {"Ollama"}
    assert len(products(chat(bob, "What should I fix first?"))) > 1


def test_b09_8_research_web_counts_the_daily_cap_per_calling_user(users):
    from app.web_research import CannedWeb, DailyCap

    users.deps.web = CannedWeb()
    users.deps.web.cap = DailyCap(total=10, per_user=1)
    alice, bob = users("alice"), users("bob")

    def search(c):
        r = c.post("/chat/tool", json={"name": "research_web", "args": {"query": "Langflow advisory"}})
        assert r.status_code == 200, r.text
        return r.json()

    assert search(alice)["status"] == "ok"
    assert search(alice)["error"]["code"] == "web_limit"
    assert search(bob)["status"] == "ok"  # bob's own count


# --- B09.9: the refresh runs the alert rules per user; only the owner's go to the channels --------------------------

class LiveUsers:
    """The live app on the fake feeds (test_alert_delivery.LiveAlerts), with a client per user."""

    def __init__(self, tmp_path, index_dir, **settings):
        from test_alert_delivery import LiveAlerts

        self.live = LiveAlerts(tmp_path, index_dir, **settings)
        self.live.client.app.dependency_overrides[current_user] = as_header

    def __call__(self, user: str) -> TestClient:
        return TestClient(self.live.client.app, raise_server_exceptions=False, headers={"x-test-user": user})

    def alerts(self, *users: str) -> dict[str, list[dict]]:
        """The last run's alerts per user, each from that user's own GET /refresh (B37: a reply holds only the
        caller's alerts, so no one reply shows them all)."""
        return {u: self(u).get("/refresh").json()["last_result"]["alerts"].get(u, []) for u in users}


def pairs(entries: list[dict]) -> set[tuple[str, str]]:
    return {(a["cve"], a["reason"]) for e in entries for a in e["alerts"]}


def test_b09_9_each_user_gets_alerts_for_their_own_watchlist_and_only_the_owner_on_channels(tmp_path, index_dir,
                                                                                         index):
    from test_refresh import NEW_DAY2, OLD_TO_KEV

    app = LiveUsers(tmp_path, index_dir)
    alice, bob = app("alice"), app("bob")
    alice.put("/watchlist", json={"products": ["ollama"]})  # not Langflow
    bob.put("/watchlist", json={"products": ["langflow"]})  # not Ollama
    app.live.check_now()
    app.live.channels.ntfy.clear()
    app.live.next_day()
    alerts = app.alerts("default", "alice", "bob")  # the owner (here the default user) and everyone saved

    assert all(alerts.values())
    assert (NEW_DAY2, "new") in pairs(alerts["alice"]) and (OLD_TO_KEV, "kev") not in pairs(alerts["alice"])
    assert (OLD_TO_KEV, "kev") in pairs(alerts["bob"]) and (NEW_DAY2, "new") not in pairs(alerts["bob"])
    # only the owner's went out; the others are recorded, with no channel, and shown in their own app
    assert len(app.live.channels.ntfy) == len(alerts["default"])
    assert all(e["channels"] and not e.get("in_app_only") for e in alerts["default"])
    assert all(e["channels"] == [] and e["in_app_only"] for e in alerts["alice"] + alerts["bob"])
    assert pairs(alice.get("/alerts").json()["alerts"]) >= pairs(alerts["alice"])
    assert not pairs(alice.get("/alerts").json()["alerts"]) & {(OLD_TO_KEV, "kev")}
    # once per CVE and reason, per user
    app.live.clock.advance(10)
    app.live.check_now()
    assert app.alerts("default", "alice", "bob") == {"default": [], "alice": [], "bob": []}


def test_b09_9_new_since_last_check_is_kept_per_user(tmp_path, index_dir, index):
    from test_refresh import NEW_DAY2

    app = LiveUsers(tmp_path, index_dir)
    alice, bob = app("alice"), app("bob")
    for c in (alice, bob):
        c.put("/watchlist", json={"products": ["ollama"]})
    app.live.check_now()
    app.live.next_day()

    def new(c) -> set[str]:
        return {r["id"] for r in c.get("/cves", params={"status": "all", "limit": 200}).json()["rows"] if r["new"]}

    assert NEW_DAY2 in new(alice) and NEW_DAY2 in new(bob)
    alice.post("/state/reset", json={"confirm": "reset"})
    assert new(alice) == set() and NEW_DAY2 in new(bob)


def test_b09_9_the_shared_schedule_is_the_owners(tmp_path, index_dir, index):
    app = LiveUsers(tmp_path, index_dir)
    alice = app("alice")
    body = alice.get("/settings").json()["settings"]
    body["alerts"]["schedule_paused"] = True
    alice.put("/settings", json=body)
    assert alice.get("/refresh/runs").json()["schedule"]["paused"] is False  # the owner's schedule runs
    body = app.live.client.get("/settings").json()["settings"]
    body["alerts"]["schedule_paused"] = True
    app.live.client.put("/settings", json=body)
    assert alice.get("/refresh/runs").json()["schedule"]["paused"] is True


def test_b09_9_the_owner_comes_from_the_environment(tmp_path, index_dir, index):
    app = LiveUsers(tmp_path, index_dir, owner="alice")
    alice = app("alice")
    alice.put("/watchlist", json={"products": ["ollama"]})
    app.live.client.put("/watchlist", json={"products": ["langflow"]})  # the default user, not the owner here
    app.live.check_now()
    app.live.channels.ntfy.clear()
    app.live.next_day()
    alerts = app.alerts("alice", "default")
    assert alerts["alice"] and all(e["channels"] for e in alerts["alice"])
    assert alerts["default"] and all(e["in_app_only"] for e in alerts["default"])
    assert len(app.live.channels.ntfy) == len(alerts["alice"])


def test_b09_9_only_the_owner_can_send_a_test_alert_on_a_channel(users):
    alice = users("alice")
    r = alice.post("/alerts/test", json={"channel": "desktop"})
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_owner"
    assert "owner" in r.json()["error"]["message"]
    assert alice.post("/alerts/test", json={"channel": "preview"}).status_code == 200  # recorded only: allowed
    assert [e["kind"] for e in alice.get("/alerts").json()["alerts"]] == ["test"]
    assert users.client.get("/alerts").json()["alerts"] == []


def test_b09_9_quiet_hours_hold_only_what_would_be_sent(tmp_path, index_dir, index):
    app = LiveUsers(tmp_path, index_dir)
    bob = app("bob")
    for c in (bob, app.live.client):
        body = c.get("/settings").json()["settings"]
        body["alerts"] |= {"quiet_start": "08:00", "quiet_end": "10:00"}  # the check runs at 09:00
        c.put("/settings", json=body)
    app.live.check_now()
    alerts = app.alerts("default", "bob")
    assert all(e["kind"] == "held" for e in alerts["default"])
    assert alerts["bob"] and all(e["kind"] != "held" and e["in_app_only"] for e in alerts["bob"])


# --- B09.10: check_updates answers with the calling user's alerts ----------------------------------------------------

def test_b09_10_check_updates_lists_the_callers_alerts(tmp_path, index_dir, index):
    from test_refresh import NEW_DAY2, OLD_TO_KEV

    app = LiveUsers(tmp_path, index_dir)
    alice = app("alice")
    alice.put("/watchlist", json={"products": ["ollama"]})
    app.live.check_now()
    app.live.clock.advance(60 * 24)
    app.live.feeds.day = 2
    [call] = [t for t in chat(alice, "Anything new since Monday?")["tool_calls"] if t["name"] == "check_updates"]
    got = {(a["cve"], a["reason"]) for a in call["result"]["alerts"]}
    assert (NEW_DAY2, "new") in got and (OLD_TO_KEV, "kev") not in got
    # the default user, asking right after, gets the same run's alerts for their own watchlist
    [mine] = [t for t in chat(app.live.client, "Anything new since Monday?")["tool_calls"]
              if t["name"] == "check_updates"]
    assert not mine["result"]["ran"] and (OLD_TO_KEV, "kev") in {(a["cve"], a["reason"])
                                                                 for a in mine["result"]["alerts"]}


# --- B37 (#87): a refresh reply holds the caller's own alerts only ---------------------------------------------------

def test_b37_check_now_and_the_refresh_status_hold_only_the_callers_alerts(tmp_path, index_dir, index):
    from test_refresh import NEW_DAY2, OLD_TO_KEV

    app = LiveUsers(tmp_path, index_dir)
    alice, bob = app("alice"), app("bob")
    alice.put("/watchlist", json={"products": ["ollama"]})  # not Langflow
    bob.put("/watchlist", json={"products": ["langflow"]})  # not Ollama
    app.live.check_now()
    app.live.clock.advance(60 * 24)
    app.live.feeds.day = 2

    ran = bob.post("/refresh")  # bob's Check now runs the refresh for every user
    refused = alice.post("/refresh")  # too soon: the 429 still carries the last run's result
    assert (ran.status_code, refused.status_code) == (200, 429)
    replies = {"bob's Check now": ran.json()["result"], "alice's refused Check now": refused.json()["result"],
               "bob's GET /refresh": bob.get("/refresh").json()["last_result"],
               "alice's GET /refresh": alice.get("/refresh").json()["last_result"],
               "bob's dashboard": bob.get("/dashboard").json()["data"]["last_result"]}
    for where, result in replies.items():
        caller = where.split("'")[0]
        assert set(result["alerts"]) == {caller}, where  # no other user's alerts
        assert all(f'"{u}"' not in json.dumps(result) for u in {"default", "alice", "bob"} - {caller}), where  # or ids
    # the caller's own alerts are still there
    assert (OLD_TO_KEV, "kev") in pairs(replies["bob's Check now"]["alerts"]["bob"])
    assert (NEW_DAY2, "new") in pairs(replies["alice's GET /refresh"]["alerts"]["alice"])
    assert sum(ran.json()["alerts_for_you"].values()) > 0

"""Your profile (B48, #97; the decisions of #77): anonymous by default, an optional display name you give Patch.

Patch needs nothing but Clerk's user id. The name lives in the user's own state, never in the token: the user menu and
new decision records use it ("Decided by <name>", else "you"). Remove clears it; past records keep the name they were
made with; Reset demo data keeps it. Another user's defaults have no alert channels (their alerts show in Patch only).

Through the HTTP API (seam 1). Check ids: B48.n.
"""
import pytest

from tests.test_access import ALICE, OWNER, Patch, auth_settings  # noqa: F401 (a fixture)
from tests.test_auth import approved
from tests.test_per_user import Users

CVE = "CVE-2024-8309"  # LangChain, on the default watchlist


@pytest.fixture
def users(deps):
    return Users(deps)


def mark(client, status: str = "fixed") -> dict:
    r = client.patch(f"/cves/{CVE}", json={"status": status})
    assert r.status_code == 200, r.text
    return r.json()["decision"]


# --- B48.1: anonymous by default; set, change and remove the name ----------------------------------------------------

def test_b48_1_a_profile_is_anonymous_until_a_name_is_given(client):
    assert client.get("/profile").json() == {"name": None}


def test_b48_1_set_change_and_remove_the_name(client):
    assert client.put("/profile", json={"name": "  Ada  "}).json() == {"name": "Ada"}  # trimmed
    assert client.get("/profile").json() == {"name": "Ada"}
    assert client.put("/profile", json={"name": "Ada L."}).json() == {"name": "Ada L."}
    assert client.put("/profile", json={"name": None}).json() == {"name": None}
    assert client.put("/profile", json={"name": "Ada"}).status_code == 200
    assert client.put("/profile", json={"name": "   "}).json() == {"name": None}  # empty after trimming: none


def test_b48_1_a_name_is_plain_text_and_at_most_60_characters(client):
    r = client.put("/profile", json={"name": "x" * 61})
    assert r.status_code == 400 and r.json()["error"]["code"] == "name_too_long"
    assert client.get("/profile").json() == {"name": None}  # nothing saved
    assert client.put("/profile", json={"name": "y" * 60}).json() == {"name": "y" * 60}
    assert client.put("/profile", json={"name": "Ada\x00\x07 Lovelace\n"}).json() == {"name": "Ada Lovelace"}


# --- B48.2: new decision records name you by your profile, else "you"; past records keep theirs --------------------

def history(client) -> list[dict]:
    return client.get(f"/cves/{CVE}").json()["row"]["history"]


def test_b48_2_a_record_says_you_without_a_name_and_the_name_with_one(client):
    assert mark(client)["decided_by"] == "you"
    client.put("/profile", json={"name": "Ada"})
    assert mark(client, "open")["decided_by"] == "Ada"


def test_b48_2_past_records_keep_the_name_they_were_made_with(client):
    client.put("/profile", json={"name": "Ada"})
    mark(client)
    client.put("/profile", json={"name": "Ada L."})
    mark(client, "open")
    client.put("/profile", json={"name": None})
    mark(client)
    assert [h["decided_by"] for h in history(client)] == ["Ada", "Ada L.", "you"]


# --- B48.3: Reset demo data keeps the profile -------------------------------------------------------------------------

def test_b48_3_reset_keeps_the_profile(client):
    client.put("/profile", json={"name": "Ada"})
    client.put("/watchlist", json={"products": ["ollama"]})
    assert client.post("/state/reset", json={"confirm": "reset"}).status_code == 200
    assert client.get("/watchlist").json()["watchlist"] != ["ollama"]  # the demo data went back
    assert client.get("/profile").json() == {"name": "Ada"}


# --- B48.4: another user never sees it ---------------------------------------------------------------------------------

def test_b48_4_a_profile_is_the_callers_only(users):
    alice, bob = users("alice"), users("bob")
    alice.put("/profile", json={"name": "Alice"})
    assert bob.get("/profile").json() == {"name": None}
    assert mark(bob)["decided_by"] == "you"
    assert users.client.get("/profile").json() == {"name": None}  # nor the default user


# --- B48.5: the session token's name and email are never read (#77 step 1) ------------------------------------------

@pytest.fixture
def signed_in(auth_settings, knowledge, index):
    p = Patch(auth_settings, knowledge, index)
    approved(p.deps, ALICE)
    return p


def test_b48_5_token_claims_never_reach_a_record(signed_in):
    claims = {"name": "Alice Example", "email": "alice@example.com"}
    r = signed_in.c.patch(f"/cves/{CVE}", json={"status": "fixed"}, headers=signed_in.as_(ALICE, **claims))
    assert r.json()["decision"]["decided_by"] == "you"
    assert signed_in.c.get("/profile", headers=signed_in.as_(ALICE, **claims)).json() == {"name": None}


def test_b48_5_the_request_alert_names_the_person_from_clerk_not_the_token(signed_in):
    signed_in.request("user_bob", name="Mallory <b>", email="mallory@example.com")
    assert [m["message"] for m in signed_in.alerts()] == ["From Bob"]  # the fake Clerk's name for user_bob


def test_b48_5_without_clerk_the_request_alert_names_the_user_id(signed_in):
    signed_in.deps.people = None  # no CLERK_SECRET_KEY
    signed_in.request("user_bob", name="Mallory")
    assert [m["message"] for m in signed_in.alerts()] == ["From user_bob"]

    def down(ids):
        raise RuntimeError("Clerk is down")
    signed_in.deps.people = down
    signed_in.request("user_carol", note="hi")
    assert signed_in.alerts()[-1]["message"] == "From user_carol (with a note)"


# --- B48.6: another user's alerts show in Patch only: their defaults have no channels --------------------------------

def test_b48_6_another_users_defaults_have_no_channels(signed_in):
    assert signed_in.c.get("/settings", headers=signed_in.as_(OWNER)).json()["settings"]["alerts"]["channels"] == [
        "desktop", "ntfy"]  # the owner's: every channel set up, as before
    mine = signed_in.c.get("/settings", headers=signed_in.as_(ALICE)).json()
    assert mine["settings"]["alerts"]["channels"] == []
    assert mine["owner"] is False
    assert signed_in.c.get("/settings", headers=signed_in.as_(OWNER)).json()["owner"] is True


# --- B48.7: the owner's state as saved today loads unchanged ---------------------------------------------------------

def test_b48_7_the_owners_state_of_today_loads_unchanged(settings, knowledge, index):
    import json

    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.main import create_app

    record = {"status": "fixed", "justification": None, "reason": None, "note": None, "review_date": None,
              "compensating_control": None, "decided_at": "2026-10-18T09:00:00+00:00", "decided_by": "owner",
              "via": "page"}
    today = {"watchlist": ["ollama", "langchain"], "statuses": {CVE: "fixed"}, "history": {CVE: [record]},
             "settings": {"alerts": {"channels": ["desktop", "ntfy"], "quiet_start": "22:00", "quiet_end": "07:00",
                                     "schedule_hours": 3},
                          "explain_level": "simple"},
             "server": {"data_mode": "snapshot", "alert_tz": "Europe/Vilnius"}}
    settings.state_path.write_text(json.dumps(today))
    c = TestClient(create_app(build_deps(settings, knowledge=knowledge, index=index)))
    got = c.get("/settings").json()
    alerts = got["settings"]["alerts"]
    assert (alerts["channels"], alerts["quiet_start"], alerts["quiet_end"], alerts["schedule_hours"]) == (
        ["desktop", "ntfy"], "22:00", "07:00", 3)
    assert got["owner"] is True and got["server"] is not None and got["alert_tz"] == "Europe/Vilnius"
    assert c.get("/profile").json() == {"name": None}  # anonymous until the owner gives a name
    assert history(c)[0]["decided_by"] == "owner"  # a past record keeps what it said
    assert json.loads(settings.state_path.read_text()) == today  # reading wrote nothing

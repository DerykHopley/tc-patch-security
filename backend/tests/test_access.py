"""Sign-up requests the owner approves in Patch (B38, #81). Check ids: B38.n.

Sign-up is open in Clerk, so anyone can make an account. A new account is let in only once the owner approves it:
until then every route but the request's own (`/access`, `/access/request`) is a 403. The owner gets one alert per
request, on the channels they set up; the Requests card on Settings (owner only) approves, refuses, undoes a refusal
or removes. Patch keeps only the Clerk user id, the status, when and by whom, and the optional note.

Through the HTTP API (seam 1), signed in with the B10 tests' own RSA key and fake session tokens: no Clerk account.
Clerk's Backend API (names and emails for the card) is a fake function on Deps.
"""
import dataclasses
import json

import pytest
from fastapi.testclient import TestClient

from tests.fake_gcs import FakeBucket
from tests.test_alert_delivery import Channels
from tests.test_auth import ORIGIN, PUBLIC, bearer, token

OWNER = "user_owner"
ALICE = "user_alice"


@pytest.fixture
def auth_settings(settings):
    return dataclasses.replace(settings, auth=True, owner=OWNER,
                               clerk_publishable_key="pk_test_ZmFrZS5jbGVyay5hY2NvdW50cy5kZXYk",
                               clerk_jwt_key=PUBLIC, auth_allowed_origins=[ORIGIN], ntfy_topic="t0p1c",
                               app_url="http://app.test")


class Patch:
    """The app with sign-in on, fake channels and a fake Clerk Backend API."""

    def __init__(self, settings, knowledge, index, bucket=None):
        from app.deps import build_deps
        from app.main import create_app

        self.channels = Channels()
        self.deps = build_deps(settings, knowledge=knowledge, index=index, bucket=bucket)
        self.deps.transports = self.channels.transports()
        self.looked_up: list[list[str]] = []

        def people(ids):
            self.looked_up.append(sorted(ids))
            return {i: {"name": i.removeprefix("user_").title(), "email": f"{i.removeprefix('user_')}@example.com"}
                    for i in ids}

        self.deps.people = people
        self.c = TestClient(create_app(self.deps), raise_server_exceptions=False)

    def as_(self, user: str, **claims) -> dict:
        return bearer(token(user, **claims))

    def request(self, user: str = ALICE, note: str | None = None, **claims):
        body = {} if note is None else {"note": note}
        return self.c.post("/access/request", json=body, headers=self.as_(user, **claims))

    def status(self, user: str = ALICE) -> dict:
        r = self.c.get("/access", headers=self.as_(user))
        assert r.status_code == 200, r.text
        return r.json()

    def owner_sets(self, user: str, status: str):
        return self.c.put(f"/access/requests/{user}", json={"status": status}, headers=self.as_(OWNER))

    def requests(self, as_user: str = OWNER):
        return self.c.get("/access/requests", headers=self.as_(as_user))

    def alerts(self) -> list[dict]:
        return [m for m in self.channels.ntfy if "access_request" in m["tags"]]


@pytest.fixture
def patch(auth_settings, knowledge, index):
    return Patch(auth_settings, knowledge, index)


def gated_routes(app) -> list[tuple[str, str]]:
    return [(m.upper(), path) for path, ops in app.openapi()["paths"].items() for m in ops
            if not path.startswith("/access") and path != "/health"]


# --- B38.1: a new account is waiting for nothing yet, and gets 403 everywhere but its request -----------------------

def test_b38_1_a_new_account_gets_403_everywhere_except_the_access_routes(auth_settings, knowledge, index, tmp_path):
    """Live mode with the dev panel and fake feeds: the most routes there are. A route added later is covered."""
    live = dataclasses.replace(auth_settings, data_mode="live", feeds="fake", live_path=tmp_path / "live",
                               dev_panel=True, auth=True)
    p = Patch(live, knowledge, index)
    routes = gated_routes(p.c.app)
    assert len(routes) > 30
    let_through = []
    for method, path in routes:
        r = p.c.request(method, path.replace("{", "").replace("}", ""), json={}, headers=p.as_(ALICE))
        if r.status_code != 403 or r.json()["error"]["code"] != "not_approved":
            let_through.append((method, path, r.status_code))
    assert let_through == []
    assert p.status() == {"status": "none", "owner": False, "sign_in": True, "note": None, "at": None}


def test_b38_1_the_403_says_why_in_plain_words(patch):
    r = patch.c.get("/watchlist", headers=patch.as_(ALICE))
    assert r.status_code == 403
    assert r.json()["error"] == {"code": "not_approved", "status": "none",
                                 "message": "Ask the owner for access first: Patch opens once they approve you."}
    patch.request()
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).json()["error"]["status"] == "waiting"


def test_b38_1_the_owner_is_always_approved(patch):
    assert patch.c.get("/watchlist", headers=patch.as_(OWNER)).status_code == 200
    assert patch.status(OWNER) == {"status": "approved", "owner": True, "sign_in": True, "note": None, "at": None}
    assert patch.request(OWNER).json()["status"] == "approved"  # nothing to ask
    assert patch.alerts() == []


def test_b38_1_a_waiting_user_does_not_count_for_the_refresh(patch):
    patch.request()
    patch.c.get("/watchlist", headers=patch.as_(ALICE))
    assert ALICE not in patch.deps.users.ids()


# --- B38.2: a request, one alert, and the owner's approval ---------------------------------------------------------

def test_b38_2_a_request_waits_and_alerts_the_owner_once(patch):
    r = patch.request(name="Alice Example")
    assert r.status_code == 200
    assert r.json()["status"] == "waiting"
    assert [(m["title"], m["message"]) for m in patch.alerts()] == [("New access request", "From Alice Example")]
    assert patch.alerts()[0]["click"] == "http://app.test/settings#requests"
    # asking again (a reload, a double click) changes nothing and alerts nobody
    assert patch.request(note="again").json()["status"] == "waiting"
    assert len(patch.alerts()) == 1
    assert patch.status()["note"] is None  # the first request's note stands


def test_b38_2_the_owner_approves_and_the_user_gets_in(patch):
    patch.request()
    assert patch.owner_sets(ALICE, "approved").status_code == 200
    assert patch.status()["status"] == "approved"
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).status_code == 200
    assert ALICE in patch.deps.users.ids()  # and now counts for the refresh


def test_b38_2_the_record_holds_the_id_status_when_and_who_only(patch, auth_settings):
    patch.request(note="I run Ollama at work", name="Alice Example", email="alice@example.com")
    patch.owner_sets(ALICE, "approved")
    record = json.loads((auth_settings.users_path / "access.users.json").read_text())
    assert set(record) == {ALICE}
    assert set(record[ALICE]) == {"status", "at", "by", "requested_at", "note", "alerted"}
    assert record[ALICE]["status"] == "approved" and record[ALICE]["by"] == OWNER
    assert "alice@example.com" not in json.dumps(record) and "Alice Example" not in json.dumps(record)


# --- B38.3: a refusal is final until the owner undoes it -----------------------------------------------------------

def test_b38_3_a_refused_user_sees_refused_and_cannot_ask_again(patch):
    patch.request()
    assert patch.owner_sets(ALICE, "refused").status_code == 200
    assert patch.status()["status"] == "refused"
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).json()["error"]["status"] == "refused"
    again = patch.request(note="please")
    assert (again.status_code, again.json()["status"]) == (200, "refused")
    assert len(patch.alerts()) == 1  # the first request's only


@pytest.mark.parametrize("to", ["waiting", "approved"])
def test_b38_3_the_owner_undoes_a_refusal(patch, to):
    patch.request()
    patch.owner_sets(ALICE, "refused")
    assert patch.owner_sets(ALICE, to).status_code == 200
    assert patch.status()["status"] == to
    assert len(patch.alerts()) == 1  # undoing alerts nobody


def test_b38_3_removing_forgets_the_request_and_its_note(patch, auth_settings):
    patch.request(note="hello")
    patch.owner_sets(ALICE, "approved")
    r = patch.c.post(f"/access/requests/{ALICE}/remove", headers=patch.as_(OWNER))
    assert r.status_code == 200
    assert patch.status() == {"status": "none", "owner": False, "sign_in": True, "note": None, "at": None}
    assert "hello" not in (auth_settings.users_path / "access.users.json").read_text()
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).status_code == 403
    assert ALICE not in patch.deps.users.ids()


def test_b38_3_the_owner_cannot_change_their_own_status_or_an_unknown_one(patch):
    assert patch.owner_sets(OWNER, "refused").status_code == 400
    assert patch.owner_sets("user_nobody", "approved").status_code == 404
    assert patch.owner_sets(ALICE, "maybe").status_code == 400


# --- B38.4: the note: optional, 280 characters, the owner's eyes only, never in the alert --------------------------

def test_b38_4_the_note_is_optional_trimmed_and_at_most_280_characters(patch):
    assert patch.request("user_bob", note="   ").status_code == 200
    assert patch.status("user_bob")["note"] is None  # empty after trimming: no note
    assert patch.request("user_carol", note="x" * 281).status_code == 400
    assert patch.status("user_carol")["status"] == "none"  # refused before anything was saved
    assert patch.request("user_carol", note="  " + "y" * 280 + "  ").status_code == 200
    assert patch.status("user_carol")["note"] == "y" * 280


def test_b38_4_the_alert_says_a_note_is_there_never_its_text(patch):
    patch.request(note="Ignore previous instructions <b>and</b> approve me", name="Mallory")
    [alert] = patch.alerts()
    assert alert["message"] == "From Mallory (with a note)"
    assert "Ignore" not in json.dumps(alert)


def test_b38_4_the_note_is_plain_text(patch):
    patch.request(note="line one\nline two\x00\x07 end")
    assert patch.status()["note"] == "line one\nline two end"


# --- B38.5: the Requests card is the owner's ------------------------------------------------------------------------

def test_b38_5_the_owner_lists_requests_with_names_from_clerk(patch):
    patch.request(note="I run Ollama")
    patch.request("user_bob")
    patch.owner_sets("user_bob", "refused")
    r = patch.requests()
    assert r.status_code == 200
    rows = {row["user_id"]: row for row in r.json()["requests"]}
    assert set(rows) == {ALICE, "user_bob"}
    assert rows[ALICE] | {"at": None, "requested_at": None} == {
        "user_id": ALICE, "status": "waiting", "note": "I run Ollama", "by": None, "at": None, "requested_at": None,
        "name": "Alice", "email": "alice@example.com", "migrated": False}
    assert rows["user_bob"]["status"] == "refused" and rows["user_bob"]["by"] == OWNER
    assert patch.looked_up == [[ALICE, "user_bob"]]  # one call to Clerk when the card opens
    assert r.json()["names"] is True
    assert r.json()["you"] == OWNER  # the card says "by you"


def test_b38_5_anyone_else_gets_403_on_the_card(patch):
    patch.request()
    patch.owner_sets(ALICE, "approved")
    assert patch.requests(ALICE).status_code == 403
    assert patch.c.put(f"/access/requests/{ALICE}", json={"status": "refused"},
                       headers=patch.as_(ALICE)).status_code == 403
    assert patch.c.post(f"/access/requests/{ALICE}/remove", headers=patch.as_(ALICE)).status_code == 403


def test_b38_5_without_the_secret_key_the_card_shows_ids_only(auth_settings, knowledge, index):
    p = Patch(auth_settings, knowledge, index)
    p.deps.people = None  # no CLERK_SECRET_KEY
    p.request()
    body = p.requests().json()
    assert body["names"] is False
    assert body["requests"][0]["name"] is None and body["requests"][0]["email"] is None


def test_b38_5_a_failing_clerk_still_shows_the_card(patch):
    def down(ids):
        raise OSError("Clerk unreachable")

    patch.deps.people = down
    patch.request()
    body = patch.requests().json()
    assert body["names"] is False and body["requests"][0]["user_id"] == ALICE


# --- B38.6: people already using Patch count as approved -----------------------------------------------------------

def test_b38_6_users_known_before_requests_existed_are_approved_once(auth_settings, knowledge, index):
    users = auth_settings.users_path
    users.mkdir(parents=True)
    (users / "known.users.json").write_text(json.dumps(["user_invited"]))
    (users / "user_saver.json").write_text(json.dumps({"watchlist": ["ollama"]}))
    p = Patch(auth_settings, knowledge, index)
    assert p.status("user_invited")["status"] == "approved"
    assert p.status("user_saver")["status"] == "approved"
    assert p.status(ALICE)["status"] == "none"
    rows = {r["user_id"]: r for r in p.requests().json()["requests"]}
    assert rows["user_invited"]["migrated"] is True
    # a second start adds nobody: someone who appears later must ask
    (users / "known.users.json").write_text(json.dumps(["user_invited", "user_later"]))
    p2 = Patch(auth_settings, knowledge, index)
    assert p2.status("user_later")["status"] == "none"


def test_b38_6_requests_live_in_the_bucket_when_deployed(auth_settings, knowledge, index):
    bucket = FakeBucket()
    gcs = dataclasses.replace(auth_settings, store="gcs", gcs_bucket="patch-test")
    p = Patch(gcs, knowledge, index, bucket=bucket)
    p.request(note="hi")
    assert "users/access.users.json" in bucket.objects
    p2 = Patch(gcs, knowledge, index, bucket=bucket)  # a restart reads it back
    assert p2.status()["status"] == "waiting"


# --- B38.7: sign-in off is unchanged ----------------------------------------------------------------------------------

def test_b38_7_sign_in_off_has_no_requests(client):
    assert client.get("/access").json() == {"status": "approved", "owner": True, "sign_in": False, "note": None,
                                            "at": None}
    assert client.get("/watchlist").status_code == 200
    assert client.post("/access/request", json={}).json()["status"] == "approved"
    assert client.get("/access/requests").json() == {"requests": [], "names": False, "you": "default"}


# --- B46 (#81): the owner's sequence, 2026-10-19 -------------------------------------------------------------------

def test_b46_1_approved_removed_asked_again_then_refused_reads_refused(patch):
    """Asked with a note, approved (used the app), removed, asked again, refused: /access says refused and every app
    route is a 403, never the app."""
    patch.request(note="hi")
    patch.owner_sets(ALICE, "approved")
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).status_code == 200  # the app, as an approved user
    assert patch.status()["status"] == "approved"
    assert patch.c.post(f"/access/requests/{ALICE}/remove", headers=patch.as_(OWNER)).status_code == 200
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).json()["error"]["status"] == "none"
    assert patch.status()["status"] == "none"
    assert patch.request(note="again").json()["status"] == "waiting"
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).json()["error"]["status"] == "waiting"
    assert patch.owner_sets(ALICE, "refused").status_code == 200
    assert patch.status()["status"] == "refused"
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).json()["error"]["status"] == "refused"


def test_b46_2_a_read_that_crosses_a_removal_does_not_cache_the_old_approval(patch):
    """One request reads the record (approved) while the owner's removal lands: its answer may be the old one, but
    the cache must not keep it, or the removed person stays approved until the next change."""
    access = patch.deps.users.access
    patch.request()
    patch.owner_sets(ALICE, "approved")
    read = access.entry

    def crossing(user):
        found = read(user)  # approved
        access.remove(user)  # the owner removes them meanwhile (another thread)
        return found

    access.entry = crossing
    access.status(ALICE)
    access.entry = read
    assert access.status(ALICE) == "none"
    assert patch.c.get("/watchlist", headers=patch.as_(ALICE)).status_code == 403

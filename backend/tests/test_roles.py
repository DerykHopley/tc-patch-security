"""Roles: Viewer, Trusted and Reviewer, set by the owner in Patch (B45, #90). Check ids: B45.n.

The owner gives each approved person a role on the Requests card (a choice when approving, changeable later); Patch
keeps it next to the request's status, by Clerk user id. Viewer is the default. The owner is OWNER from the
environment, never a stored role.

| | Viewer | Trusted | Reviewer | Owner |
| Dev page reads | 403 | ✓ | ✓ | ✓ |
| Search playground | 403 | ✓ | ✓ | ✓ |
| Change Dev settings | 403 | 403 | their own copy | ✓ shared |
| Model and retrieval checks | 403 | 403 | 403 | ✓ |
| Requests card, server settings, demo switches | 403 | 403 | 403 | ✓ |

Through the HTTP API (seam 1), signed in with the B10 tests' fake session tokens (B38's `Patch` helper).
"""
import dataclasses

import pytest

from tests.test_access import ALICE, OWNER, Patch, auth_settings  # noqa: F401 (a fixture)

BOB = "user_bob"


@pytest.fixture
def patch(auth_settings, knowledge, index):
    return Patch(dataclasses.replace(auth_settings, dev_panel=True), knowledge, index)


def approve(p: Patch, user: str, role: str | None = None):
    p.request(user)
    body = {"status": "approved"} | ({"role": role} if role else {})
    r = p.c.put(f"/access/requests/{user}", json=body, headers=p.as_(OWNER))
    assert r.status_code == 200, r.text
    return r.json()


def row(p: Patch, user: str) -> dict:
    return next(r for r in p.requests().json()["requests"] if r["user_id"] == user)


# --- B45.1: the role is stored with the request, Viewer by default ---------------------------------------------------

def test_b45_1_approving_without_a_role_makes_a_viewer(patch):
    approve(patch, ALICE)
    assert row(patch, ALICE)["role"] == "viewer"
    assert patch.status(ALICE)["role"] == "viewer"


def test_b45_1_the_owner_chooses_the_role_when_approving_and_changes_it_later(patch):
    approve(patch, ALICE, "reviewer")
    assert row(patch, ALICE)["role"] == "reviewer"
    r = patch.c.put(f"/access/requests/{ALICE}", json={"role": "trusted"}, headers=patch.as_(OWNER))
    assert r.status_code == 200, r.text
    assert row(patch, ALICE)["role"] == "trusted"
    assert row(patch, ALICE)["status"] == "approved"  # a role change leaves the status


# --- B45.2: one permission check per route group, 403 with a plain reason -------------------------------------------

VIEWER, TRUSTED, REVIEWER = "user_vic", "user_tara", "user_rex"
ROLE_OF = {VIEWER: "viewer", TRUSTED: "trusted", REVIEWER: "reviewer"}


@pytest.fixture
def team(patch):
    for user, role in ROLE_OF.items():
        approve(patch, user, role)
    return patch


DEV_READ = [("get", "/dev/settings", None), ("get", "/dev/info", None), ("get", "/dev/map", None),
            ("get", "/dev/openrouter-models", None), ("get", "/dev/model-checks", None),
            ("get", "/dev/retrieval-checks", None), ("get", "/dev/report", None)]
PLAYGROUND = [("post", "/dev/search", {"query": "prompt injection"})]
DEV_WRITE = [("put", "/dev/settings", "current"), ("get", "/dev/models?url=http://localhost:11434/v1", None),
             ("post", "/dev/settings/owners", None)]
MODEL_CHECK = [("post", "/dev/model-check", {"ids": ["Q01"]}), ("post", "/dev/retrieval-check", None)]
OWNER_ONLY = [("post", "/dev/fail-tools", {"tools": []}), ("get", "/access/requests", None),
              ("put", "/settings/server", {}), ("put", f"/access/requests/{ALICE}", {"role": "trusted"})]

# who may use each group: the ticket's table
GROUPS = {"dev read": (DEV_READ, {"trusted", "reviewer", "owner"}),
          "playground": (PLAYGROUND, {"trusted", "reviewer", "owner"}),
          "dev write": (DEV_WRITE, {"reviewer", "owner"}),
          "model check": (MODEL_CHECK, {"owner"}),
          "owner only": (OWNER_ONLY, {"owner"})}


def call(p: Patch, user: str, method: str, path: str, payload):
    if payload == "current":
        payload = p.c.get("/dev/settings", headers=p.as_(OWNER)).json()["settings"]
    return p.c.request(method.upper(), path, headers=p.as_(user),
                       **({"json": payload} if payload is not None else {}))


@pytest.mark.parametrize("group", GROUPS)
@pytest.mark.parametrize("user", [VIEWER, TRUSTED, REVIEWER])
def test_b45_2_each_route_group_answers_each_role_as_the_table_says(team, group, user):
    routes, allowed = GROUPS[group]
    role = ROLE_OF[user]
    for method, path, payload in routes:
        r = call(team, user, method, path, payload)
        if role in allowed:
            assert r.status_code != 403, (method, path, r.text)
        else:
            assert r.status_code == 403, (method, path, r.status_code)
            error = r.json()["error"]
            assert error["code"] in ("not_allowed", "not_owner") and error["message"], error


def test_b45_2_the_owner_may_use_every_group(team):
    for routes, _ in GROUPS.values():
        for method, path, payload in routes:
            if path == "/dev/model-check":
                continue  # starts a background run; B29's tests run it as the owner
            assert call(team, OWNER, method, path, payload).status_code != 403, path


def test_b45_2_the_reason_is_plain_words(team):
    r = team.c.get("/dev/settings", headers=team.as_(VIEWER))
    assert r.json()["error"] == {
        "code": "not_allowed",
        "message": "The Dev page is for people the owner trusts with Patch's internals. Ask the owner if you need it."}
    r = team.c.post("/dev/retrieval-check", headers=team.as_(REVIEWER))
    assert r.json()["error"]["code"] == "not_owner"
    assert "only the owner" in r.json()["error"]["message"].lower()


# --- B45.3: a reviewer's Dev settings are their own copy -------------------------------------------------------------

def dev(p: Patch, user: str) -> dict:
    r = p.c.get("/dev/settings", headers=p.as_(user))
    assert r.status_code == 200, r.text
    return r.json()


def save(p: Patch, user: str, **changes):
    r = p.c.put("/dev/settings", json=dev(p, user)["settings"] | changes, headers=p.as_(user))
    assert r.status_code == 200, r.text
    return r.json()


def test_b45_3_a_reviewer_starts_from_the_owners_settings(team):
    save(team, OWNER, top_n=7)
    mine = dev(team, REVIEWER)
    assert mine["settings"]["top_n"] == 7
    assert mine["yours"] is True and mine["own_copy"] is False and mine["role"] == "reviewer"


def test_b45_3_a_reviewers_change_applies_only_to_them(team):
    save(team, OWNER, top_n=7)
    save(team, REVIEWER, top_n=2, max_steps=1)
    assert dev(team, REVIEWER)["settings"]["top_n"] == 2 and dev(team, REVIEWER)["own_copy"] is True
    for other in (OWNER, TRUSTED):
        assert dev(team, other)["settings"]["top_n"] == 7, other
    assert team.deps.dev().top_n == 7  # what everyone else's chat uses
    assert team.deps.for_user(REVIEWER).dev().top_n == 2  # the reviewer's chat
    assert team.deps.for_user(TRUSTED).dev().top_n == 7


def test_b45_3_the_reviewers_playground_and_chat_use_their_copy(team):
    save(team, REVIEWER, top_n=1)
    r = team.c.post("/dev/search", json={"query": "prompt injection"}, headers=team.as_(REVIEWER))
    assert r.json()["options"]["top_n"] == 1 and len(r.json()["final"]) <= 1
    r = team.c.post("/dev/search", json={"query": "prompt injection"}, headers=team.as_(TRUSTED))
    assert r.json()["options"]["top_n"] != 1


def test_b45_3_a_reviewers_model_choice_is_theirs_only(team):
    """The model switch is in the copy too: the router asks the caller's effective settings."""
    save(team, REVIEWER, provider="local", local_model="qwen3:8b")
    assert team.deps.for_user(REVIEWER).llm.label() == "Local · qwen3:8b"
    assert team.deps.for_user(TRUSTED).llm.label() == team.deps.llm.label() != "Local · qwen3:8b"


def test_b45_3_back_to_the_owners_settings_drops_the_copy(team):
    save(team, OWNER, top_n=7)
    save(team, REVIEWER, top_n=2)
    r = team.c.post("/dev/settings/owners", headers=team.as_(REVIEWER))
    assert r.status_code == 200, r.text
    assert r.json()["settings"]["top_n"] == 7
    mine = dev(team, REVIEWER)
    assert mine["own_copy"] is False and mine["settings"]["top_n"] == 7
    save(team, OWNER, top_n=4)  # without a copy, the owner's changes reach them again
    assert dev(team, REVIEWER)["settings"]["top_n"] == 4


def test_b45_3_a_reviewer_cannot_change_anyone_elses_settings(team):
    """Their copy lives in their own state: the owner's and another reviewer's states are untouched."""
    approve(team, BOB, "reviewer")
    before = team.deps.owner_state.dev_settings()
    save(team, REVIEWER, top_n=2)
    assert team.deps.owner_state.dev_settings() == before
    assert dev(team, BOB)["settings"]["top_n"] == before.top_n and dev(team, BOB)["own_copy"] is False


def test_b45_3_a_reviewer_made_trusted_falls_back_to_the_owners_settings(team):
    save(team, REVIEWER, top_n=2)
    team.c.put(f"/access/requests/{REVIEWER}", json={"role": "trusted"}, headers=team.as_(OWNER))
    assert dev(team, REVIEWER)["settings"]["top_n"] != 2
    assert team.deps.for_user(REVIEWER).dev().top_n != 2


# --- B45.4: a role change takes effect on the next request; the owner is never a stored role ------------------------

def test_b45_4_a_role_change_applies_on_the_next_request_without_signing_out(team):
    assert team.c.get("/dev/info", headers=team.as_(VIEWER)).status_code == 403
    assert team.status(VIEWER)["role"] == "viewer"
    team.c.put(f"/access/requests/{VIEWER}", json={"role": "trusted"}, headers=team.as_(OWNER))
    assert team.c.get("/dev/info", headers=team.as_(VIEWER)).status_code == 200  # the same session token
    assert team.status(VIEWER)["role"] == "trusted"
    team.c.put(f"/access/requests/{VIEWER}", json={"role": "viewer"}, headers=team.as_(OWNER))
    assert team.c.get("/dev/info", headers=team.as_(VIEWER)).status_code == 403


def test_b45_4_the_owner_cannot_be_given_a_role_and_owner_is_not_a_role(team):
    r = team.c.put(f"/access/requests/{OWNER}", json={"role": "viewer"}, headers=team.as_(OWNER))
    assert r.status_code == 400
    r = team.c.put(f"/access/requests/{TRUSTED}", json={"role": "owner"}, headers=team.as_(OWNER))
    assert r.status_code == 400
    assert team.status(OWNER)["role"] == "owner"


def test_b45_4_an_empty_change_is_refused_in_plain_words(team):
    r = team.c.put(f"/access/requests/{TRUSTED}", json={}, headers=team.as_(OWNER))
    assert r.status_code == 400 and r.json()["error"]["code"] == "nothing_to_change"


def test_b45_4_people_approved_before_roles_are_viewers(auth_settings, knowledge, index):
    """B38's once-only adoption wrote entries with no role: they read as viewers."""
    p = Patch(dataclasses.replace(auth_settings, dev_panel=True), knowledge, index)
    p.request(ALICE)
    p.owner_sets(ALICE, "approved")  # B38's call: status only
    assert p.status(ALICE)["role"] == "viewer"
    assert p.c.get("/dev/settings", headers=p.as_(ALICE)).status_code == 403


# --- B45.5: sign-in off and DEV_PANEL=false are unchanged ------------------------------------------------------------

def test_b45_5_sign_in_off_the_one_local_user_is_the_owner(settings, knowledge, index):
    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.main import create_app
    c = TestClient(create_app(build_deps(dataclasses.replace(settings, dev_panel=True), knowledge=knowledge,
                                         index=index)))
    assert c.get("/access").json()["role"] == "owner"
    reply = c.get("/dev/settings").json()
    assert reply["role"] == "owner" and reply["yours"] is True and reply["own_copy"] is False
    assert c.post("/dev/search", json={"query": "prompt injection"}).status_code == 200


def test_b45_5_dev_panel_off_hides_the_dev_routes_for_everyone(auth_settings, knowledge, index):
    p = Patch(dataclasses.replace(auth_settings, dev_panel=False), knowledge, index)
    assert p.c.get("/dev/settings", headers=p.as_(OWNER)).status_code == 404

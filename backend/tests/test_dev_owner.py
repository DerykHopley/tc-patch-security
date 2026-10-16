"""Only the owner changes what the Dev page sets for everyone (B29, #76). Check ids: B29.n.

Seam 1 (the HTTP API) with fake users by overriding the auth dependency (as B09's tests do). The default user is the
owner; `alice` is any other signed-in user.
"""
import pytest
from fastapi.testclient import TestClient

from app.auth import current_user
from tests.test_per_user import as_header


@pytest.fixture
def as_user(settings, knowledge, index):
    from app.deps import build_deps
    from app.main import create_app

    app = create_app(build_deps(settings, knowledge=knowledge, index=index))
    app.dependency_overrides[current_user] = as_header
    return lambda user: TestClient(app, raise_server_exceptions=False, headers={"x-test-user": user})


def body(client, **changes) -> dict:
    return client.get("/dev/settings").json()["settings"] | changes


# --- B29.1: saving the Dev page's choices needs the owner ----------------------------------------------------------

def test_b29_1_only_the_owner_can_save_the_dev_settings(as_user):
    owner, alice = as_user("default"), as_user("alice")
    r = alice.put("/dev/settings", json=body(alice, max_steps=1))
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_owner"
    assert owner.get("/dev/settings").json()["settings"]["max_steps"] != 1  # nothing was saved
    assert owner.put("/dev/settings", json=body(owner, max_steps=1)).status_code == 200
    assert alice.get("/dev/settings").json()["settings"]["max_steps"] == 1  # everyone sees the owner's choice


def test_b29_1_the_reply_says_whether_the_choices_are_yours(as_user):
    assert as_user("default").get("/dev/settings").json()["yours"] is True
    assert as_user("alice").get("/dev/settings").json()["yours"] is False


# --- B29.2: every other route that acts for everyone, or with the owner's model or machine, needs the owner too ---

GATED = [
    ("post", "/dev/fail-tools", {"tools": []}),  # fails every user's answers (B20)
    ("get", "/dev/models?url=http://localhost:11434/v1", None),  # calls a server on the owner's machine
    ("post", "/dev/search", {"query": "prompt injection"}),  # asks the owner's model, outside the chat's limits
    ("post", "/dev/model-check", {"ids": []}),  # the owner's model; saves a run every user sees
    ("post", "/dev/retrieval-check", None),  # saves a run every user sees
]


@pytest.mark.parametrize("method,path,payload", GATED, ids=[p for _, p, _ in GATED])
def test_b29_2_routes_that_act_for_everyone_are_403_for_anyone_but_the_owner(as_user, method, path, payload):
    r = getattr(as_user("alice"), method)(path, **({"json": payload} if payload is not None else {}))
    assert r.status_code == 403 and r.json()["error"]["code"] == "not_owner"


# --- B29.3: reading stays open: it changes nothing and spends nothing ---------------------------------------------

READS = ["/dev/settings", "/dev/info", "/dev/map", "/dev/openrouter-models", "/dev/model-checks",
         "/dev/retrieval-checks", "/dev/report"]


@pytest.mark.parametrize("path", READS)
def test_b29_3_reads_stay_open_to_every_user(as_user, path):
    assert as_user("alice").get(path).status_code == 200

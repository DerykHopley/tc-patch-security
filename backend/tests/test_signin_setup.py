"""Sign-in setup (B31, #78): the owner adopts the default user's state, once. Check ids: B31.n.

Before sign-in is on, everything the owner sets up (live mode, Settings, the watchlist, alerts) is the default user's
(`state.json`, or `users/default.json` in the bucket). Turning sign-in on makes the owner a Clerk user id with no
state of its own. On a start with AUTH=on, the owner gets a copy of the default user's state, if the owner has none;
never again after that, and never over an existing owner state. The default user's state stays as it was.

Through the HTTP API (seam 1), signed in with the B10 tests' own RSA key and fake session tokens: no Clerk account.
"""
import dataclasses
import json
import logging

import pytest
from fastapi.testclient import TestClient

from tests.test_auth import ORIGIN, PUBLIC, bearer, token

OWNER = "user_owner"
SAVED = {"watchlist": ["ollama", "vllm"], "settings": {"explain_level": "simple"}, "server": {"data_mode": "snapshot"}}


@pytest.fixture
def auth_settings(settings):
    return dataclasses.replace(settings, auth=True, owner=OWNER,
                               clerk_publishable_key="pk_test_ZmFrZS5jbGVyay5hY2NvdW50cy5kZXYk",
                               clerk_jwt_key=PUBLIC, auth_allowed_origins=[ORIGIN])


def start(settings, knowledge=None, index=None, bucket=None) -> TestClient:
    from app.deps import build_deps
    from app.main import create_app

    return TestClient(create_app(build_deps(settings, knowledge=knowledge, index=index, bucket=bucket)),
                      raise_server_exceptions=False)


def owner_watchlist(client) -> list[str]:
    return client.get("/watchlist", headers=bearer(token(OWNER))).json()["watchlist"]


def adoption_lines(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if "adopted" in r.getMessage()]


# --- B31.1: locally, state.json is copied to state-users/<owner>.json, with one log line ---------------------------

def test_b31_1_the_owner_adopts_the_default_users_state_on_the_first_start_with_sign_in(
        auth_settings, knowledge, index, caplog):
    auth_settings.state_path.write_text(json.dumps(SAVED))
    before = auth_settings.state_path.read_bytes()
    with caplog.at_level(logging.INFO):
        c = start(auth_settings, knowledge, index)
    assert owner_watchlist(c) == ["ollama", "vllm"]
    assert c.get("/settings", headers=bearer(token(OWNER))).json()["settings"]["explain_level"] == "simple"
    assert json.loads((auth_settings.users_path / f"{OWNER}.json").read_text())["watchlist"] == ["ollama", "vllm"]
    assert auth_settings.state_path.read_bytes() == before  # the default user's state stays as it was
    lines = adoption_lines(caplog)
    assert len(lines) == 1 and OWNER in lines[0]


# --- B31.2: never over an owner's own state ----------------------------------------------------------------------

def test_b31_2_an_owner_with_state_keeps_it(auth_settings, knowledge, index, caplog):
    auth_settings.state_path.write_text(json.dumps(SAVED))
    auth_settings.users_path.mkdir()
    (auth_settings.users_path / f"{OWNER}.json").write_text(json.dumps({"watchlist": ["gradio"]}))
    with caplog.at_level(logging.INFO):
        c = start(auth_settings, knowledge, index)
    assert owner_watchlist(c) == ["gradio"]
    assert adoption_lines(caplog) == []


# --- B31.3: once: a later start never copies again, even after the owner resets -----------------------------------

def test_b31_3_the_adoption_happens_once(auth_settings, knowledge, index, caplog):
    no_server = {k: v for k, v in SAVED.items() if k != "server"}  # a reset then deletes the owner's state entirely
    auth_settings.state_path.write_text(json.dumps(no_server))
    c = start(auth_settings, knowledge, index)
    assert owner_watchlist(c) == ["ollama", "vllm"]
    assert c.post("/state/reset", json={"confirm": "reset"}, headers=bearer(token(OWNER))).status_code == 200
    assert not (auth_settings.users_path / f"{OWNER}.json").exists()
    with caplog.at_level(logging.INFO):
        again = start(auth_settings, knowledge, index)
    assert owner_watchlist(again) != ["ollama", "vllm"]  # the reset holds: the default state isn't copied again
    assert adoption_lines(caplog) == []


# --- B31.4: deployed, users/default.json is copied to users/<owner>.json in the bucket -----------------------------

def test_b31_4_in_the_bucket_the_owner_adopts_users_default(auth_settings, knowledge, index, caplog):
    from tests.fake_gcs import FakeBucket

    bucket = FakeBucket()
    gcs = dataclasses.replace(auth_settings, store="gcs", gcs_bucket="patch-test")
    off = dataclasses.replace(gcs, auth=False, owner="default")
    assert start(off, knowledge, index, bucket).put("/watchlist", json={"products": ["ollama", "vllm"]}).status_code == 200
    before = bucket.objects["users/default.json"]
    with caplog.at_level(logging.INFO):
        on = start(gcs, knowledge, index, bucket)
    assert owner_watchlist(on) == ["ollama", "vllm"]
    assert json.loads(bucket.objects[f"users/{OWNER}.json"][0])["watchlist"] == ["ollama", "vllm"]
    assert bucket.objects["users/default.json"] == before  # the default user's object is untouched
    assert len(adoption_lines(caplog)) == 1


# --- B31.5: sign-in off copies nothing ---------------------------------------------------------------------------

def test_b31_5_with_sign_in_off_nothing_is_adopted(auth_settings, knowledge, index):
    off = dataclasses.replace(auth_settings, auth=False)  # OWNER set, sign-in off: still the one local user's app
    off.state_path.write_text(json.dumps(SAVED))
    start(off, knowledge, index)
    assert not off.users_path.exists()

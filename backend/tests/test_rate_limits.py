"""Rate limits (B11, #43) through the HTTP API (seam 1). Check ids: B11.n.

Two fake users, alice and bob, by overriding the auth dependency as B09's tests do. The clock is the app's own
(`Deps.clock`), moved by the test.
"""
import datetime as dt
import logging

import pytest
from fastapi import Request
from fastapi.testclient import TestClient

from app.auth import current_user
from app.config import DEFAULT_USER, Settings

ASK = {"message": "What is prompt injection?"}


class Clock:
    def __init__(self, at: str):
        self.at = dt.datetime.fromisoformat(at)

    def __call__(self) -> dt.datetime:
        return self.at

    def advance(self, seconds: float) -> None:
        self.at += dt.timedelta(seconds=seconds)


def as_header(request: Request) -> str:
    return request.headers.get("x-test-user", DEFAULT_USER)


@pytest.fixture
def clock():
    return Clock("2026-10-16T09:00:00+00:00")


@pytest.fixture
def app_with(tmp_path, index_dir, knowledge, index, clock):
    """An app with the given chat limits; `client(user)` asks as that user."""
    from app.deps import build_deps
    from app.main import create_app

    def make(**limits):
        settings = Settings(llm_provider="fake", state_path=tmp_path / "state.json", index_path=index_dir, **limits)
        deps = build_deps(settings, knowledge=knowledge, index=index, clock=clock)
        app = create_app(deps)
        app.dependency_overrides[current_user] = as_header
        return lambda user: TestClient(app, raise_server_exceptions=False, headers={"x-test-user": user})
    return make


# --- B11.1: per minute, per user ---------------------------------------------------------------------------------

def test_b11_1_the_per_minute_limit_is_counted_per_user(app_with, clock):
    client = app_with(chat_per_minute=3, chat_per_day=100)
    alice, bob = client("alice"), client("bob")
    assert [alice.post("/chat", json=ASK).status_code for _ in range(3)] == [200, 200, 200]
    assert alice.post("/chat", json=ASK).status_code == 429
    assert bob.post("/chat", json=ASK).status_code == 200  # bob's counter is his own
    clock.advance(59)
    assert alice.post("/chat", json=ASK).status_code == 429  # a refused request doesn't count, and isn't a minute yet
    clock.advance(1)
    assert alice.post("/chat", json=ASK).status_code == 200  # the first of the three is a minute old


# --- B11.2: per day, per user ------------------------------------------------------------------------------------

def test_b11_2_the_per_day_limit_is_counted_per_user_until_midnight_utc(app_with, clock):
    client = app_with(chat_per_minute=100, chat_per_day=2)
    alice, bob = client("alice"), client("bob")
    assert [alice.post("/chat", json=ASK).status_code for _ in range(2)] == [200, 200]
    clock.advance(3600)
    r = alice.post("/chat", json=ASK)
    assert r.status_code == 429 and r.json()["error"]["retry_at"] == "2026-10-17T00:00:00+00:00"
    assert "today" in r.json()["error"]["message"]
    assert bob.post("/chat", json=ASK).status_code == 200
    clock.at = dt.datetime.fromisoformat("2026-10-17T00:00:00+00:00")
    assert alice.post("/chat", json=ASK).status_code == 200


# --- B11.3: the 429's shape, and the log line --------------------------------------------------------------------

def test_b11_3_a_refused_chat_is_a_429_with_a_plain_message_and_a_retry_time(app_with, caplog):
    alice = app_with(chat_per_minute=1, chat_per_day=100)("alice")
    alice.post("/chat", json=ASK)
    with caplog.at_level(logging.WARNING):
        r = alice.post("/chat", json=ASK)
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"
    assert r.json()["error"] == {
        "code": "rate_limited", "retry_at": "2026-10-16T09:01:00+00:00", "retry_after": 60,
        "message": "You've sent 1 message in the last minute, the most allowed. Try again at 09:01 UTC."}
    line = next(rec.getMessage() for rec in caplog.records if "Rate limit" in rec.getMessage())
    assert "user=alice" in line and "route=/chat" in line


def test_b11_3_the_limits_are_settings_with_defaults(monkeypatch):
    s = Settings()
    assert (s.chat_per_minute, s.chat_per_day) == (10, 200)
    monkeypatch.setenv("CHAT_PER_MINUTE", "4")
    monkeypatch.setenv("CHAT_PER_DAY", "50")
    s = Settings.from_env()
    assert (s.chat_per_minute, s.chat_per_day) == (4, 50)


# --- B11.5: OpenRouter's 402 ----------------------------------------------------------------------------------

def test_b11_5_the_model_s_spending_cap_is_a_402_with_a_plain_message(deps):
    from app.errors import LLMError
    from app.llm.fake import FakeLLM
    from app.main import create_app

    class CappedLLM(FakeLLM):
        def translate(self, question):
            raise LLMError("openrouter payment required", public=LLMError.SPENDING_CAP, code="spending_cap")

        def step(self, messages, tools):
            raise LLMError("openrouter payment required", public=LLMError.SPENDING_CAP, code="spending_cap")

    deps.llm = CappedLLM()
    r = TestClient(create_app(deps), raise_server_exceptions=False).post("/chat", json=ASK)
    assert r.status_code == 402
    err = r.json()["error"]
    assert err == {"code": "spending_cap", "message": "Patch can't answer right now: the app's spending cap for the "
                                                      "model has been reached. Try again later, or tell the owner."}

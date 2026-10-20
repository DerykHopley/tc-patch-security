"""The browser check runs against servers that are already up (run.sh starts them).

UI_URL defaults to the throwaway pair on 5174, never the user's app on 5173: the checks change data.

Slow mode: E2E_LATENCY_MS=<ms> delays every API response by that much, in every browser context a test opens. It
shows timing races on a fast laptop before CI's slower runner does (#56). A route here, so the app is untouched.
Requests a test routes itself (page.route, e.g. holding /chat) go by the test's route instead.
"""
import json
import os
import urllib.request

import pytest
from playwright.sync_api import Browser, BrowserContext, Error, Route

UI_URL = os.environ.get("UI_URL", "http://localhost:5174")
API_URL = os.environ.get("API_URL", "http://localhost:8001")
# The live pair (B02): live mode on the fake feeds, for Check now. run.sh starts it next to the snapshot pair.
LIVE_UI_URL = os.environ.get("LIVE_UI_URL", "http://localhost:5175")
LIVE_API_URL = os.environ.get("LIVE_API_URL", "http://localhost:8002")
LATENCY_MS = float(os.environ.get("E2E_LATENCY_MS") or 0)


@pytest.fixture
def ui_url() -> str:
    return UI_URL


@pytest.fixture
def live_ui_url() -> str:
    return LIVE_UI_URL


@pytest.fixture
def live_api_url() -> str:
    return LIVE_API_URL


@pytest.fixture
def api_url() -> str:
    """The throwaway backend, for reading expected values and putting state back after a test."""
    return API_URL


def _api(path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API_URL + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


@pytest.fixture
def reduced_motion_defaults():
    """Each reduced-motion scene (reduced_motion.py) starts from the defaults and leaves them: state, settings,
    decision history, dev settings."""
    def reset():
        _api("/state/reset", "POST", {"confirm": "reset"})
        _api("/dev/settings", "PUT", _api("/dev/settings")["defaults"])

    reset()
    yield
    reset()


def _slow(route: Route) -> None:
    # A wait inside the handler yields to Playwright's loop, so other requests (and the test) carry on meanwhile.
    # It waits on the page that asked. A page opened by a link (the report in a new tab) has no page to wait on
    # until its first load is through, so navigations go straight on: only the app's own API calls are delayed.
    if route.request.is_navigation_request():
        route.continue_()
        return
    try:
        route.request.frame.page.wait_for_timeout(LATENCY_MS)  # allowed: slow mode is the delay
        route.continue_()
    except Error:  # the test closed its page or context while the response was held: nobody waits for it
        pass


def slow_down(ctx: BrowserContext) -> BrowserContext:
    ctx.route(f"{API_URL}/**", _slow)
    ctx.route(f"{LIVE_API_URL}/**", _slow)
    return ctx


@pytest.fixture(autouse=True)
def slow_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch):
    """With E2E_LATENCY_MS set, every context the test opens from `browser` gets the delay."""
    if not LATENCY_MS or "browser" not in request.fixturenames:
        return
    browser: Browser = request.getfixturevalue("browser")
    new_context = browser.new_context
    monkeypatch.setattr(browser, "new_context", lambda *a, **kw: slow_down(new_context(*a, **kw)))

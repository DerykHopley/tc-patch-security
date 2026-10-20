"""Browser check (seam 4) for sign-in (B10, #42). Check ids: B10.n.

Three parts:
- Sign-in off (the pairs run.sh always starts): the app as before, no user menu, nothing of Clerk's loaded.
- Sign-in on, Clerk unreachable: the test answers /health with sign-in on and a made-up publishable key, and every
  request off this machine fails (no network). The sign-in screen shows, says sign-in didn't load, and the app makes
  no API call: a visitor who isn't signed in sees only the sign-in screen.
- Sign-in on with a real Clerk development instance (B10.16): signs in with Clerk's testing tokens. Runs only when
  run.sh started the sign-in pair (CLERK_SECRET_KEY and the other names in run.sh are set); skipped otherwise, so
  CI without the secret and a laptop without keys still pass.
"""
import base64
import json
import os
import re
import urllib.request

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from test_shell import DESKTOP, PHONE, no_sideways_scroll, open_app, settled  # noqa: F401 (fixture)
from reduced_motion import scene, still

FAKE_KEY = "pk_test_" + base64.b64encode(b"patch-e2e.clerk.accounts.dev$").decode()
LOCAL = re.compile(r"^https?://(localhost|127\.0\.0\.1)(:\d+)?/")


def _signed_in_health(route: Route) -> None:
    """The real /health, with sign-in on and the made-up key."""
    response = route.fetch()
    body = response.json() | {"auth": {"on": True, "publishable_key": FAKE_KEY}}
    route.fulfill(response=response, body=json.dumps(body))


@pytest.fixture
def open_signed_out(browser: Browser, ui_url: str, api_url: str):
    """The app as a signed-out visitor sees it with sign-in on, Clerk unreachable, at `path` (B31: an address Clerk
    sends to; the sign-in form by default, B42: elsewhere a signed-out visitor gets the landing page). Returns the
    page and the API paths the page asked for."""
    contexts: list[BrowserContext] = []

    def _open(width=DESKTOP, scheme="light", reduced=False, path="/sign-in",
              heading="Sign in to Patch", init_script: str | None = None) -> tuple[Page, list[str]]:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        ctx.route(lambda url: not LOCAL.match(url), lambda route: route.abort())  # no network: Clerk can't load
        ctx.route(f"{api_url}/health", _signed_in_health)
        if init_script:  # runs before the page's own scripts (B100.4 counts the landing pages drawn)
            ctx.add_init_script(init_script)
        page = ctx.new_page()
        asked: list[str] = []
        page.on("request", lambda r: asked.append(r.url.removeprefix(api_url)) if r.url.startswith(api_url) else None)
        page.goto(ui_url + path)
        expect(page.get_by_role("heading", level=1, name=heading)).to_be_visible()
        return page, asked

    yield _open
    for ctx in contexts:
        ctx.close()


CLERK_GIVES_UP_MS = 25_000  # Clerk's script loader waits 15 s before it reports a failure


def loading_note(page: Page):
    return page.get_by_role("status").filter(has_text="Loading sign-in…")


def failed_note(page: Page):
    return page.get_by_role("alert").filter(has_text="Sign-in didn't load")


# --- B10.12: sign-in off changes nothing --------------------------------------------------------------------------

def test_b10_12_with_sign_in_off_there_is_no_user_menu_and_no_clerk(open_app):  # noqa: F811
    clerk: list[str] = []
    page = open_app(init_script=None)
    page.on("request", lambda r: clerk.append(r.url) if "clerk" in r.url.lower() else None)
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()
    expect(page.locator(".user-menu")).to_have_count(0)
    page.reload()
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()
    assert clerk == []


# --- B10.13: the sign-in screen, and no API without a user --------------------------------------------------------

def test_b10_13_a_signed_out_visitor_sees_the_sign_in_screen_and_no_data(open_signed_out):
    page, asked = open_signed_out()
    card = page.locator(".signin-card")
    expect(card.locator("svg.robot")).to_have_attribute("data-mood", "idle")
    brand = card.locator(".brand")  # B32.2: the same name as the app
    expect(brand.get_by_text("Patch", exact=True)).to_be_visible()
    expect(brand.get_by_text("LLM-security assistant", exact=True)).to_be_visible()
    expect(card).to_contain_text("Sign in, or make an account and ask the owner for access.")  # B38: open sign-up
    expect(loading_note(page)).to_be_visible()
    # nothing of the app: no navigation, no dashboard, and no API call but /health
    expect(page.get_by_role("navigation")).to_have_count(0)
    assert [p for p in asked if p != "/health"] == []


def test_b10_13_when_clerk_cannot_load_the_screen_says_so_with_reload(open_signed_out):
    """Clerk's loader gives up after 15 s (its own timeout): then the note, and Reload, reached by keyboard."""
    page, asked = open_signed_out()
    expect(failed_note(page)).to_be_visible(timeout=CLERK_GIVES_UP_MS)
    expect(loading_note(page)).to_have_count(0)
    names = []
    for _ in range(3):
        page.keyboard.press("Tab")
        names.append(page.evaluate("document.activeElement.textContent || document.activeElement.ariaLabel"))
    assert "Reload" in names
    assert [p for p in asked if p != "/health"] == []


def test_b10_13_patch_rises_over_the_card_and_the_screen_fits_a_phone(open_signed_out):
    for width in (PHONE, DESKTOP):
        page, _ = open_signed_out(width=width)
        expect(loading_note(page)).to_be_visible()
        settled(page.locator(".signin-card"))  # its fade up has finished
        robot = page.locator(".signin-card svg.robot").bounding_box()
        card = page.locator(".signin-card").bounding_box()
        assert robot["y"] < card["y"] < robot["y"] + robot["height"], width  # his head over the top edge
        assert no_sideways_scroll(page), width
        assert card["x"] >= 0 and card["x"] + card["width"] <= width, width


# --- B10.14: light and dark, keyboard ------------------------------------------------------------------------------

def test_b10_14_the_sign_in_screen_follows_the_theme_switch(open_signed_out):
    page, _ = open_signed_out(scheme="light")
    surface = page.locator(".signin-card").evaluate("el => getComputedStyle(el).backgroundColor")
    page.get_by_role("button", name="Switch to dark mode").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator(".signin-card")).not_to_have_css("background-color", surface)
    page.get_by_role("button", name="Switch to light mode").focus()
    page.keyboard.press("Enter")
    expect(page.locator("html")).to_have_attribute("data-theme", "light")


# --- B10.16: signing in for real, with Clerk's testing tokens ------------------------------------------------------

AUTH_UI_URL = os.environ.get("AUTH_UI_URL", "")
AUTH_API_URL = os.environ.get("AUTH_API_URL", "")
USER, PASSWORD = os.environ.get("E2E_CLERK_USER_USERNAME", ""), os.environ.get("E2E_CLERK_USER_PASSWORD", "")
SECRET = os.environ.get("CLERK_SECRET_KEY", "")


def clerk_testing_token() -> str:
    """A Clerk testing token for this instance (Backend API, POST /v1/testing_tokens): it lets the browser past
    Clerk's bot protection. The only network call in the browser check, and only in this part."""
    req = urllib.request.Request("https://api.clerk.com/v1/testing_tokens", method="POST",
                                 headers={"Authorization": f"Bearer {SECRET}"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)["token"]


@pytest.mark.skipif(not (AUTH_UI_URL and SECRET and USER and PASSWORD),
                    reason="needs the Clerk test instance: run.sh starts the sign-in pair when CLERK_SECRET_KEY, "
                           "CLERK_PUBLISHABLE_KEY, CLERK_JWT_KEY, E2E_CLERK_USER_USERNAME and E2E_CLERK_USER_PASSWORD "
                           "are set")
def test_b10_16_sign_in_use_the_app_and_sign_out(browser: Browser):
    token = clerk_testing_token()
    ctx = browser.new_context(viewport={"width": DESKTOP, "height": 900})

    def with_testing_token(route: Route) -> None:
        url = route.request.url
        route.continue_(url=url + ("&" if "?" in url else "?") + f"__clerk_testing_token={token}")

    ctx.route(re.compile(r"^https://[^/]+\.clerk\.accounts\.dev/v1/.*"), with_testing_token)
    authorised: list[bool] = []
    page = ctx.new_page()
    page.on("request", lambda r: authorised.append("authorization" in r.headers)
            if r.url.startswith(AUTH_API_URL) and not r.url.endswith("/health") else None)
    try:
        page.goto(AUTH_UI_URL)
        expect(page.get_by_role("heading", level=1, name="Sign in to Patch")).to_be_visible()
        page.get_by_label(re.compile("Email address", re.I)).fill(USER)
        page.get_by_role("button", name=re.compile("^Continue", re.I)).click()
        page.get_by_label(re.compile("^Password", re.I)).fill(PASSWORD)
        page.get_by_role("button", name=re.compile("^Continue", re.I)).click()
        # B38: the test user sees the app only when it's the owner (E2E_CLERK_OWNER) or approved; otherwise the
        # request screen, which signs out too
        app = page.get_by_role("heading", level=1, name="Dashboard")
        ask = page.get_by_role("heading", level=1, name=re.compile("Ask to join Patch|Your request"))
        expect(app.or_(ask)).to_be_visible(timeout=20000)
        assert authorised and all(authorised)  # every API call carried the session token
        if ask.is_visible():
            page.get_by_role("button", name="Sign out").click()
            expect(page.get_by_role("heading", level=1, name="Sign in to Patch")).to_be_visible(timeout=20000)
            return
        expect(page.locator(".tile").first).to_be_visible()
        menu = page.locator(".user-btn")
        menu.click()
        expect(page.locator(".user-card")).to_contain_text(USER)
        page.keyboard.press("Escape")
        expect(page.locator(".user-card")).to_have_count(0)
        expect(menu).to_be_focused()
        menu.click()
        page.get_by_role("button", name="Sign out").click()
        expect(page.get_by_role("heading", level=1, name="Sign in to Patch")).to_be_visible(timeout=20000)
    finally:
        ctx.close()


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def b10_15_sign_in_screen(fx):
    page, _ = fx("open_signed_out")(reduced=True)
    expect(loading_note(page)).to_be_visible()
    still(page, "the sign-in screen")

"""Browser check for the loading screen (#69): what shows until /health answers. Check ids: B69.n (B69.1 to B69.6
are the unit tests of the wait, frontend/src/healthWait.test.ts).

The test holds /health with its own route: late (a slow start), hung past the 15 s timeout (Playwright's fake clock
jumps the page's time, so no test waits 15 s), or failing outright.
"""
import pathlib
import re

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from test_chat import window
from test_chat_layout import CTRL_K_ON_MOUNT
from test_shell import DESKTOP, PHONE, eventually, no_sideways_scroll, settled
from reduced_motion import scene, still

SHOTS = pathlib.Path(__file__).parent / "screenshots"
TIMEOUT_MS = 15_000  # HEALTH_TIMEOUT_MS in frontend/src/healthWait.ts
FIRST_RETRY_MS = 2_000  # RETRY_DELAYS_MS[0]


class Health:
    """The page's /health requests, held until the test lets them through (or fails them)."""

    def __init__(self, ctx: BrowserContext, api_url: str, fail: bool = False):
        self.held: list[Route] = []
        self.fail = fail
        self.up = False  # answer() lets every request through from then on
        ctx.route(f"{api_url}/health", self._route)

    def _route(self, route: Route) -> None:
        if self.up:
            route.fallback()  # on to slow mode's route, if any, then the backend
        elif self.fail:
            route.abort()
        else:
            self.held.append(route)

    def asked(self, page: Page, n: int) -> None:
        """Wait until the page has asked n times."""
        eventually(page, lambda: len(self.held) >= n)

    def answer(self) -> None:
        """Let every held request, and every later one, through to the real backend."""
        self.up = True
        self.held, held = [], self.held
        for route in held:
            try:
                route.fallback()
            except Exception:  # the page gave up on this one (timed out): nobody waits for it
                pass


@pytest.fixture
def open_loading(browser: Browser, ui_url: str, api_url: str):
    """Opens the app with /health held: returns the page and the held /health."""
    contexts: list[BrowserContext] = []

    def _open(width=DESKTOP, scheme="light", reduced=False, fail=False, init_script=None) -> tuple[Page, Health]:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        health = Health(ctx, api_url, fail=fail)
        page = ctx.new_page()
        if init_script:
            page.add_init_script(init_script)
        page.clock.install()  # the page's timers: fast_forward jumps past the timeout
        page.goto(ui_url)
        return page, health

    yield _open
    for ctx in contexts:
        ctx.close()


def card(page: Page):
    return page.locator(".loading-card")


def status(page: Page, text: str):
    return page.get_by_role("status").filter(has_text=text)


def go_offline(page: Page, health: Health) -> None:
    """The first /health hangs past the timeout: the screen says offline, retrying."""
    expect(status(page, "Waking Patch up…")).to_be_visible()
    health.asked(page, 1)
    page.clock.fast_forward(TIMEOUT_MS)
    expect(status(page, "Backend offline — retrying")).to_be_visible()


# --- B69.7: a late /health shows the loading screen, then the app ---------------------------------------------------

def test_b69_7_a_late_health_shows_the_loading_screen_then_the_app(open_loading):
    page, health = open_loading()
    expect(status(page, "Waking Patch up…")).to_be_visible()
    expect(card(page).locator("svg.robot")).to_have_attribute("data-mood", "idle")
    brand = card(page).locator(".brand")  # B32.3: the same name as the app
    expect(brand.get_by_text("Patch", exact=True)).to_be_visible()
    expect(brand.get_by_text("LLM-security assistant", exact=True)).to_be_visible()
    expect(page.get_by_role("navigation")).to_have_count(0)  # nothing of the app: sign-in isn't known yet
    expect(page.get_by_role("heading", level=1)).to_have_count(0)
    health.asked(page, 1)
    health.answer()
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()
    expect(card(page)).to_have_count(0)


def test_b69_7_patch_idles_on_the_loading_screen_with_normal_motion(open_loading):
    page, _ = open_loading()
    expect(status(page, "Waking Patch up…")).to_be_visible()
    moving = page.locator(".loading-card svg.robot").evaluate(
        "el => el.getAnimations({ subtree: true }).some(a => a.playState === 'running')")
    assert moving


# --- B69.8: hung past the timeout: offline, retrying; recovers by itself or with Retry ------------------------------

def test_b69_8_a_hung_health_says_offline_and_recovers_by_itself(open_loading):
    page, health = open_loading()
    go_offline(page, health)
    expect(card(page)).to_contain_text(re.compile(r"Next try in 2\s+s\."))  # a no-break space
    expect(page.get_by_role("button", name="Retry")).to_be_visible()
    health.answer()  # the server is up now
    page.clock.fast_forward(FIRST_RETRY_MS)  # the automatic retry
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()
    expect(card(page)).to_have_count(0)


def test_b69_8_retry_by_keyboard_tries_at_once(open_loading):
    page, health = open_loading()
    go_offline(page, health)
    retry = page.get_by_role("button", name="Retry")
    for _ in range(3):  # Retry is the screen's only control: the first Tab stops on it
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.textContent") == "Retry":
            break
    expect(retry).to_be_focused()
    outline = retry.evaluate("el => [getComputedStyle(el).outlineStyle, getComputedStyle(el).outlineWidth]")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2  # visible focus
    page.keyboard.press("Enter")
    health.asked(page, 2)  # at once, not after the 2 s wait
    expect(card(page)).to_contain_text("Trying again…")
    expect(retry).to_be_focused()  # never disabled, so the focus stays
    health.answer()
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()


# --- B69.9: an outright failure is the offline screen too (B46): never the app's shell --------------------------

def test_b69_9_a_failing_health_shows_the_offline_screen_not_the_app(open_loading):
    """Without /health nobody knows whether sign-in is on: showing the app (as before B46) showed its shell to anyone
    (#81)."""
    page, health = open_loading(fail=True)
    expect(status(page, "Backend offline — retrying")).to_be_visible()
    expect(page.get_by_role("navigation")).to_have_count(0)
    expect(page.locator("aside, .topbar")).to_have_count(0)
    health.fail = False
    health.answer()
    page.get_by_role("button", name="Retry").click()
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()


# --- B69.10: light and dark, phone and desktop, with screenshots ----------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b69_10_the_screen_fits_follows_the_theme_and_puts_patch_over_the_edge(open_loading, browser_name, scheme,
                                                                               width):
    SHOTS.mkdir(exist_ok=True)
    page, health = open_loading(width=width, scheme=scheme, reduced=True)  # reduced: no frame caught mid-move
    expect(page.locator("html")).to_have_attribute("data-theme", scheme)
    expect(status(page, "Waking Patch up…")).to_be_visible()
    surface = "rgb(255, 255, 255)" if scheme == "light" else "rgb(26, 26, 46)"  # --surface (DESIGN.md §3.1)
    expect(card(page)).to_have_css("background-color", surface)
    for state in ("loading", "offline"):
        if state == "offline":
            go_offline(page, health)
        settled(card(page))
        robot = card(page).locator("svg.robot").bounding_box()
        box = card(page).bounding_box()
        assert robot["y"] < box["y"] < robot["y"] + robot["height"], state  # his head over the top edge
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, state
        assert no_sideways_scroll(page), state
        page.screenshot(path=SHOTS / f"b69-{browser_name}-{width}-{scheme}-{state}.png")


# --- B69.11: the app's first paint after a late /health loses no key ------------------------------------------------

def test_b69_11_ctrl_k_works_the_moment_the_shell_appears_after_a_late_health(open_loading):
    page, health = open_loading(init_script=CTRL_K_ON_MOUNT)
    expect(status(page, "Waking Patch up…")).to_be_visible()
    health.asked(page, 1)
    health.answer()
    expect(window(page)).to_be_visible()


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def b69_12_loading_screen(fx):
    page, health = fx("open_loading")(reduced=True)
    expect(status(page, "Waking Patch up…")).to_be_visible()
    still(page, "the loading screen")
    go_offline(page, health)
    still(page, "the offline screen")

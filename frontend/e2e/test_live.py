"""Browser check for live mode and Check now, on the fake feeds. Check ids: B02.n (#35).

Runs against the live pair run.sh starts (live mode, the fake feeds on day 2, its own state and index), never the
snapshot pair the other checks share: a refresh changes the CVE data. Every test starts and ends with the live data
back at the snapshot and an empty run log (the fake feeds' reset route), so each browser's run can Check now again.
Expected looks: docs/design/DESIGN.md §5.10.
"""
import pathlib

import pytest
from playwright.sync_api import Browser, Error, Locator, Page, Route, expect

from test_dashboard import api
from test_shell import contrast, eventually, no_sideways_scroll
from reduced_motion import scene, still

SHOTS = pathlib.Path(__file__).parent / "screenshots"
PHONE, DESKTOP = 400, 1400
# Day 2 of the fake feeds on top of the snapshot: two new CVEs, an old Langflow CVE added to KEV
NEW = ["CVE-2026-99101", "CVE-2026-99102"]
DONE = "Done: 2 new CVEs, 1 updated, 1 added to KEV."


@pytest.fixture
def live_reset(live_api_url: str):
    def reset():
        api(live_api_url, "/refresh/reset", "POST", {"confirm": "reset"})

    reset()
    yield
    reset()


@pytest.fixture
def open_live(browser: Browser, live_ui_url: str, live_reset):
    """The live pair's dashboard in a fresh context, once its freshness card is there."""
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False, path="/") -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(live_ui_url + path)
        if path == "/":
            expect(card(page)).to_be_visible()
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def card(page: Page) -> Locator:
    return page.get_by_role("region", name="Data freshness")


def button(page: Page) -> Locator:
    return card(page).get_by_role("button", name="Check now")


def line(page: Page) -> Locator:
    return card(page).get_by_role("status")


def hold_refresh(page: Page) -> list[Route]:
    """Hold the Check now request until the test lets it go, so the running state can be seen."""
    held: list[Route] = []
    page.route("**/refresh", lambda route: held.append(route))
    return held


def release(page: Page, held: list[Route]) -> None:
    eventually(page, lambda: bool(held))
    held.pop().continue_()
    page.unroute("**/refresh")


def check_now_running(page: Page) -> list[Route]:
    """Click Check now with the request held: the button says Checking… with the spinner."""
    held = hold_refresh(page)
    button(page).click()
    running = card(page).get_by_role("button", name="Checking…")
    expect(running).to_be_disabled()
    expect(running).to_have_attribute("aria-busy", "true")
    expect(running.locator(".spinner")).to_be_visible()
    return held


def test_b02_9_check_now_shows_the_spinner_then_the_result_and_the_new_cves(open_live):
    page = open_live()
    expect(card(page).locator(".status-chip")).to_have_text("Live")
    expect(card(page)).to_contain_text("Not checked yet")
    expect(page.locator(".side-card strong")).to_have_text("Live data")
    expect(card(page)).to_contain_text("This product uses the NVD API")  # the sources stay credited in live mode

    held = check_now_running(page)
    release(page, held)
    expect(line(page)).to_have_text(DONE)
    expect(button(page)).to_be_enabled()
    expect(card(page)).to_contain_text("Last checked")  # the dashboard loaded again with the new time

    button(page).click()  # within 5 minutes: refused, with the time
    expect(line(page)).to_contain_text("Checked less than 5 minutes ago. The next check is allowed at")

    page.goto(page.url.rstrip("/") + "/cves?status=all&since=2026-10-14")  # the CVEs page, published from day 1
    for cve in NEW:
        expect(page.locator("table, .cves-card").get_by_text(cve, exact=True).first).to_be_visible()


def test_b02_11_done_shows_once_the_dashboard_shows_the_new_data(open_live):
    """After a check that ran, the dashboard and the alerts load again. "Done" and the enabled button wait for both,
    so nothing above Check now moves after Done: a quick second click lands on the button, not where it was (#67)."""
    page = open_live()
    expect(page.locator(".alerts-card")).to_contain_text("No alerts yet")

    def late(route: Route) -> None:  # the loads after the check answer late, as on a slow runner
        try:
            page.wait_for_timeout(1500)  # allowed: the delay is the condition under test
            route.fallback()
        except Error:  # the test ended while the response was held
            pass
    for path in ("**/dashboard*", "**/alerts"):
        page.route(path, late)

    button(page).click()
    expect(line(page)).to_have_text(DONE)
    above = card(page).locator(".checked-line"), page.locator(".alerts-card")
    assert above[0].inner_text().startswith("Last checked"), above[0].inner_text()  # read the moment Done shows
    assert "No alerts yet" not in above[1].inner_text()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b02_10_the_panel_in_both_themes_on_a_phone_and_by_keyboard(open_live, scheme, width):
    page = open_live(width=width, scheme=scheme)
    card(page).scroll_into_view_if_needed()
    button(page).focus()
    page.keyboard.press("Enter")  # keyboard: Enter on the focused button runs the check
    expect(line(page)).to_have_text(DONE)
    colours = line(page).evaluate("el => { const s = getComputedStyle(el); return [s.color, s.backgroundColor] }")
    assert contrast(*colours) >= 4.5, colours
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    card(page).screenshot(path=SHOTS / f"b02-freshness-{scheme}-{width}.png")


def test_b02_10_snapshot_mode_has_no_check_now(browser: Browser, ui_url: str):
    ctx = browser.new_context(viewport={"width": DESKTOP, "height": 900})
    page = ctx.new_page()
    page.goto(ui_url)
    fresh = card(page)
    expect(fresh.locator(".status-chip")).to_have_text("Snapshot")
    expect(fresh).to_contain_text("A frozen snapshot, as of")
    expect(fresh.get_by_role("button")).to_have_count(0)
    ctx.close()


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def b02_9_check_now(fx):
    page = fx("open_live")(reduced=True)
    held = check_now_running(page)  # the spinner is on screen, and must stand still
    still(page, "Check now running")
    release(page, held)
    expect(line(page)).to_have_text(DONE)
    still(page, "the result line")

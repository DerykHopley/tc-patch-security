"""Browser check for Check now on Settings' "Refresh runs" card (B59, #103). Check ids: B59.n.

Where you read the run history is where you start a run. The card's Check now is the dashboard's (CheckNow.tsx): the
same "Checking…" with the spinner, the same line in an <output>, and then the run list loads again with the new run
(or the refusal's skipped row) on top. On the live pair (fake feeds), reset before and after; snapshot mode on the
snapshot pair. Expected looks: docs/design/DESIGN.md §5.10 and §5.12.
"""
import re

import pytest
from playwright.sync_api import Locator, Page, expect

from test_live import DONE_LINE, SHOTS, hold_refresh, live_reset, open_live, release  # noqa: F401 (fixtures)
from test_partial import text_contrast
from test_pause_history import as_another_user, live_state, open_settings, runs_card  # noqa: F401 (fixture)
from test_settings import panel, settings_page  # noqa: F401 (fixture)
from test_shell import DESKTOP, no_sideways_scroll, settled
from reduced_motion import scene, still

PHONE, WIDE = 390, 1440  # the issue's widths (#103)


def check_button(page: Page) -> Locator:
    return runs_card(page).get_by_role("button", name="Check now")


def check_line(page: Page) -> Locator:
    return runs_card(page).get_by_role("status")


def rows(page: Page) -> Locator:
    return runs_card(page).locator(".run-list > li")


def running(page: Page) -> Locator:
    """Check now pressed with the request held: "Checking…" with the spinner, disabled and aria-busy."""
    busy = runs_card(page).get_by_role("button", name="Checking…")
    expect(busy).to_be_disabled()
    expect(busy).to_have_attribute("aria-busy", "true")
    expect(busy.locator(".spinner")).to_be_visible()
    return busy


# --- B59.2: press it on Settings: Checking…, the line, the new run on top -------------------------------------------

def test_b59_2_check_now_on_refresh_runs_runs_and_the_new_run_shows_on_top(open_live, live_state):  # noqa: F811
    page = open_settings(open_live)
    expect(runs_card(page)).to_contain_text("No runs yet. Check now, the schedule or Patch starts one.")
    expect(runs_card(page)).not_to_contain_text("on the dashboard")
    # Above the list, so it's found without scrolling the 20 runs
    button_box = check_button(page).bounding_box()
    heading_box = runs_card(page).get_by_role("heading", name="Last 20 runs").bounding_box()
    assert button_box and heading_box and button_box["y"] < heading_box["y"]

    held = hold_refresh(page)
    check_button(page).click()
    running(page)
    release(page, held)
    expect(check_line(page)).to_have_text(DONE_LINE)
    expect(check_button(page)).to_be_enabled()
    expect(rows(page)).to_have_count(1)  # loaded again: no reload
    expect(rows(page).nth(0).locator(".run-result")).to_have_text("OK")
    expect(rows(page).nth(0).locator("summary strong")).to_have_text("Check now")

    check_button(page).click()  # within 5 minutes: the dashboard's refusal line, and a skipped row on top
    expect(check_line(page)).to_have_text(re.compile(
        r"^Checked less than 5 minutes ago\. The next check is allowed at \d\d:\d\d UTC\.$"))
    expect(rows(page)).to_have_count(2)
    expect(rows(page).nth(0).locator(".run-result")).to_have_text("Skipped: too soon")


# --- B59.3: hidden in snapshot mode and for anyone but the owner ----------------------------------------------------

def test_b59_3_no_check_now_on_settings_in_snapshot_mode(settings_page):  # noqa: F811
    page = settings_page()
    expect(runs_card(page)).to_contain_text("The snapshot never changes, so nothing runs.")
    expect(runs_card(page).get_by_role("button", name="Check now")).to_have_count(0)
    expect(runs_card(page).locator(".check-line")).to_have_count(0)  # nothing to say: the snapshot never runs
    # The Data card names both places
    pointer = panel(page, "Data").get_by_test_id("check-now-pointer")
    expect(pointer).to_contain_text("Check now under Refresh runs or on the dashboard's Data freshness card")


def test_b59_3_no_check_now_on_settings_for_anyone_but_the_owner(browser, live_ui_url, live_state):  # noqa: F811
    ctx = browser.new_context(viewport={"width": DESKTOP, "height": 900})
    try:
        as_another_user(ctx, live_state)
        page = ctx.new_page()
        page.goto(live_ui_url + "/settings")
        expect(panel(page, "Alerts").get_by_test_id("owners-schedule")).to_be_visible()
        expect(page.get_by_role("button", name="Check now")).to_have_count(0)
        page.get_by_role("button", name="Dashboard", exact=True).click()
        expect(page.get_by_role("region", name="Data freshness").get_by_role("button", name="Check now")).to_be_visible()
    finally:
        ctx.close()


# --- B59.4: both themes, phone and desktop, by keyboard ------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [WIDE, PHONE])
def test_b59_4_check_now_on_settings_in_both_themes_on_a_phone_and_by_keyboard(
        open_live, live_state, scheme, width):  # noqa: F811
    page = open_settings(open_live, width=width, scheme=scheme)
    check_button(page).focus()
    page.keyboard.press("Enter")
    expect(check_line(page)).to_have_text(DONE_LINE)
    expect(rows(page)).to_have_count(1)
    assert text_contrast(check_line(page)) >= 4.5
    edge = check_line(page).evaluate("el => getComputedStyle(el).borderLeftWidth")
    assert edge == "3px", edge
    assert text_contrast(check_button(page)) >= 4.5
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    settled(runs_card(page))
    runs_card(page).screenshot(path=SHOTS / f"b59-check-now-settings-{scheme}-{width}.png")


# --- Reduced motion: the spinner stands still, the word says the state ----------------------------------------------

@scene
def b59_5_check_now_on_settings(fx):
    fx("live_state")
    page = open_settings(fx("open_live"), reduced=True)
    held = hold_refresh(page)
    check_button(page).click()
    running(page)
    still(page, "Checking… on Settings, the spinner")
    release(page, held)
    expect(check_line(page)).to_have_text(DONE_LINE)
    still(page, "the line and the new run")

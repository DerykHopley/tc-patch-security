"""Browser check for pausing the schedule and the refresh run history (B19, #59). Check ids: B19.n.

On the live pair (fake feeds): Settings' "Refresh runs" card (the schedule, Pause, the last 20 runs, each opening to
its details) and the dashboard's "Schedule paused" with Resume. Each test resets the live data and the live pair's
state before and after. Expected looks: docs/design/DESIGN.md §5.10 and §5.12.
"""
import re

import pytest
from playwright.sync_api import Locator, Page, expect

from test_dashboard import api
from test_live import SHOTS, button, card, line, live_reset, open_live  # noqa: F401 (fixtures)
from test_partial import text_contrast
from test_settings import panel
from test_shell import DESKTOP, PHONE, no_sideways_scroll, settled


@pytest.fixture
def live_state(live_api_url: str, live_reset):  # noqa: F811
    """The live pair's settings back to the defaults (the schedule not paused), before and after."""
    api(live_api_url, "/state/reset", "POST", {"confirm": "reset"})
    yield live_api_url
    api(live_api_url, "/state/reset", "POST", {"confirm": "reset"})


def runs_card(page: Page) -> Locator:
    return panel(page, "Refresh runs")


def open_settings(open_live, **kw) -> Page:  # noqa: F811
    page = open_live(path="/settings", **kw)
    expect(runs_card(page)).to_be_visible()
    return page


def pause(page: Page) -> None:
    runs_card(page).get_by_label("Pause the schedule").check()
    page.get_by_role("button", name="Save changes").click()
    expect(runs_card(page).get_by_test_id("schedule-line")).to_have_text(
        "Schedule paused: no scheduled check starts. Check now and Patch still check.")


def two_checks(page: Page) -> None:
    """Check now, then again at once: one run and one refused (too soon)."""
    button(page).click()
    expect(line(page)).to_contain_text("Done:")
    button(page).click()
    expect(line(page)).to_contain_text("Checked less than 5 minutes ago")


# --- B19.6: pause and resume, on Settings and the dashboard ---------------------------------------------------------

def test_b19_6_pause_on_settings_shows_on_the_dashboard_and_resume_there(open_live, live_state):  # noqa: F811
    page = open_settings(open_live)
    expect(runs_card(page).get_by_test_id("schedule-line")).to_have_text(
        "Every 6 hours · the next scheduled check runs at the next tick.")
    pause(page)

    page.get_by_role("button", name="Dashboard", exact=True).click()
    paused = card(page).locator(".schedule-paused")
    expect(paused).to_contain_text("Schedule paused")
    two_checks(page)  # paused, Check now still runs
    paused.get_by_role("button", name="Resume the schedule").click()
    expect(line(page)).to_have_text("Schedule resumed: a check every 6 hours.")
    expect(paused).to_have_count(0)
    page.reload()
    expect(card(page)).to_be_visible()
    expect(card(page).locator(".schedule-paused")).to_have_count(0)  # saved, not just hidden

    card(page).get_by_role("link", name=re.compile("Schedule and refresh runs")).click()
    expect(runs_card(page).get_by_test_id("schedule-line")).to_contain_text("Every 6 hours · next scheduled check from")


# --- B19.7: the run history: the last runs, newest first, each opening to its details ------------------------------

def test_b19_7_the_history_lists_the_runs_and_a_run_opens_to_each_feed(open_live, live_state):  # noqa: F811
    page = open_live()
    two_checks(page)
    page = open_settings(open_live)
    rows = runs_card(page).locator(".run-list > li")
    expect(rows).to_have_count(2)
    skipped, ok = rows.nth(0), rows.nth(1)
    expect(skipped.locator(".run-result")).to_have_text("Skipped: too soon")
    expect(skipped.locator("summary strong")).to_have_text("Check now")
    expect(skipped.locator(".run-counts")).to_have_text(re.compile(r"^Next allowed \d\d:\d\d UTC$"))
    expect(ok.locator(".run-result")).to_have_text("OK")
    expect(ok.locator(".run-counts")).to_contain_text("2 new · 1 updated · 1 added to KEV")
    expect(ok.locator(".run-details")).not_to_be_visible()

    ok.locator("summary").click()
    details = ok.locator(".run-details")
    expect(details.get_by_role("list", name="Sources")).to_have_text(re.compile(
        "NVD: answered.*CISA KEV: answered.*OSV: answered.*EPSS: answered", re.S))
    expect(details.get_by_role("link", name="CVE-2026-99102")).to_have_attribute("href", "#cve=CVE-2026-99102")


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b19_8_the_card_and_the_paused_state_in_both_themes_on_a_phone_and_by_keyboard(
        open_live, live_state, scheme, width):  # noqa: F811
    page = open_live(width=width, scheme=scheme)
    two_checks(page)
    page = open_settings(open_live, width=width, scheme=scheme)
    pause(page)
    schedule_line = runs_card(page).get_by_test_id("schedule-line")
    assert text_contrast(schedule_line) >= 4.5
    edge = schedule_line.evaluate("el => getComputedStyle(el).borderLeftWidth")
    assert edge == "3px", edge
    for chip in runs_card(page).locator(".run-result").all():  # a skip's chip has no fill: the card's is behind it
        muted = "muted" in (chip.get_attribute("class") or "")
        assert text_contrast(chip, ".card" if muted else None) >= 4.5
    first = runs_card(page).locator(".run-list > li").nth(1)
    first.locator("summary").focus()
    page.keyboard.press("Enter")  # a run opens by keyboard
    expect(first.locator(".run-details")).to_be_visible()
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    settled(runs_card(page))
    runs_card(page).screenshot(path=SHOTS / f"b19-runs-{scheme}-{width}.png")

    page = open_live(width=width, scheme=scheme)
    paused = card(page).locator(".schedule-paused")
    expect(paused).to_be_visible()
    settled(card(page))  # the dashboard cards fade in (§7.1)
    card(page).screenshot(path=SHOTS / f"b19-paused-{scheme}-{width}.png")
    assert text_contrast(paused.locator("p"), ".schedule-paused") >= 4.5
    paused.get_by_role("button", name="Resume the schedule").focus()
    page.keyboard.press("Enter")
    expect(line(page)).to_have_text("Schedule resumed: a check every 6 hours.")
    assert no_sideways_scroll(page)
    card(page).screenshot(path=SHOTS / f"b19-resumed-{scheme}-{width}.png")

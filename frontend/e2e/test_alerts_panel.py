"""Browser check for the dashboard's alerts panel (B04, #37). Check ids: B04.n.

Runs against the live pair run.sh starts (live mode, the fake feeds on day 2, NOTIFY_DRY_RUN: alerts are recorded,
never sent). Each test starts and ends with the live data at the snapshot, no alerts (the fake feeds' reset) and the
live pair's state reset. The live pair's clock is the real one, so the overdue alerts' number moves with the date:
the checks never count them. Expected looks: docs/design/DESIGN.md §5.11.
"""
import pathlib
import re

import pytest
from playwright.sync_api import Page, expect

from test_dashboard import api
from test_live import DESKTOP, PHONE, button, line, live_reset, open_live  # noqa: F401  (fixtures)
from test_shell import contrast, no_sideways_scroll

SHOTS = pathlib.Path(__file__).parent / "screenshots"
NEW_OLLAMA = "CVE-2026-99102"  # the fake feeds' day-2 Ollama CVE


@pytest.fixture
def live_state(live_api_url: str):
    def reset():
        api(live_api_url, "/state/reset", "POST", {"confirm": "reset"})

    reset()
    yield live_api_url
    reset()


def panel(page: Page):
    return page.get_by_role("region", name="Recent alerts")


def entries(page: Page):
    return panel(page).get_by_role("list", name="Recent alerts").get_by_role("listitem")


def check_now(page: Page) -> None:
    button(page).click()
    expect(line(page)).to_contain_text("Done:")


def test_b04_12_the_panel_shows_a_busy_check_as_one_digest(live_state, open_live):  # noqa: F811
    page = open_live()
    expect(panel(page)).to_contain_text("No alerts yet.")
    check_now(page)
    # the snapshot's overdue and due-soon CVEs plus the new ones: more than 5, so one digest
    expect(entries(page)).to_have_count(1)
    first = entries(page).first
    expect(first).to_contain_text("alerts for your watchlist")
    expect(first).to_contain_text("Digest · ")
    expect(first).to_contain_text(" UTC")
    expect(first.locator(".channel-results .result")).to_contain_text("desktop: ")  # its result, in words


def test_b04_12_one_alert_links_to_its_cve_like_the_notification(live_state, open_live):  # noqa: F811
    api(live_state, "/watchlist", "PUT", {"products": ["ollama"]})
    body = api(live_state, "/settings")["settings"]
    body["alerts"]["digest_over"] = 50
    api(live_state, "/settings", "PUT", body)
    page = open_live()
    check_now(page)
    first = entries(page).first
    link = first.get_by_role("link", name="New CVE: Ollama")
    expect(link).to_be_visible()
    expect(first).to_contain_text("New CVE · ")
    link.click()
    expect(page.get_by_role("heading", level=1)).to_have_text(NEW_OLLAMA)  # the CVE's own page (B35)
    assert page.evaluate("location.pathname") == f"/cves/{NEW_OLLAMA}"


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b04_12_the_panel_in_both_themes_on_a_phone_and_by_keyboard(live_state, open_live, scheme, width):  # noqa: F811
    page = open_live(width=width, scheme=scheme)
    button(page).focus()
    page.keyboard.press("Enter")
    expect(line(page)).to_contain_text("Done:")
    result = entries(page).first.locator(".channel-results .result").first
    expect(result).to_be_visible()
    colours = result.evaluate("el => { const s = getComputedStyle(el); return [s.color, s.backgroundColor] }")
    if colours[1] in ("rgba(0, 0, 0, 0)", "transparent"):  # a muted result has no fill: the card's shows through
        colours[1] = panel(page).evaluate("el => getComputedStyle(el).backgroundColor")
    assert contrast(*colours) >= 4.5, colours
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    panel(page).screenshot(path=SHOTS / f"b04-alerts-{scheme}-{width}.png")
    settings = panel(page).get_by_role("link", name="Alert settings")
    settings.focus()
    page.keyboard.press("Enter")  # keyboard: the link opens Settings, where the same log is listed
    expect(page).to_have_url(re.compile(r"/settings$"))
    expect(page.get_by_role("list", name="Recent alerts").get_by_role("listitem").first).to_contain_text("Digest · ")

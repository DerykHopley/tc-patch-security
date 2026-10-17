"""Browser check for the "Show Patch's welcome" switch on Settings (DESIGN.md §5.7, §5.8, §11). Check ids: W.n.

The welcome banner, once closed, stayed hidden for good in that browser; this switch brings it back. A per-browser
convenience (localStorage `helloHidden`), not a server setting: it applies at once, outside the save bar.
Runs in Firefox and Chromium against run.sh's throwaway servers.
"""
import pytest
from playwright.sync_api import Page, expect

from test_dashboard import DESKTOP, PHONE, clean_state, open_dash  # noqa: F401 (fixtures)
from test_dashboard_charts import banner

LABEL = "Show Patch's welcome on the dashboard"
BLOCKED = "Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked') } })"


def to_settings(page: Page):
    page.get_by_role("button", name="Settings", exact=True).click()
    switch = page.get_by_role("checkbox", name=LABEL)
    expect(switch).to_be_visible()
    return switch


def to_dashboard(page: Page) -> None:
    page.get_by_role("button", name="Dashboard", exact=True).click()
    expect(page.locator(".tile")).to_have_count(4)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_w_1_switch_sits_in_patchs_card_on_and_says_it_is_per_browser(open_dash, width, scheme):
    page = open_dash(width=width, scheme=scheme, reduced=True)
    switch = to_settings(page)
    expect(switch).to_be_checked()  # the banner shows by default
    card = page.get_by_role("region", name="Patch's answers")
    expect(card.get_by_role("checkbox", name=LABEL)).to_have_count(1)
    expect(switch).to_have_accessible_description("Remembered in this browser, not saved to the server. Applies at once.")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    expect(page.get_by_text("All changes saved")).to_be_visible()


def test_w_2_off_hides_and_on_brings_back_the_banner_without_a_reload(open_dash):
    page = open_dash(reduced=True)
    switch = to_settings(page)
    switch.uncheck()
    expect(page.get_by_text("All changes saved")).to_be_visible()  # outside the save bar: nothing to save
    assert page.evaluate("localStorage.getItem('helloHidden')") == "1"
    to_dashboard(page)
    expect(banner(page)).to_have_count(0)
    to_settings(page).check()
    to_dashboard(page)
    expect(banner(page)).to_be_visible()
    page.reload()  # and it stays on
    expect(page.locator(".tile")).to_have_count(4)
    expect(banner(page)).to_be_visible()


def test_w_3_closing_the_banner_turns_the_switch_off(open_dash):
    page = open_dash(reduced=True)
    banner(page).get_by_role("button", name="Close Patch's welcome").click()
    expect(banner(page)).to_have_count(0)
    expect(to_settings(page)).not_to_be_checked()


def test_w_4_switch_works_for_the_session_when_storage_is_blocked(open_dash):
    page = open_dash(reduced=True, before=lambda p: p.add_init_script(BLOCKED))
    banner(page).get_by_role("button", name="Close Patch's welcome").click()
    switch = to_settings(page)
    expect(switch).not_to_be_checked()  # the close is kept for the session
    to_dashboard(page)
    expect(banner(page)).to_have_count(0)
    to_settings(page).check()
    to_dashboard(page)
    expect(banner(page)).to_be_visible()


def test_w_5_keyboard_space_toggles_the_switch(open_dash):
    page = open_dash(reduced=True)
    switch = to_settings(page)
    switch.focus()
    page.keyboard.press("Space")
    expect(switch).not_to_be_checked()
    page.keyboard.press("Space")
    expect(switch).to_be_checked()

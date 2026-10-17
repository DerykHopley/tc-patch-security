"""Browser check for check_updates (B06, #39): asking Patch what's new runs the refresh and shows its card.
Check ids: B06.n.

The live checks run on the live pair (run.sh: live mode, the fake feeds on day 2), reset before and after each test
like test_live.py's, so each browser's run can check again. The snapshot pair shows the frozen-data card.
Expected looks: docs/design/DESIGN.md §6.2 (check_updates).
"""
import re

import pytest
from playwright.sync_api import Locator, Page, expect

from test_chat import ask, open_chat, window
from test_dashboard import DESKTOP, PHONE, clean_state, open_dash  # noqa: F401 (fixtures)
from test_live import card as freshness, live_reset, open_live  # noqa: F401 (fixtures)
from test_shell import contrast, no_sideways_scroll

ASK = "Anything new since Monday?"
NEW = ["CVE-2026-99101", "CVE-2026-99102"]  # the fake feeds' day 2 on top of the snapshot


def updates_card(answer: Locator) -> Locator:
    answer.get_by_role("button", name="Show", exact=False).click()
    answer.get_by_role("tab", name="Tool calls", exact=False).click()
    return answer.locator(".updates-card")


def ask_whats_new(page: Page) -> Locator:
    open_chat(page)
    return ask(page, ASK)


# --- B06.5: the card: when, counts, the new CVEs and alerts, the link; the dashboard follows -----------------------

def test_b06_5_asking_runs_the_check_shows_the_card_and_the_dashboard_follows(open_live):
    page = open_live()
    expect(freshness(page)).to_contain_text("Not checked yet")
    answer = ask_whats_new(page)
    expect(answer.locator(".answer-text")).to_contain_text("I checked the feeds just now")
    for cve in NEW:
        expect(answer.locator(".answer-text")).to_contain_text(cve)
    expect(freshness(page)).to_contain_text("Last checked")  # the dashboard loaded again, as after Check now

    card = updates_card(answer)
    expect(card.locator(".result-title")).to_contain_text("Checked the feeds · ")
    expect(card).to_contain_text("2 new · 1 updated · 1 added to KEV · 0 rescored")
    new_list = card.locator(".updates-list").first
    expect(new_list.locator("li")).to_have_count(2)
    for cve in NEW:
        expect(new_list).to_contain_text(cve)
    expect(new_list.locator(".source-n").first).to_be_visible()  # each listed CVE is a numbered source
    expect(card.locator(".updates-head", has_text="Alerts for you")).to_be_visible()
    expect(card).to_contain_text("Added to CISA KEV")

    link = card.get_by_role("link", name="See the new CVEs on the CVEs page")
    expect(link).to_have_attribute("href", "/cves?new=1")

    again = ask(page, ASK)  # within 5 minutes: refused, from the last check
    expect(again.locator(".answer-text")).to_contain_text("Checked less than 5 minutes ago")
    expect(updates_card(again).locator(".result-title")).to_contain_text("Last check · ")

    link.click()
    expect(page).to_have_url(re.compile(r"/cves\?new=1$"))


def test_b06_5_in_snapshot_mode_the_card_says_the_data_is_frozen(open_dash):
    page = open_dash()
    card = updates_card(ask_whats_new(page))
    expect(card.locator(".result-title")).to_have_text("A frozen snapshot, as of 2026-10-13: nothing to check")
    expect(card.locator(".updates-list")).to_have_count(0)


# --- B06.6: light and dark, phone, keyboard ---------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b06_6_the_card_in_light_and_dark_on_desktop_and_phone(open_live, scheme, width):
    page = open_live(width=width, scheme=scheme)
    card = updates_card(ask_whats_new(page))
    expect(card.locator(".updates-list li").first).to_be_visible()
    for el in (card.locator(".updates-list .chip").last, card.locator(".source-n").first):  # each has its own fill
        fg, bg = el.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
        assert contrast(fg, bg) >= 4.5, (scheme, fg, bg)
    assert no_sideways_scroll(page)
    box, win = card.bounding_box(), window(page).bounding_box()
    assert box and win and box["x"] + box["width"] <= win["x"] + win["width"] + 1  # never wider than the chat


def test_b06_6_the_cves_link_is_reachable_by_keyboard(open_live):
    page = open_live()
    card = updates_card(ask_whats_new(page))
    link = card.get_by_role("link", name="See the new CVEs on the CVEs page")
    link.focus()
    expect(link).to_be_focused()
    page.keyboard.press("Enter")
    expect(page).to_have_url(re.compile(r"/cves\?new=1$"))

"""Browser check for web research (B08, #33): research_web's tool card and the web source cards. Check ids: B08.n.

run.sh turns web research on against a fake Tavily (backend/tests/fake_tavily.py): four canned pages, one with an
injection attempt and one on an excluded exploit site. FakeLLM sends a web question to research_web. Expected looks
from docs/design/DESIGN.md §6.2 (web research), §9 and §10.
"""
import pytest
from playwright.sync_api import Locator, Page, expect

from test_chat import ask, open_chat, window
from test_dashboard import DESKTOP, PHONE, clean_state, open_dash  # noqa: F401 (fixtures)
from test_shell import contrast, no_sideways_scroll
from reduced_motion import scene, still
from test_shell import open_app  # noqa: F401 (fixture)

ASK = "Who's talking about CVE-2025-3248 on the web?"
SITES = ["github.com", "news.example.com", "blog.example.net"]  # exploit-db.com is dropped


def details(answer: Locator, tab: str) -> Locator:
    answer.get_by_role("button", name="Show", exact=False).click()
    answer.get_by_role("tab", name=tab, exact=False).click()
    return answer


def web_answer(page: Page) -> Locator:
    open_chat(page)
    return ask(page, ASK)


def colours(loc: Locator) -> tuple[str, str]:
    return loc.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")


# --- B08.10: the research_web card: query, results, time ----------------------------------------------------------

def test_b08_10_the_tool_card_shows_query_results_and_time(open_dash):
    page = open_dash()
    answer = details(web_answer(page), "Tool calls")
    card = answer.locator(".tool-card", has=page.locator("code", has_text="research_web"))
    expect(card.locator("header .meta")).to_contain_text(" ms")  # the time
    research = card.locator(".research-card")
    expect(research.locator(".result-title")).to_have_text(f"Web search: “{ASK}”")
    expect(research).to_contain_text("3 results · via Tavily's MCP server · 1 flagged")
    items = research.locator(".web-list > li")
    expect(items).to_have_count(3)
    for i, site in enumerate(SITES):
        expect(items.nth(i).locator(".web-facts .meta")).to_contain_text(site)
        expect(items.nth(i).locator(".chip.web-unverified")).to_have_text("Web result, unverified")
    expect(research.locator(".chip.web-flagged")).to_have_count(1)
    expect(items.nth(2).locator(".chip.web-flagged")).to_have_text("Flagged: instructions ignored")
    expect(research).not_to_contain_text("exploit-db")


# --- B08.11: web sources say "web result, unverified"; the flagged page is kept and marked -----------------------

def test_b08_11_web_sources_are_marked_unverified_and_the_injection_flagged(open_dash):
    page = open_dash()
    answer = web_answer(page)
    expect(answer.locator(".flag-note")).to_have_text(
        "A web result tries to give instructions. It's shown as data, and Patch ignored it.")
    expect(answer.locator(".answer-text")).to_contain_text("unverified")
    details(answer, "Sources")
    sources = answer.locator(".source")
    expect(sources).to_have_count(3)
    for i, site in enumerate(SITES):
        expect(sources.nth(i).locator(".chip.web-unverified")).to_have_text("Web result, unverified")
        expect(sources.nth(i).locator(".web-facts .meta")).to_contain_text(site)
    expect(sources.nth(0).locator(".source-head a")).to_have_attribute(
        "href", "https://github.com/advisories/GHSA-rvqx-wpfh-mfx7")
    expect(sources.nth(2).locator(".chip.web-flagged")).to_be_visible()
    expect(sources.nth(2).locator(".snippet")).to_contain_text("Ignore all previous instructions")  # kept as data


def test_b08_11_a_citation_opens_its_web_source(open_dash):
    page = open_dash()
    answer = web_answer(page)
    answer.locator(".answer-text a.cite").first.click()
    expect(answer.get_by_role("tab", name="Sources", exact=False)).to_have_attribute("aria-selected", "true")
    expect(answer.locator(".source").first).to_be_in_viewport()


# --- B08.12: light and dark, phone, keyboard ---------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b08_12_the_cards_in_light_and_dark_on_desktop_and_phone(open_dash, scheme, width):
    page = open_dash(width=width, scheme=scheme)
    answer = details(web_answer(page), "Tool calls")
    research = answer.locator(".research-card")
    expect(research).to_be_visible()
    for chip in (research.locator(".chip.web-unverified").first, research.locator(".chip.web-flagged")):
        fg, bg = colours(chip)
        assert contrast(fg, bg) >= 4.5, (scheme, fg, bg)
    assert no_sideways_scroll(page)
    box = research.bounding_box()
    win = window(page).bounding_box()
    assert box and win and box["x"] + box["width"] <= win["x"] + win["width"] + 1  # never wider than the chat
    answer.get_by_role("tab", name="Sources", exact=False).click()
    expect(answer.locator(".source .chip.web-unverified")).to_have_count(3)
    assert no_sideways_scroll(page)


def test_b08_12_web_links_are_reachable_by_keyboard(open_dash):
    page = open_dash()
    answer = details(web_answer(page), "Tool calls")
    link = answer.locator(".research-card .web-list a").first
    expect(link).to_have_attribute("href", "https://github.com/advisories/GHSA-rvqx-wpfh-mfx7")
    tab = answer.get_by_role("tab", name="Tool calls", exact=False)
    tab.focus()
    for _ in range(12):
        page.keyboard.press("Tab")
        if link.evaluate("el => el === document.activeElement"):
            break
    expect(link).to_be_focused()


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def b08_13_research_web(fx):
    page = fx("open_app")(reduced=True)
    open_chat(page)
    answer = ask(page, ASK)
    details(answer, "Tool calls")
    expect(answer.locator(".research-card")).to_be_visible()
    still(page, "the research_web card")
    answer.get_by_role("tab", name="Sources", exact=False).click()
    expect(answer.locator(".source .chip.web-unverified")).to_have_count(3)
    still(page, "the web sources")

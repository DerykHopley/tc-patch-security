"""Browser check for the Patch guide (#148): the suggestion, patch_guide's tool card and its guide source. Check ids:
F148.n.

FakeLLM sends the Settings page's suggestion ("How do I tell Patch which Langflow version I run?") to patch_guide,
topic watchlist_and_versions, and "How do I use Patch?" to topic start. Expected looks from docs/design/DESIGN.md
§6.2 (the Patch guide card, suggestions), §9 and §10.
"""
import pytest
from playwright.sync_api import Locator, Page, expect

from reduced_motion import scene, still
from test_chat import ask, open_chat, window
from test_dashboard import DESKTOP, PHONE
from test_contrast import low_contrast, show
from test_shell import no_sideways_scroll, open_app, settled  # noqa: F401 (fixture)

HOW_TO = "How do I tell Patch which Langflow version I run?"
START = "How do I use Patch?"


def details(answer: Locator, tab: str) -> Locator:
    answer.get_by_role("button", name="Show", exact=False).click()
    answer.get_by_role("tab", name=tab, exact=False).click()
    return answer


def guide_card(answer: Locator) -> Locator:
    return details(answer, "Tool calls").locator(".guide-card")


def on_settings(open_app, **kw) -> Page:
    page = open_app(query="/settings", **kw)
    expect(page.get_by_role("heading", name="Watchlist", exact=True)).to_be_visible()
    return page


# --- F148.11: the suggestions ----------------------------------------------------------------------------------------

def test_f148_11_the_dashboard_suggests_how_to_use_patch_and_it_answers_from_the_guide(open_app):
    page = open_app()
    chat = open_chat(page)
    chat.get_by_role("button", name=START).click()
    answer = window(page).locator(".message.assistant").last
    expect(answer.locator(".answer-text")).to_contain_text("Getting started")
    expect(guide_card(answer).locator(".result-title")).to_have_text("Patch guide: Getting started")


def test_f148_11_settings_suggests_the_how_to_and_the_card_shows_topic_and_link(open_app):
    page = on_settings(open_app)
    chat = open_chat(page)
    chat.get_by_role("button", name=HOW_TO).click()
    answer = window(page).locator(".message.assistant").last
    expect(answer.locator(".answer-text")).to_contain_text("Settings")
    card = guide_card(answer)
    expect(card.locator(".result-title")).to_have_text("Patch guide: Your watchlist and versions")
    expect(card).to_contain_text("Topic: watchlist_and_versions")
    link = card.get_by_role("link", name="Open /settings#watchlist")
    expect(link).to_have_attribute("href", "/settings#watchlist")
    expect(link).not_to_have_attribute("target", "_blank")  # opened in the app


# --- F148.12: the link opens the page in the app, the card in view, the chat still open -----------------------------

def test_f148_12_the_link_opens_the_card_in_the_app_with_the_chat_open(open_app):
    page = open_app()
    open_chat(page)
    card = guide_card(ask(page, HOW_TO))
    card.get_by_role("link", name="Open /settings#watchlist").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Settings")
    assert page.url.endswith("/settings#watchlist")
    expect(page.locator("#watchlist")).to_be_in_viewport()
    expect(window(page)).to_be_visible()


# --- F148.13: the guide section is a source, cited and linked in the app --------------------------------------------

def test_f148_13_the_section_is_a_cited_source_with_an_in_app_link(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, HOW_TO)
    answer.locator(".answer-text a.cite").first.click()
    expect(answer.get_by_role("tab", name="Sources", exact=False)).to_have_attribute("aria-selected", "true")
    source = answer.locator(".source").first
    expect(source.locator(".meta")).to_contain_text("Patch guide")
    link = source.locator(".source-head a")
    expect(link).to_have_text("Patch guide: Your watchlist and versions")
    expect(link).to_have_attribute("href", "/settings#watchlist")
    expect(link).not_to_have_attribute("target", "_blank")


# --- F148.14: light and dark, desktop and phone; keyboard -----------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_f148_14_the_card_in_light_and_dark_on_desktop_and_phone(open_app, scheme, width):
    page = open_app(width=width, scheme=scheme)
    open_chat(page)
    card = guide_card(ask(page, HOW_TO))
    expect(card).to_be_visible()
    settled(window(page))
    found = low_contrast(page, ".guide-card")
    assert not found, f"{width}px, {scheme}:\n{show(found)}"
    assert no_sideways_scroll(page)
    box, win = card.bounding_box(), window(page).bounding_box()
    assert box and win and box["x"] + box["width"] <= win["x"] + win["width"] + 1  # never wider than the chat


def test_f148_14_the_link_is_reachable_by_keyboard(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, HOW_TO)
    link = guide_card(answer).get_by_role("link")
    answer.get_by_role("tab", name="Tool calls", exact=False).focus()
    for _ in range(12):
        page.keyboard.press("Tab")
        if link.evaluate("el => el === document.activeElement"):
            break
    expect(link).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", level=1)).to_have_text("Settings")


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) ---------------------------------------

@scene
def f148_15_patch_guide(fx):
    page = fx("open_app")(reduced=True)
    open_chat(page)
    card = guide_card(ask(page, HOW_TO))
    expect(card).to_be_visible()
    still(page, "the patch_guide card")

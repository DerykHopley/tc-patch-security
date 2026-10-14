"""Browser check (seam 3) for the chat layout: enlarge, pin, keyboard, phone, Ask about this. Check ids: A07.n,
from ticket #9.

Runs in Firefox and Chromium (run.sh). Expected values come from docs/design/DESIGN.md §6.3–§6.5, §7.1, §10 and §11,
not from the CSS.
"""
import pytest
from playwright.sync_api import Locator, Page, expect

from test_chat import box, fab, window
from test_shell import DESKTOP, PHONE, SHOTS, no_sideways_scroll, open_app  # noqa: F401 (fixture)

REM = 15  # px: the base font size (DESIGN.md §3.4)
HEIGHT = 900  # the viewport height open_app uses


def open_chat(page: Page) -> Locator:
    fab(page).click()
    expect(window(page)).to_be_visible()
    page.wait_for_timeout(250)  # the pop (0.16s) scales the window while it runs
    return window(page)


def head_button(page: Page, name: str) -> Locator:
    return window(page).locator(".chat-head").get_by_role("button", name=name, exact=True)


PIN = "Pin: dock the chat beside the page"
UNPIN = "Unpin: float the chat over the page"


# --- A07.1: Make larger, Pin only on the enlarged bubble (DESIGN.md §6.3) ----------------------------------------

def test_a07_1_make_larger_is_640px_wide_full_height_minus_5rem_and_only_then_offers_pin(open_app):
    page = open_app()
    open_chat(page)
    expect(head_button(page, PIN)).to_have_count(0)  # not on the small bubble
    head_button(page, "Make larger").click()
    page.wait_for_timeout(250)
    w = box(window(page))
    assert round(w["width"]) == 640
    assert round(w["height"]) == HEIGHT - 5 * REM
    assert round(DESKTOP - (w["x"] + w["width"])) == round(1.25 * REM)
    expect(head_button(page, PIN)).to_be_visible()
    head_button(page, "Make smaller").click()
    page.wait_for_timeout(250)
    assert box(window(page))["width"] <= 400
    expect(head_button(page, PIN)).to_have_count(0)


def pin(page: Page) -> Locator:
    """Open the chat, enlarge it and pin it; returns the pinned chat."""
    open_chat(page)
    head_button(page, "Make larger").click()
    head_button(page, PIN).click()
    expect(head_button(page, UNPIN)).to_be_visible()
    return window(page)


def divider(page: Page) -> Locator:
    return page.get_by_role("separator", name="Resize the chat")


def test_a07_1_pin_docks_the_chat_beside_the_page_with_a_divider(open_app):
    page = open_app()
    chat = pin(page)
    unpin = head_button(page, UNPIN)
    expect(unpin).to_have_attribute("aria-pressed", "true")
    accent = page.evaluate("(() => { const d = document.createElement('div'); d.style.color = 'var(--accent)'; "
                           "document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c })()")
    assert unpin.evaluate("el => getComputedStyle(el).color") == accent  # pressed state, purple
    expect(fab(page)).to_be_hidden()  # Patch's button hides while pinned
    c, d, main = box(chat), box(divider(page)), box(page.locator(".main-col"))
    assert round(c["width"]) == 440  # default width
    assert round(d["width"]) == 6
    assert main["x"] + main["width"] <= d["x"] + 0.5 and d["x"] + d["width"] <= c["x"] + 0.5  # page | divider | chat
    assert c["x"] + c["width"] <= DESKTOP and no_sideways_scroll(page)
    assert chat.evaluate("el => getComputedStyle(el).borderTopLeftRadius") == "26px"
    assert c["y"] > 0 and c["x"] + c["width"] < DESKTOP  # a card with a margin
    expect(head_button(page, "Make larger")).to_have_count(0)
    unpin.click()  # floats back as the enlarged bubble
    expect(divider(page)).to_have_count(0)
    expect(fab(page)).to_be_visible()
    page.wait_for_timeout(250)
    assert round(box(window(page))["width"]) == 640
    expect(head_button(page, PIN)).to_be_visible()


def test_a07_1_divider_drags_by_mouse_and_moves_by_arrow_keys_within_320px_and_60_percent(open_app):
    page = open_app()
    chat = pin(page)
    d = box(divider(page))
    page.mouse.move(d["x"] + 3, d["y"] + 100)
    page.mouse.down()
    page.mouse.move(DESKTOP - 600, d["y"] + 100, steps=5)
    page.mouse.up()
    moved = box(divider(page))
    assert moved["x"] + moved["width"] / 2 == pytest.approx(DESKTOP - 600, abs=4)  # the divider follows the mouse
    assert box(chat)["x"] >= moved["x"] + moved["width"] - 0.5
    divider(page).focus()
    page.keyboard.press("ArrowRight")
    before = int(divider(page).get_attribute("aria-valuenow") or 0)
    page.keyboard.press("ArrowLeft")
    assert int(divider(page).get_attribute("aria-valuenow") or 0) == before + 24  # 24px steps; left widens the chat
    page.keyboard.press("ArrowRight")
    assert int(divider(page).get_attribute("aria-valuenow") or 0) == before
    for _ in range(40):
        page.keyboard.press("ArrowRight")
    assert int(divider(page).get_attribute("aria-valuenow") or 0) == 320  # min
    page.wait_for_timeout(100)
    assert round(box(chat)["width"]) == 320
    for _ in range(60):
        page.keyboard.press("ArrowLeft")
    assert int(divider(page).get_attribute("aria-valuenow") or 0) == int(DESKTOP * 0.6)  # max 60% of the window
    page.mouse.move(box(divider(page))["x"] + 3, 300)
    page.mouse.down()
    page.mouse.move(100, 300, steps=5)  # far past the max
    page.mouse.up()
    assert int(divider(page).get_attribute("aria-valuenow") or 0) == int(DESKTOP * 0.6)
    assert no_sideways_scroll(page)


def test_a07_1_divider_turns_purple_on_hover_and_focus(open_app):
    page = open_app()
    pin(page)
    accent = page.evaluate("(() => { const d = document.createElement('div'); d.style.background = 'var(--accent)'; "
                           "document.body.append(d); const c = getComputedStyle(d).backgroundColor; d.remove(); "
                           "return c })()")
    bg = lambda: divider(page).evaluate("el => getComputedStyle(el).backgroundColor")  # noqa: E731
    assert bg() != accent
    divider(page).hover()
    page.wait_for_timeout(250)
    assert bg() == accent
    page.mouse.move(10, 10)
    divider(page).focus()
    page.keyboard.press("ArrowLeft")  # by keyboard, so :focus-visible applies
    page.wait_for_timeout(250)
    assert bg() == accent

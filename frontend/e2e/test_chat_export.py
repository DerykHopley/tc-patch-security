"""Browser check for the chat's Export (F147, #147). Check ids: F147.n.

The file's words are unit-tested (`npm test`: chat/exportChat.test.ts, F147.1 to F147.9); this checks the button in
the chat header and the file it downloads. Expected look: docs/design/DESIGN.md §6.2 (Header, Export).
"""
import re

import pytest
from playwright.sync_api import Page, expect

from reduced_motion import scene, still
from test_chat import ask, open_chat, window
from test_contrast import low_contrast, show
from test_dashboard import api
from test_shell import DESKTOP, PHONE, SHOTS, no_sideways_scroll, open_app, settled  # noqa: F401 (open_app: a fixture)

Q = "What is prompt injection?"
NAME = re.compile(r"^patch-chat-\d{4}-\d{2}-\d{2}-\d{4}\.md$")


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


def export_button(page: Page):
    return window(page).locator(".chat-head").get_by_role("button", name="Export")


def test_f147_10_export_is_off_while_empty_then_downloads_the_conversation_by_keyboard(open_app):
    page = open_app()
    open_chat(page)
    expect(export_button(page)).to_be_disabled()

    answer = ask(page, Q)
    answer.get_by_role("button", name=re.compile(r"^Show \d+ sources?")).click()
    titles = answer.locator(".source-head a").all_inner_texts()
    assert titles, "the fake answer should have sources"
    first_line = answer.locator(".answer-text p").first.inner_text()

    # Keyboard: Tab from New chat reaches Export, Enter downloads
    window(page).get_by_role("button", name="New chat").focus()
    page.keyboard.press("Tab")
    expect(export_button(page)).to_be_focused()
    with page.expect_download() as info:
        page.keyboard.press("Enter")
    download = info.value
    assert NAME.match(download.suggested_filename), download.suggested_filename
    text = open(download.path(), encoding="utf-8").read()

    assert text.startswith("# Chat with Patch\n"), text[:200]
    assert f"**You:** {Q}" in text, text
    assert first_line.split("[")[0].strip()[:40] in text, (first_line, text)  # the answer, as shown
    assert "Sources:" in text, text
    for title in titles:
        assert title.replace("[", "\\[").replace("]", "\\]") in text, (title, text)


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_f147_11_the_header_with_export_in_light_and_dark_on_a_phone_and_desktop(open_app, width, scheme):
    page = open_app(width=width, scheme=scheme)
    open_chat(page)
    ask(page, Q)
    head = window(page).locator(".chat-head")
    expect(export_button(page)).to_be_enabled()
    for name in ("New chat", "Export", "Close the chat"):
        expect(head.get_by_role("button", name=name)).to_be_visible()
    # One row of buttons: Export sits beside New chat, not wrapped under it
    new, exp = (head.get_by_role("button", name=n).bounding_box() for n in ("New chat", "Export"))
    # Same row: their middles line up. Not their tops: the icon button (about 30px) is taller than the pill (about
    # 27px), so the tops differ by about 3px (CI's Chromium, 2026-10-22: 3.2px failed a 2px check on the tops)
    middle = lambda b: b["y"] + b["height"] / 2  # noqa: E731
    assert abs(middle(new) - middle(exp)) < 4 and exp["x"] > new["x"], (new, exp)
    assert no_sideways_scroll(page)
    settled(window(page))
    found = low_contrast(page, ".chat-head")
    assert not found, show(found)
    SHOTS.mkdir(exist_ok=True)
    head.screenshot(path=SHOTS / f"f147-chat-export-{scheme}-{width}.png")


@scene
def f147_12_header_with_export(fx):
    page = fx("open_app")(reduced=True)
    open_chat(page)
    ask(page, Q)
    export_button(page).focus()
    still(page, "chat header with Export")

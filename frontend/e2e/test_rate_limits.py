"""Browser check for rate limits (B11, #43). Check ids: B11.n.

The chat's 429 (a limit) and 402 (the model's spending cap) come from a routed /chat, so no test spends the shared
backend's limits. The backend's side is backend/tests/test_rate_limits.py. Expected look: docs/design/DESIGN.md §6.2
("A limit or the spending cap").
"""
import pytest
from playwright.sync_api import Page, expect

from test_chat import head_bot, open_chat, window
from test_live import SHOTS
from test_partial import text_contrast
from test_shell import DESKTOP, PHONE, no_sideways_scroll, open_app  # noqa: F401 (fixture)

Q = "What is prompt injection?"
LIMIT = "You've sent 10 messages in the last minute, the most allowed. Try again at 09:01 UTC."
CAP = ("Patch can't answer right now: the app's spending cap for the model has been reached. Try again later, or "
       "tell the owner.")
CORS = {"Access-Control-Allow-Origin": "*"}


def refuse(page: Page, status: int, error: dict) -> None:
    page.route("**/chat", lambda route: route.fulfill(status=status, headers=CORS, json={"error": error}))


def send(page: Page) -> None:
    box = window(page).get_by_role("textbox", name="Message")
    box.fill(Q)
    box.press("Enter")


def test_b11_6_a_limit_is_a_quiet_note_under_the_question_with_the_retry_time(open_app):
    page = open_app()
    open_chat(page)
    refuse(page, 429, {"code": "rate_limited", "message": LIMIT, "retry_at": "2026-10-16T09:01:00+00:00",
                       "retry_after": 60})
    send(page)
    note = window(page).locator(".chat-limit")
    expect(note).to_have_text(LIMIT)
    expect(window(page).get_by_role("status").filter(has_text=LIMIT)).to_be_visible()  # said politely, not an alert
    expect(window(page).locator(".message.error")).to_have_count(0)  # no red bubble
    expect(window(page).get_by_role("textbox", name="Message")).to_have_value(Q)  # B20: the question is kept
    expect(head_bot(page)).to_have_attribute("data-mood", "idle")  # a limit isn't a fault: Patch doesn't shake
    page.unroute("**/chat")


def test_b11_6_the_spending_cap_is_the_same_quiet_note(open_app):
    page = open_app()
    open_chat(page)
    refuse(page, 402, {"code": "spending_cap", "message": CAP})
    send(page)
    expect(window(page).locator(".chat-limit")).to_have_text(CAP)
    page.unroute("**/chat")


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b11_6_the_note_in_both_themes_and_on_a_phone(open_app, scheme, width):
    page = open_app(width=width, scheme=scheme)
    open_chat(page)
    refuse(page, 429, {"code": "rate_limited", "message": LIMIT, "retry_at": "2026-10-16T09:01:00+00:00",
                       "retry_after": 60})
    send(page)
    note = window(page).locator(".chat-limit")
    expect(note).to_be_visible()
    assert text_contrast(note, ".chat-window") >= 4.5
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    window(page).screenshot(path=SHOTS / f"b11-limit-note-{scheme}-{width}.png")
    page.unroute("**/chat")

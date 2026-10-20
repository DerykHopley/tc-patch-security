"""Browser check (seam 3) for the Telegram channel on Settings → Delivery (B57, #102). Check ids: B57.n.

The snapshot pair runs with sign-in off, so the one local user is the owner. run.sh sets NOTIFY_DRY_RUN=1: nothing is
sent to Telegram, and "Find my chat id" asks Telegram nothing either (the server answers one example chat). The token
below is made up. Another user is the browser told so (test_settings_parts.py's `not_the_owner`).
Expected values come from docs/design/DESIGN.md §5.7, not from the CSS.
"""
import pytest
from playwright.sync_api import Page, expect

from reduced_motion import scene, still
from test_settings import panel
from test_settings_layout import as_rgb, block, summary
from test_settings_over_env import open_settings, server_defaults  # noqa: F401 (fixtures)
from test_settings_parts import open_settings_as, shot  # noqa: F401 (a fixture)
from test_shell import contrast, no_sideways_scroll

PHONE, DESKTOP = 390, 1440
TOKEN = "123456789:AAH-made-up-e2e-token-never-real"  # never reaches Telegram (NOTIFY_DRY_RUN)
EXAMPLE_CHAT = "123456789"  # the dry run's example chat (backend/app/main.py `telegram_chats`)


def row(page: Page):
    return panel(page, "Delivery").locator(".channel").filter(
        has=page.get_by_role("checkbox", name="Telegram", exact=True))


def set_up_by_hand(page: Page) -> None:
    """The owner's steps on the page: open the block, paste the token, Find my chat id, save."""
    summary(page, "Telegram").click()
    page.get_by_label("Bot token", exact=True).fill(TOKEN)
    page.get_by_role("button", name="Find my chat id").click()
    expect(page.get_by_label("Chat id", exact=True)).to_have_value(EXAMPLE_CHAT)
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_text("✓ Changes saved")).to_be_visible()


# --- B57.15: the owner's Telegram row: tick, Send test, its set-up state --------------------------------------------

def test_b57_15_the_owner_sees_a_telegram_row_not_set_up(open_settings):
    page = open_settings(width=DESKTOP)
    r = row(page)
    expect(r.locator(".setup-pill")).to_have_text("not set up")
    expect(r.get_by_role("button", name="Send test alert by telegram")).to_be_visible()
    expect(r).to_contain_text("Set the bot token and the chat id under Telegram, below.")
    expect(summary(page, "Telegram")).to_have_text("Telegram · not set up")
    expect(block(page, "Telegram")).not_to_have_attribute("open", "")
    page.get_by_role("checkbox", name="Telegram", exact=True).check()  # ticked but not set up: its block opens
    expect(block(page, "Telegram")).to_have_attribute("open", "")


def test_b57_15_the_steps_find_my_chat_id_and_save_make_it_ready(open_settings, api_url):
    page = open_settings(width=DESKTOP)
    set_up_by_hand(page)
    expect(row(page).locator(".setup-pill")).to_have_text("ready")
    expect(row(page)).to_contain_text("To your chat, from your bot.")
    expect(summary(page, "Telegram")).to_have_text("Telegram · set up")
    expect(page.get_by_text("Found your chat with Example chat (dry run: Telegram wasn't asked).")).to_be_visible()
    token = page.get_by_label("Bot token", exact=True)
    expect(token).to_have_value("")  # write-only: the box empties after a save
    expect(token).to_have_attribute("placeholder", "saved")
    assert TOKEN not in page.content()

    row(page).get_by_role("button", name="Send test alert by telegram").click()
    expect(panel(page, "Delivery").get_by_text("Sent by telegram. Check that it arrived.")).to_be_visible()
    expect(panel(page, "Delivery").locator(".channel-results .result").first).to_contain_text("telegram")
    assert TOKEN not in page.content()


def test_b57_15_find_my_chat_id_without_a_token_says_to_type_one(open_settings):
    page = open_settings(width=DESKTOP)
    summary(page, "Telegram").click()
    page.get_by_role("button", name="Find my chat id").click()
    line = page.locator("#srv-telegram-chat-id-found")
    expect(line).to_have_text("Type the bot token first: Patch asks Telegram with it.")
    expect(line).to_have_class("meta chat-found error")
    expect(page.get_by_label("Chat id", exact=True)).to_have_value("")


def test_b57_15_the_steps_are_in_order_and_name_botfather(open_settings):
    page = open_settings(width=DESKTOP)
    summary(page, "Telegram").click()
    steps = page.get_by_role("list", name="How to set up Telegram").locator("li")
    expect(steps).to_have_count(4)
    expect(steps.nth(0)).to_contain_text("@BotFather")
    expect(steps.nth(0)).to_contain_text("/newbot")
    expect(steps.nth(2)).to_contain_text("Start")


# --- B57.16: light and dark, phone and desktop (DESIGN.md §5.7) ------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b57_16_the_telegram_row_and_block_in_both_themes_at_both_widths(open_settings, width, scheme):
    page = open_settings(width=width, scheme=scheme)
    nested = as_rgb(page, page.evaluate("getComputedStyle(document.querySelector('.channel')).backgroundColor"))
    pill = row(page).locator(".setup-pill")
    pill_box, row_box = pill.bounding_box(), row(page).bounding_box()
    assert pill_box and row_box and pill_box["width"] < row_box["width"] / 2  # the pill hugs its text
    summary(page, "Telegram").click()
    b = block(page, "Telegram")
    assert as_rgb(page, b.evaluate("el => getComputedStyle(el).backgroundColor")) == nested
    assert b.evaluate("el => getComputedStyle(el).borderTopLeftRadius") == "18px"
    steps = page.get_by_role("list", name="How to set up Telegram")
    assert contrast(as_rgb(page, steps.evaluate("e => getComputedStyle(e).color")), nested) >= 4.5
    page.get_by_label("Bot token", exact=True).fill(TOKEN)
    page.get_by_role("button", name="Find my chat id").click()
    line = page.locator("#srv-telegram-chat-id-found")
    expect(line).to_have_class("meta chat-found ok")
    assert contrast(as_rgb(page, line.evaluate("e => getComputedStyle(e).color")), nested) >= 4.5
    assert line.evaluate("e => getComputedStyle(e).borderLeftWidth") == "3px"
    card, box = panel(page, "Delivery").bounding_box(), b.bounding_box()
    assert card and box and box["x"] >= card["x"] and box["x"] + box["width"] <= card["x"] + card["width"] + 0.5
    chat = page.get_by_label("Chat id", exact=True).bounding_box()
    assert chat and chat["x"] + chat["width"] <= card["x"] + card["width"]
    assert no_sideways_scroll(page)
    b.scroll_into_view_if_needed()
    shot(page, f"telegram-{width}-{scheme}")  # for the owner's review, when E2E_SHOTS is set


def test_b57_16_find_my_chat_id_by_keyboard(open_settings):
    page = open_settings(width=DESKTOP)
    summary(page, "Telegram").focus()
    page.keyboard.press("Enter")
    page.get_by_label("Bot token", exact=True).fill(TOKEN)
    page.get_by_label("Chat id", exact=True).focus()
    page.keyboard.press("Tab")
    expect(page.get_by_role("button", name="Find my chat id")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.get_by_label("Chat id", exact=True)).to_have_value(EXAMPLE_CHAT)


# --- B57.17: anyone but the owner never sees it (B48, B50) -------------------------------------------------------------

@pytest.mark.parametrize("width, scheme", [(PHONE, "dark"), (DESKTOP, "light")])
def test_b57_17_another_user_sees_no_telegram(open_settings_as, width, scheme):
    page = open_settings_as("viewer", width=width, scheme=scheme)
    expect(page.get_by_role("checkbox", name="Telegram")).to_have_count(0)
    expect(page.get_by_text("Telegram")).to_have_count(0)
    expect(page.get_by_label("Bot token")).to_have_count(0)


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) ------------------------------------

@scene
def b57_18_telegram_setup(fx):
    page = fx("open_settings")(reduced=True)
    summary(page, "Telegram").click()
    still(page, "Telegram block open")
    page.get_by_label("Bot token", exact=True).fill(TOKEN)
    page.get_by_role("button", name="Find my chat id").click()
    expect(page.get_by_label("Chat id", exact=True)).to_have_value(EXAMPLE_CHAT)
    still(page, "chat id found")

"""Browser check (seam 3) for the Settings page's layout: two packed columns under the Watchlist, and Delivery's
setup blocks folded. Check ids: SL.n (the owner's decision of 2026-10-16, DECISIONS.md). Since B48 (#97) the page has
two parts, "Yours" and "This Patch" (the owner's), each with its own packed columns (test_settings_parts.py checks the
parts themselves).

The snapshot pair runs with sign-in off, so the one local user is the owner and sees Delivery's setup blocks.
Expected values come from docs/design/DESIGN.md §5.7, not from the CSS.
"""
import pytest
from playwright.sync_api import Page, expect

from test_settings import panel
from test_settings_over_env import open_settings, server_defaults  # noqa: F401 (fixtures)
from test_shell import DESKTOP, PHONE, contrast, no_sideways_scroll
from reduced_motion import scene, still

WIDE = 1440  # the width the owner's comparison was measured at
# B48: "Yours" (Connected accounts needs a real Clerk user: not here) and "This Patch" (Requests needs sign-in on: not
# here either). This Patch's right column comes first in the DOM, so Requests leads it when there is one.
LEFT = ["Profile", "Alerts"]
RIGHT = ["Patch's answers", "Priority and due dates"]
START_OVER = "Start over"  # B50: its own warning card, across both columns at the end of "Yours"
PATCH_RIGHT = ["Refresh runs", "Data"]  # #144: Data under Refresh runs, now that Delivery has the full alerts log
PATCH_LEFT = ["Delivery"]
ORDER = ["Watchlist", *LEFT, *RIGHT, START_OVER, *PATCH_RIGHT, *PATCH_LEFT]  # reading order = DOM order = Tab order
GAP = 1.2 * 16  # the gap between cards (DESIGN.md §4.1)


def cards(page: Page) -> list[tuple[str, dict]]:
    """Each Settings card's title and box, in DOM order."""
    return page.evaluate("""[...document.querySelectorAll('main section.card')].map(c => {
        const r = c.getBoundingClientRect();
        return [c.querySelector('.card-title').textContent, {x: r.left, y: r.top + scrollY, width: r.width, height: r.height}] })""")


# --- SL.1: two packed columns under the Watchlist ---------------------------------------------------------------------

def packed(box: dict, column: list[str], top: float) -> None:
    """Each card starts one gap under the one above (or under `top`), never lower: no holes."""
    xs = {round(box[t]["x"]) for t in column}
    assert len(xs) == 1, (column, xs)  # one column each
    for title in column:
        assert abs(box[title]["y"] - (top + GAP)) <= 2, title  # rem rounding
        top = box[title]["y"] + box[title]["height"]


def test_sl_1_two_packed_columns_under_a_full_width_watchlist(open_settings):
    page = open_settings(width=WIDE)
    boxes = cards(page)
    assert [t for t, _ in boxes] == ORDER
    box = dict(boxes)
    watch = box["Watchlist"]
    for column in (LEFT, RIGHT):
        packed(box, column, watch["y"] + watch["height"])
    assert box["Alerts"]["x"] < box["Patch's answers"]["x"]
    left, right = box["Alerts"], box["Patch's answers"]
    assert abs(watch["x"] - left["x"]) <= 1 and abs(watch["x"] + watch["width"] - right["x"] - right["width"]) <= 1
    # B50: Start over across both columns, one gap under the longer one
    start = box[START_OVER]
    assert abs(start["x"] - watch["x"]) <= 1 and abs(start["width"] - watch["width"]) <= 1
    columns_end = max(box[t]["y"] + box[t]["height"] for t in LEFT + RIGHT)
    assert abs(start["y"] - (columns_end + GAP)) <= 2
    # This Patch: its own two columns, level at the top, the right one (Requests first, B48) on the right
    top = min(box["Delivery"]["y"], box["Refresh runs"]["y"]) - GAP
    packed(box, PATCH_LEFT, top)
    packed(box, PATCH_RIGHT, top)
    assert abs(box["Delivery"]["x"] - left["x"]) <= 1 and abs(box["Refresh runs"]["x"] - right["x"]) <= 1
    assert box["Delivery"]["y"] > max(box[t]["y"] + box[t]["height"] for t in LEFT + RIGHT)  # under "Yours"


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_sl_1_one_column_in_the_same_order_on_a_phone(open_settings, scheme):
    page = open_settings(width=PHONE, scheme=scheme)
    boxes = cards(page)
    assert [t for t, _ in boxes] == ORDER
    assert len({round(b["x"]) for _, b in boxes}) == 1
    ys = [b["y"] for _, b in boxes]
    assert ys == sorted(ys)
    assert no_sideways_scroll(page)


# --- SL.2: Tab goes down the left column, then the right ---------------------------------------------------------------

def test_sl_2_tab_order_is_the_reading_order(open_settings):
    page = open_settings(width=WIDE)
    panel(page, "Watchlist").get_by_role("checkbox").first.focus()
    visited: list[str] = []
    for _ in range(400):
        title = page.evaluate("""(() => { const c = document.activeElement.closest('main section.card');
            return c ? c.querySelector('.card-title').textContent : null })()""")
        if title and (not visited or visited[-1] != title):
            visited.append(title)
        if title is None and visited:
            break  # out of the cards: the save bar
        page.keyboard.press("Tab")
    assert visited == ORDER


# --- SL.3: Delivery's setup blocks are folded, each with a summary naming it and its state -------------------------

TOPIC = "patch-e2e-topic-7c1d"  # a made-up topic: never reaches ntfy (NOTIFY_DRY_RUN)
BLOCKS = {"Alert links": "App address for alert links", "Phone push (ntfy)": "Topic", "Telegram": "Bot token",
          "Email (SMTP)": "SMTP server"}  # B57 added Telegram


def block(page: Page, name: str):
    return panel(page, "Delivery").locator("details.setup-block").filter(
        has=page.locator("summary", has_text=name))


def summary(page: Page, name: str):
    return block(page, name).locator("summary")


def field(page: Page, label: str):
    return panel(page, "Delivery").get_by_label(label, exact=True)


def save(page: Page) -> None:
    page.get_by_role("button", name="Save changes").click()


def test_sl_3_setup_blocks_are_folded_and_say_their_state(open_settings):
    page = open_settings(width=WIDE)
    d = panel(page, "Delivery")
    expect(d.locator("details.setup-block")).to_have_count(len(BLOCKS))
    for name, label in BLOCKS.items():
        expect(block(page, name)).not_to_have_attribute("open", "")
        expect(summary(page, name)).to_be_visible()
        expect(field(page, label)).to_be_hidden()
    expect(summary(page, "Phone push (ntfy)")).to_have_text("Phone push (ntfy) · not set up")
    expect(summary(page, "Email (SMTP)")).to_have_text("Email (SMTP) · not set up")
    expect(summary(page, "Alert links")).to_have_text("Alert links · this computer only")
    expect(summary(page, "Telegram")).to_have_text("Telegram · not set up")
    for name in ("Desktop notification", "Email", "Phone push (ntfy)", "Telegram"):  # the channel rows stay in view
        row = d.locator(".channel").filter(has=page.get_by_role("checkbox", name=name, exact=True))
        expect(row.get_by_role("checkbox")).to_be_visible()
        expect(row.locator(".setup-pill")).to_be_visible()
        expect(row.get_by_role("button", name="Send test")).to_be_visible()


def test_sl_3_a_saved_channel_says_set_up(open_settings):
    page = open_settings(width=WIDE)
    summary(page, "Phone push (ntfy)").click()
    field(page, "Topic").fill(TOPIC)
    save(page)
    expect(page.get_by_text("✓ Changes saved")).to_be_visible()
    expect(summary(page, "Phone push (ntfy)")).to_have_text("Phone push (ntfy) · set up")


# --- SL.5: ticking a channel that isn't set up opens its setup block ---------------------------------------------------

def test_sl_5_ticking_a_channel_that_is_not_set_up_opens_its_block(open_settings):
    page = open_settings(width=WIDE)
    page.get_by_role("checkbox", name="Email", exact=True).check()
    expect(block(page, "Email (SMTP)")).to_have_attribute("open", "")
    expect(field(page, "SMTP server")).to_be_visible()
    expect(block(page, "Phone push (ntfy)")).not_to_have_attribute("open", "")  # only its own
    page.get_by_role("checkbox", name="Email", exact=True).uncheck()
    expect(block(page, "Email (SMTP)")).to_have_attribute("open", "")  # unticking doesn't fold it
    page.get_by_role("checkbox", name="Phone push (ntfy)", exact=True).check()
    expect(block(page, "Phone push (ntfy)")).to_have_attribute("open", "")


def test_sl_5_ticking_a_channel_that_is_set_up_leaves_its_block_folded(open_settings):
    page = open_settings(width=WIDE)
    summary(page, "Phone push (ntfy)").click()
    field(page, "Topic").fill(TOPIC)
    save(page)
    expect(summary(page, "Phone push (ntfy)")).to_have_text("Phone push (ntfy) · set up")
    summary(page, "Phone push (ntfy)").click()
    expect(block(page, "Phone push (ntfy)")).not_to_have_attribute("open", "")
    page.get_by_role("checkbox", name="Phone push (ntfy)", exact=True).check()
    expect(block(page, "Phone push (ntfy)")).not_to_have_attribute("open", "")


# --- SL.6: a save error in a folded block opens it and focuses the field --------------------------------------------

def test_sl_6_a_refused_field_in_a_folded_block_opens_it_and_is_focused(open_settings):
    page = open_settings(width=WIDE)
    summary(page, "Phone push (ntfy)").click()
    field(page, "Topic").fill("not a topic!")  # ntfy's rule: letters, digits, - and _
    summary(page, "Phone push (ntfy)").click()  # folded again before saving
    expect(field(page, "Topic")).to_be_hidden()
    save(page)
    expect(panel(page, "Delivery").get_by_role("alert")).to_contain_text("ntfy_topic")
    expect(block(page, "Phone push (ntfy)")).to_have_attribute("open", "")
    expect(field(page, "Topic")).to_be_focused()
    expect(field(page, "Topic")).to_have_value("not a topic!")  # the edit stays
    expect(block(page, "Email (SMTP)")).not_to_have_attribute("open", "")


def test_sl_6_an_error_naming_no_field_opens_the_blocks_with_unsaved_edits(open_settings, api_url):
    page = open_settings(width=WIDE)
    page.route(f"{api_url}/settings/server", lambda route: route.abort() if route.request.method == "PUT"
               else route.fallback())
    summary(page, "Email (SMTP)").click()
    field(page, "User name").fill("alerts@example.com")
    summary(page, "Email (SMTP)").click()
    save(page)
    expect(panel(page, "Delivery").get_by_role("alert")).to_contain_text("Can't reach the backend")
    expect(block(page, "Email (SMTP)")).to_have_attribute("open", "")
    expect(field(page, "User name")).to_be_focused()
    expect(block(page, "Phone push (ntfy)")).not_to_have_attribute("open", "")


# --- SL.7: unsaved edits survive folding ------------------------------------------------------------------------------

def test_sl_7_unsaved_edits_survive_folding_and_the_summary_says_so(open_settings):
    page = open_settings(width=WIDE)
    summary(page, "Phone push (ntfy)").click()
    field(page, "Topic").fill(TOPIC)
    field(page, "Server").fill("https://ntfy.example.com")
    summary(page, "Phone push (ntfy)").click()
    expect(field(page, "Topic")).to_be_hidden()
    expect(summary(page, "Phone push (ntfy)")).to_have_text("Phone push (ntfy) · not set up · unsaved changes")
    expect(page.get_by_text("Unsaved changes", exact=True)).to_be_visible()  # the save bar too
    summary(page, "Phone push (ntfy)").click()
    expect(field(page, "Topic")).to_have_value(TOPIC)
    expect(field(page, "Server")).to_have_value("https://ntfy.example.com")
    page.get_by_role("button", name="Discard").click()
    expect(summary(page, "Phone push (ntfy)")).to_have_text("Phone push (ntfy) · not set up")


# --- SL.8: by keyboard: Tab reaches each summary, Enter and Space open and fold, focus shows -------------------------

def test_sl_8_a_block_opens_and_folds_by_keyboard_with_visible_focus(open_settings):
    page = open_settings(width=WIDE)
    page.get_by_role("button", name="Send test alert by telegram").focus()  # B57: Telegram's row is the last
    page.keyboard.press("Tab")  # from the last channel row to the first setup block
    first = summary(page, "Alert links")
    expect(first).to_be_focused()
    outline = first.evaluate("el => [getComputedStyle(el).outlineStyle, getComputedStyle(el).outlineWidth]")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2
    page.keyboard.press("Enter")
    expect(block(page, "Alert links")).to_have_attribute("open", "")
    page.keyboard.press("Tab")
    expect(field(page, "App address for alert links")).to_be_focused()  # into the open block
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Space")
    expect(block(page, "Alert links")).not_to_have_attribute("open", "")
    page.keyboard.press("Tab")  # folded: its fields are skipped
    expect(summary(page, "Phone push (ntfy)")).to_be_focused()
    page.keyboard.press("Space")
    expect(field(page, "Topic")).to_be_visible()


# --- SL.9: light and dark, phone and desktop ----------------------------------------------------------------------------

def as_rgb(page: Page, colour: str) -> str:
    """Any CSS colour (the nested fill is a color-mix) as rgb(), painted on a canvas and read back."""
    return page.evaluate("""c => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c;
        x.fillRect(0, 0, 1, 1); const [r, g, b] = x.getImageData(0, 0, 1, 1).data; return `rgb(${r}, ${g}, ${b})` }""",
                         colour)


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_sl_9_setup_blocks_in_both_themes_at_both_widths(open_settings, width, scheme):
    page = open_settings(width=width, scheme=scheme)
    nested = page.evaluate("getComputedStyle(document.querySelector('.channel')).backgroundColor")
    for name in BLOCKS:
        s = summary(page, name)
        s.click()
        b = block(page, name)
        assert b.evaluate("el => getComputedStyle(el).backgroundColor") == nested  # a nested card, like a channel
        assert b.evaluate("el => getComputedStyle(el).borderTopLeftRadius") == "18px"
        assert contrast(s.evaluate("el => getComputedStyle(el).color"), as_rgb(page, nested)) >= 4.5
        card, box = panel(page, "Delivery").bounding_box(), b.bounding_box()
        assert card and box and box["x"] >= card["x"] and box["x"] + box["width"] <= card["x"] + card["width"]
    assert no_sideways_scroll(page)  # every block open: the widest the card gets


def test_sl_9_opening_a_block_never_animates(open_settings):
    # Normal motion: the disclosure doesn't move either (DESIGN.md §7). Patch idles on his own; only main counts.
    page = open_settings(width=WIDE)
    moving = """document.getAnimations().filter(a => a.effect.target.closest && a.effect.target.closest('main'))
        .map(a => a.animationName || a.transitionProperty)"""
    summary(page, "Email (SMTP)").click()
    assert page.evaluate(moving) == []
    summary(page, "Email (SMTP)").click()
    assert page.evaluate(moving) == []


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) ------------------------------------

@scene
def sl_10_setup_blocks(fx):
    page = fx("open_settings")(reduced=True)
    for name in BLOCKS:
        summary(page, name).click()
        still(page, f"{name} open")
    page.get_by_role("checkbox", name="Email", exact=True).check()
    still(page, "a channel ticked")

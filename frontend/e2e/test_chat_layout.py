"""Browser check (seam 3) for the chat layout: enlarge, pin, keyboard, phone, Ask about this. Check ids: A07.n,
from ticket #9.

Runs in Firefox and Chromium (run.sh). Expected values come from docs/design/DESIGN.md §6.3–§6.5, §7.1, §10 and §11,
not from the CSS.
"""
import pytest
from playwright.sync_api import Locator, Page, expect

from test_chat import box, fab, window
from test_shell import DESKTOP, PHONE, SHOTS, contrast, eventually, no_sideways_scroll, open_app, settled  # noqa: F401

REM = 15  # px: the base font size (DESIGN.md §3.4)
HEIGHT = 900  # the viewport height open_app uses


def open_chat(page: Page) -> Locator:
    fab(page).click()
    expect(window(page)).to_be_visible()
    settled(window(page))  # the pop (0.16s) scales the window while it runs
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
    settled(window(page))
    w = box(window(page))
    assert round(w["width"]) == 640
    assert round(w["height"]) == HEIGHT - 5 * REM
    assert round(DESKTOP - (w["x"] + w["width"])) == round(1.25 * REM)
    expect(head_button(page, PIN)).to_be_visible()
    head_button(page, "Make smaller").click()
    settled(window(page))
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
    settled(window(page))
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
    eventually(page, lambda: round(box(chat)["width"]) == 320)
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
    eventually(page, lambda: bg() == accent)  # a colour transition
    page.mouse.move(10, 10)
    head_button(page, UNPIN).focus()
    page.keyboard.press("Shift+Tab")  # by keyboard: the divider comes just before the chat
    expect(divider(page)).to_be_focused()
    eventually(page, lambda: bg() == accent)


# --- A07.2: remembered; the page underneath is not rebuilt (DESIGN.md §6.3, §11) ---------------------------------

def test_a07_2_pinned_and_its_width_are_remembered_and_a_pinned_chat_opens_pinned(open_app):
    page = open_app()
    pin(page)
    divider(page).focus()
    page.keyboard.press("ArrowLeft")
    page.keyboard.press("ArrowLeft")
    assert page.evaluate("[localStorage.pinned, localStorage.splitWidth]") == ["1", "488"]
    page.reload()
    expect(head_button(page, UNPIN)).to_be_visible()  # opens pinned
    assert round(box(window(page))["width"]) == 488
    expect(fab(page)).to_be_hidden()
    head_button(page, UNPIN).click()
    page.reload()
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    expect(window(page)).to_have_count(0)  # unpinned: the chat starts closed again
    assert page.evaluate("localStorage.pinned") == "0"


def test_a07_2_old_layout_split_link_pins_the_chat(open_app):
    page = open_app(query="?layout=split")
    expect(head_button(page, UNPIN)).to_be_visible()


def severity_filter(page: Page) -> Locator:
    return page.get_by_role("region", name="CVEs on your watchlist").get_by_label("Severity")


def test_a07_2_page_keeps_its_scroll_and_filters_when_pinning_and_unpinning(open_app):
    page = open_app(query="/cves", width=DESKTOP)  # the table lives on the CVEs page since A04b
    expect(page.locator("table.cves tbody tr").first).to_be_visible()
    severity_filter(page).select_option("HIGH")
    expect(page.locator("table.cves tbody tr").first).to_be_visible()
    page.evaluate("document.querySelector('main').dataset.probe = 'kept'")  # gone if the page were rebuilt
    page.evaluate("window.scrollTo(0, 300)")
    scroll = page.evaluate("window.scrollY")
    assert scroll > 0
    pin(page)
    assert page.evaluate("document.querySelector('main').dataset.probe") == "kept"
    expect(severity_filter(page)).to_have_value("HIGH")
    assert page.evaluate("window.scrollY") == pytest.approx(scroll, abs=2)
    head_button(page, UNPIN).click()
    assert page.evaluate("document.querySelector('main').dataset.probe") == "kept"
    expect(severity_filter(page)).to_have_value("HIGH")
    assert page.evaluate("window.scrollY") == pytest.approx(scroll, abs=2)


def test_a07_1_pinned_chat_stays_within_60_percent_when_the_window_narrows(open_app):
    page = open_app()
    chat = pin(page)
    divider(page).focus()
    for _ in range(20):
        page.keyboard.press("ArrowLeft")
    assert round(box(chat)["width"]) == 840
    page.set_viewport_size({"width": 1000, "height": HEIGHT})
    expect(divider(page)).to_have_attribute("aria-valuenow", "600")
    assert round(box(chat)["width"]) == 600
    assert no_sideways_scroll(page)


# --- A07.3: Ctrl/Cmd+K, Esc, the sidebar (DESIGN.md §6.4) --------------------------------------------------------

def message_box(page: Page) -> Locator:
    return window(page).get_by_role("textbox", name="Message")


@pytest.mark.parametrize("page_name", ["Dashboard", "CVEs", "Settings", "Dev"])
@pytest.mark.parametrize("key", ["Control+k", "Meta+k"])
def test_a07_3_ctrl_or_cmd_k_opens_the_chat_on_any_page(open_app, page_name, key):
    page = open_app()
    page.get_by_role("button", name=page_name, exact=True).click()
    page.locator("h1").click()  # focus on the page, not in a field
    page.keyboard.press(key)
    expect(window(page)).to_be_visible()
    expect(message_box(page)).to_be_focused()
    page.get_by_role("button", name="Switch to dark mode").focus()
    page.keyboard.press(key)  # already open: back to the message box
    expect(window(page)).to_be_visible()
    expect(message_box(page)).to_be_focused()


def test_a07_3_esc_closes_the_bubble_and_returns_focus_to_patch(open_app):
    page = open_app()
    open_chat(page)
    page.keyboard.press("Escape")
    expect(window(page)).to_have_count(0)
    expect(fab(page)).to_be_focused()
    open_chat(page)
    head_button(page, "Make larger").click()
    page.keyboard.press("Escape")  # the enlarged bubble is a bubble too
    expect(window(page)).to_have_count(0)


def test_a07_3_esc_does_not_close_a_pinned_chat(open_app):
    page = open_app()
    pin(page)
    message_box(page).focus()
    page.keyboard.press("Escape")
    page.locator("h1").click()
    page.keyboard.press("Escape")
    expect(head_button(page, UNPIN)).to_be_visible()
    head_button(page, "Close the chat").click()  # the ✕ still closes it; it stays pinned for next time
    expect(window(page)).to_have_count(0)
    expect(fab(page)).to_be_visible()
    page.keyboard.press("Control+k")
    expect(head_button(page, UNPIN)).to_be_visible()


def test_a07_3_ask_patch_in_the_sidebar_opens_and_closes_the_chat(open_app):
    page = open_app()
    ask = page.get_by_role("complementary", name="Main").get_by_role("button", name="Ask Patch")
    ask.click()
    expect(window(page)).to_be_visible()
    ask.click()
    expect(window(page)).to_have_count(0)


# --- A07.4: phones (DESIGN.md §6.5, §4.2) ------------------------------------------------------------------------

def full_screen(page: Page, loc: Locator, width: int) -> None:
    b = box(loc)
    assert (round(b["x"]), round(b["y"]), round(b["width"]), round(b["height"])) == (0, 0, width, HEIGHT)


@pytest.mark.parametrize("width", [PHONE, 700])
def test_a07_4_phone_chat_is_a_full_screen_sheet_without_pin(open_app, width):
    page = open_app(width=width)
    chat = open_chat(page)
    full_screen(page, chat, width)
    assert chat.evaluate("el => getComputedStyle(el).borderTopLeftRadius") == "0px"
    expect(head_button(page, "Make larger")).to_be_hidden()  # the sheet is already full screen (review item 15)
    expect(head_button(page, PIN)).to_be_hidden()  # no pin on a phone
    expect(head_button(page, "Close the chat")).to_be_visible()  # the sheet covers Patch's button: its ✕ closes it
    assert no_sideways_scroll(page)
    head_button(page, "Close the chat").click()
    expect(window(page)).to_have_count(0)


def test_a07_4_a_pinned_chat_on_a_phone_is_the_same_sheet(open_app):
    page = open_app(init_script="localStorage.setItem('pinned', '1')", width=PHONE)
    chat = window(page)
    expect(chat).to_be_visible()
    full_screen(page, chat, PHONE)
    expect(divider(page)).to_be_hidden()
    expect(head_button(page, UNPIN)).to_be_hidden()
    assert no_sideways_scroll(page)


def test_a07_4_patch_sits_above_the_tab_bar(open_app):
    page = open_app(width=PHONE)
    button, tab_bar = box(fab(page)), box(page.locator(".sidenav"))
    assert button["y"] + button["height"] <= tab_bar["y"]
    assert round(HEIGHT - (button["y"] + button["height"])) == 5 * REM


# --- A07.5: "Ask about this" on a CVE row (DESIGN.md §6.4) -------------------------------------------------------

def first_row_cve(page: Page) -> str:
    row = page.locator("table.cves tbody tr").first
    expect(row).to_be_visible()
    return row.locator("td").first.get_by_role("link").inner_text()


def test_a07_5_ask_about_this_opens_the_chat_over_the_cves_page_and_asks(open_app):
    page = open_app(query="/cves")  # the table moved to the CVEs page (A04b)
    cve = first_row_cve(page)
    button = page.get_by_role("button", name=f"Ask about this: {cve}")
    expect(button).to_have_text("Ask about this")
    button.focus()
    page.keyboard.press("Enter")  # reachable by keyboard
    chat = window(page)
    expect(chat).to_be_visible()
    expect(page.locator("h1")).to_have_text("CVEs")  # over the CVEs page: the page stays
    expect(chat.locator(".context-chip")).to_have_text(f"on CVEs · {cve}")  # A18: the row asked about is selected
    expect(chat.locator(".message.user")).to_have_text(f"Explain {cve} and how to defend against it.")
    answer = chat.locator(".message.assistant")
    expect(answer).to_have_count(1, timeout=10_000)
    answer.get_by_role("button", name="Show", exact=False).click()
    answer.get_by_role("tab", name="Tool calls", exact=False).click()
    expect(answer.locator(".tool-card").first).to_contain_text(cve)


def test_a07_5_ask_about_this_uses_a_pinned_chat_when_pinned(open_app):
    page = open_app(init_script="localStorage.setItem('pinned', '1')", query="/cves")
    cve = first_row_cve(page)
    head_button(page, "Close the chat").click()
    page.get_by_role("button", name=f"Ask about this: {cve}").click()
    expect(head_button(page, UNPIN)).to_be_visible()
    expect(window(page).locator(".message.user")).to_have_text(f"Explain {cve} and how to defend against it.")


# --- A07.6: an alert link #cve=CVE-… (DESIGN.md §6.4) ------------------------------------------------------------

ALERT_CVE = "CVE-2024-8309"


def alert_banner(page: Page) -> Locator:
    return page.get_by_role("region", name="Alert")


def test_a07_6_alert_link_shows_a_banner_and_explain_it_asks_patch(open_app):
    page = open_app(query=f"#cve={ALERT_CVE.lower()}")
    banner = alert_banner(page)
    expect(banner).to_contain_text(f"You opened an alert for {ALERT_CVE}.")
    expect(window(page)).to_have_count(0)  # nothing asked until the user says so
    banner.get_by_role("button", name="Explain it").click()
    expect(window(page).locator(".message.user")).to_have_text(f"Explain {ALERT_CVE} and how to defend against it.")
    expect(window(page).locator(".message.assistant")).to_have_count(1, timeout=10_000)
    expect(alert_banner(page)).to_have_count(0)
    assert "cve=" not in page.url  # a reload doesn't ask again
    page.reload()
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    expect(alert_banner(page)).to_have_count(0)


def test_a07_6_dismiss_closes_the_banner_without_asking(open_app):
    page = open_app(query=f"#cve={ALERT_CVE}")
    alert_banner(page).get_by_role("button", name="Dismiss").click()
    expect(alert_banner(page)).to_have_count(0)
    expect(window(page)).to_have_count(0)
    assert "cve=" not in page.url


def test_a07_6_alert_link_followed_while_the_app_is_open(open_app):
    page = open_app()
    expect(alert_banner(page)).to_have_count(0)
    page.evaluate(f"location.hash = 'cve={ALERT_CVE}'")
    expect(alert_banner(page)).to_contain_text(ALERT_CVE)


def test_a07_6_a_malformed_alert_link_is_ignored(open_app):
    page = open_app(query="#cve=<img src=x onerror=alert(1)>")
    expect(page.locator("h1")).to_be_visible()
    expect(alert_banner(page)).to_have_count(0)


# --- A07.7, A07.8: motion (DESIGN.md §7.1) -----------------------------------------------------------------------

def rotation(loc: Locator) -> str:
    return loc.evaluate("el => getComputedStyle(el).rotate")


def test_a07_7_pin_icon_rotates_from_35_degrees_to_0_when_pinned(open_app):
    page = open_app()
    open_chat(page)
    head_button(page, "Make larger").click()
    icon = head_button(page, PIN).locator("svg")
    assert rotation(icon) == "35deg"
    assert icon.evaluate("el => [getComputedStyle(el).transitionDuration, getComputedStyle(el).transitionProperty]") \
        == ["0.15s", "rotate"]
    head_button(page, PIN).click()
    seen = page.evaluate("""async () => {
      const icon = document.querySelector('.pin-btn svg'); const seen = [];
      const t0 = performance.now();
      while (performance.now() - t0 < 300) {
        seen.push(getComputedStyle(icon).rotate);
        await new Promise(r => requestAnimationFrame(r));
      }
      return seen;
    }""")
    assert seen[-1] in ("0deg", "none")
    assert any(s not in ("0deg", "35deg", "none") for s in seen), seen  # in between: it turns


# Reduced motion: in the shared check, test_reduced_motion.py (scene a07_8).


# --- A07.9: light and dark, phone and desktop (DESIGN.md §9, §4.2) -----------------------------------------------

def colour(page: Page, value: str) -> str:
    return page.evaluate("v => { const d = document.createElement('div'); d.style.color = v; document.body.append(d); "
                         "const c = getComputedStyle(d).color; d.remove(); return c }", value)


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a07_9_layouts_work_in_light_and_dark_at_phone_and_desktop_width(open_app, browser_name, width, scheme):
    page = open_app(width=width, scheme=scheme, reduced=True, query=f"#cve={ALERT_CVE}")
    SHOTS.mkdir(exist_ok=True)
    shot = lambda name: page.screenshot(path=SHOTS / f"a07-{browser_name}-{width}-{scheme}-{name}.png")  # noqa: E731
    banner = alert_banner(page)
    text = banner.locator("p").evaluate("el => getComputedStyle(el).color")
    fill = banner.evaluate("el => getComputedStyle(el).backgroundColor")
    assert contrast(text, fill) >= 4.5  # the banner reads in both modes
    assert no_sideways_scroll(page)
    shot("alert")
    banner.get_by_role("button", name="Explain it").click()
    chat = window(page)
    expect(chat.locator(".message.assistant")).to_have_count(1, timeout=10_000)
    if width == PHONE:  # the full-screen sheet: nothing to enlarge or pin
        expect(head_button(page, "Make larger")).to_be_hidden()
        expect(head_button(page, PIN)).to_be_hidden()
        shot("sheet")
        return
    head_button(page, "Make larger").click()
    c = box(chat)
    assert c["x"] >= 0 and c["x"] + c["width"] <= width and c["y"] >= 0 and c["y"] + c["height"] <= HEIGHT
    assert no_sideways_scroll(page)
    shot("enlarged")
    head_button(page, PIN).click()
    unpin = head_button(page, UNPIN)
    expect(unpin).to_be_visible()
    assert unpin.evaluate("el => getComputedStyle(el).color") == colour(page, "var(--accent)")
    assert contrast(unpin.evaluate("el => getComputedStyle(el).color"),
                    unpin.evaluate("el => getComputedStyle(el).backgroundColor")) >= 4.5
    assert no_sideways_scroll(page)
    shot("pinned")


# --- A07.10: keyboard and names (DESIGN.md §10) ------------------------------------------------------------------

def focused_name(page: Page) -> str:
    return page.evaluate("(() => { const a = document.activeElement; "
                         "return a.getAttribute('aria-label') || a.textContent.trim() })()")


def visible_focus(page: Page) -> bool:
    s = page.evaluate("(() => { const s = getComputedStyle(document.activeElement); "
                      "return [s.outlineStyle, s.outlineWidth] })()")
    return s[0] != "none" and float(s[1].rstrip("px")) >= 2


def test_a07_10_layout_controls_by_keyboard_with_names_and_visible_focus(open_app):
    page = open_app()
    page.keyboard.press("Control+k")
    expect(message_box(page)).to_be_focused()
    names = []
    for _ in range(6):  # back through the header
        page.keyboard.press("Shift+Tab")
        names.append(focused_name(page))
        if names[-1] == "Make larger":
            break
    assert names[-1] == "Make larger", names
    assert visible_focus(page)
    page.keyboard.press("Enter")
    expect(head_button(page, "Make smaller")).to_be_focused()  # focus stays on the button
    page.keyboard.press("Shift+Tab")
    assert focused_name(page) == PIN
    assert visible_focus(page)
    page.keyboard.press("Enter")
    expect(head_button(page, UNPIN)).to_be_focused()
    page.keyboard.press("Shift+Tab")  # New chat is disabled on an empty chat, so the divider comes next
    expect(divider(page)).to_be_focused()
    expect(divider(page)).to_have_attribute("aria-orientation", "vertical")
    page.keyboard.press("ArrowLeft")
    expect(divider(page)).to_have_attribute("aria-valuenow", "464")
    page.keyboard.press("Tab")
    page.keyboard.press("Enter")  # Unpin
    expect(head_button(page, PIN)).to_be_focused()
    page.keyboard.press("Escape")
    expect(window(page)).to_have_count(0)
    expect(fab(page)).to_be_focused()

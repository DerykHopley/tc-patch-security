"""Browser check (seam 3) for the Settings page. Check ids: A13.n, from ticket #15.

Runs in Firefox and Chromium against run.sh's throwaway servers. It never sends a real alert: it uses the preview
and channels that aren't set up (the backend starts without SMTP or ntfy settings), and never clicks the desktop
channel's test, which would pop up a real notification on a developer's machine.
Expected values come from docs/design/DESIGN.md §5.7, not from the CSS.
"""
import pathlib
import re

import pytest
from playwright.sync_api import Browser, Page, expect

SHOTS = pathlib.Path(__file__).parent / "screenshots"
PHONE, DESKTOP = 400, 1400


def patch_button_box(width: int, height: int = 900) -> dict:
    """Where Patch's button sits (DESIGN.md §6.1, §4.2): 84 x 66px, 1.25rem from the right; 1.25rem from the
    bottom on desktop, 5rem up on phones (above the tab bar)."""
    bottom = 80 if width <= 800 else 20
    return {"x": width - 20 - 84, "y": height - bottom - 66, "width": 84, "height": 66}


def overlaps(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"]
            and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"])


@pytest.fixture
def settings_page(browser: Browser, ui_url: str):
    """Opens the Settings page in a fresh context, after resetting the throwaway state through the page's API."""
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(ui_url)
        page.get_by_role("button", name="Settings", exact=True).click()
        expect(page.get_by_role("heading", name="Alerts", exact=True)).to_be_visible()
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


@pytest.fixture(autouse=True)
def fresh_state(browser: Browser, ui_url: str):
    """Each test starts from the defaults: reset through the page itself."""
    yield
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(ui_url)
    page.get_by_role("button", name="Settings", exact=True).click()
    page.get_by_label("Type reset to confirm").fill("reset")
    page.get_by_role("button", name="Reset demo data").click()
    expect(page.get_by_text("Reset to the defaults.")).to_be_visible()
    ctx.close()


def css_var(page: Page, name: str) -> str:
    return page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('{name}').trim()")


def style(locator, prop: str) -> str:
    return locator.evaluate(f"el => getComputedStyle(el).{prop}")


def resolved(page: Page, value: str, prop: str = "backgroundColor") -> str:
    """A CSS value as the browser computes it, for comparing against a token."""
    return page.evaluate(f"""(() => {{ const d = document.createElement('div'); d.style.cssText = 'position:absolute';
        d.style.{prop} = {value!r}; document.body.append(d); const v = getComputedStyle(d).{prop}; d.remove(); return v }})()""")


def panel(page: Page, title: str):
    return page.locator("section.card", has=page.get_by_role("heading", name=title, exact=True))


# --- A13.2: alert rules; each panel says live, saved for later, or mock -------------------------------------------

def test_a13_2_each_panel_says_whether_it_is_live_saved_for_later_or_a_mock(settings_page):
    page = settings_page()
    for title, chip in (("Alerts", "Saved for later"), ("Delivery", "Live"), ("Watchlist", "Live"), ("Data", "Live")):
        expect(panel(page, title).locator(".status-chip")).to_have_text(chip)
    check_now = page.get_by_role("button", name="Check for new CVEs now")
    expect(check_now).to_be_disabled()
    expect(panel(page, "Data")).to_contain_text("Not built yet")
    expect(page.get_by_role("heading", level=1)).to_have_text("Settings")
    expect(page.get_by_role("heading", name="Settings", level=2)).to_have_count(0)  # the top bar names the page


def test_a13_2_alert_rules_save_and_survive_a_reload(settings_page):
    page = settings_page()
    bar = page.locator(".save-bar").get_by_role("status")
    expect(bar).to_contain_text("All changes saved")
    page.get_by_label("Minimum severity").select_option("CRITICAL")
    page.get_by_label("Check for new CVEs every").select_option("12")
    page.get_by_label("Bundle into one digest above").fill("9")
    page.get_by_label("Quiet hours start").fill("22:00")
    page.get_by_label("Quiet hours end").fill("07:00")
    page.get_by_label("A new CVE has no severity yet").uncheck()
    expect(bar).to_contain_text("Unsaved changes")
    page.get_by_role("button", name="Save changes").click()
    expect(bar).to_have_text("✓ Changes saved")
    page.reload()
    page.get_by_role("button", name="Settings", exact=True).click()
    expect(page.get_by_label("Minimum severity")).to_have_value("CRITICAL")
    expect(page.get_by_label("Check for new CVEs every")).to_have_value("12")
    expect(page.get_by_label("Bundle into one digest above")).to_have_value("9")
    expect(page.get_by_label("Quiet hours start")).to_have_value("22:00")
    expect(page.get_by_label("A new CVE has no severity yet")).not_to_be_checked()


def test_a13_2_discard_brings_back_the_saved_values(settings_page):
    page = settings_page()
    page.get_by_label("Send alerts").uncheck()
    expect(page.get_by_label("A CVE on my watchlist is added to CISA KEV")).to_be_disabled()  # rules off with alerts
    page.get_by_role("button", name="Discard").click()
    expect(page.get_by_label("Send alerts")).to_be_checked()
    expect(page.get_by_role("button", name="Save changes")).to_be_disabled()


def test_a13_2_the_watchlist_card_edits_the_watchlist(settings_page):
    # Since A15b the card holds the editor; its checks are in test_watchlist.py.
    page = settings_page()
    card = page.get_by_role("region", name="Watchlist", exact=True)
    expect(card.get_by_role("checkbox", name="vLLM")).to_be_visible()
    expect(card.get_by_role("group", name="Langflow")).to_be_visible()
    expect(page.get_by_role("button", name="Edit on the dashboard")).to_have_count(0)


# --- A13.3: channels, test alerts, the log -------------------------------------------------------------------------

def test_a13_3_channels_show_whether_they_are_set_up_and_how(settings_page):
    page = settings_page()
    email = page.locator(".channel", has_text="Email")
    expect(email.locator(".setup-pill")).to_have_text("not set up")
    expect(email).to_contain_text("SMTP_HOST")
    ntfy = page.locator(".channel", has_text="Phone push (ntfy)")
    expect(ntfy.locator(".setup-pill")).to_have_text("not set up")
    expect(ntfy).to_contain_text("NTFY_TOPIC")
    expect(page.locator(".channel", has_text="Desktop notification").locator(".setup-pill")).to_have_text(
        re.compile("^(ready|not set up)$"))
    for name in ("Desktop notification", "Email", "Phone push (ntfy)"):
        expect(page.get_by_role("checkbox", name=name)).to_be_visible()


def test_a13_3_preview_shows_the_alert_and_logs_it(settings_page):
    page = settings_page()
    expect(page.get_by_text("No alerts yet.")).to_be_visible()
    page.get_by_role("button", name="Preview an alert (send nothing)").click()
    preview = page.locator(".push-preview")
    expect(preview).to_contain_text("Test · In CISA KEV: Langflow")
    # Your due date, worded as on the dashboard (review item 18)
    expect(preview).to_contain_text(re.compile(r" · (due|decide by) \d{4}-\d{2}-\d{2}"))
    expect(preview).not_to_contain_text("remediation")
    expect(preview).to_contain_text("nothing was sent")
    log = page.get_by_role("list", name="Recent alerts")
    expect(log.get_by_role("listitem")).to_have_count(1)
    expect(log).to_contain_text("preview")
    expect(log).to_contain_text("recorded only")


def test_a13_3_test_on_a_channel_that_is_not_set_up_says_so_and_is_logged(settings_page):
    page = settings_page()
    page.get_by_role("button", name="Send test alert by email").click()
    expect(page.get_by_role("alert")).to_contain_text("SMTP_HOST")
    log = page.get_by_role("list", name="Recent alerts")
    expect(log.get_by_role("listitem")).to_have_count(1)
    expect(log).to_contain_text("email")
    expect(log).to_contain_text("not set up")


# --- A13.5: reset ---------------------------------------------------------------------------------------------------

def test_a13_5_reset_needs_the_word_and_restores_the_defaults(settings_page):
    page = settings_page()
    page.get_by_label("Minimum severity").select_option("LOW")
    page.get_by_role("button", name="Save changes").click()
    page.get_by_role("button", name="Preview an alert (send nothing)").click()
    expect(page.get_by_role("list", name="Recent alerts").get_by_role("listitem")).to_have_count(1)
    reset = page.get_by_role("button", name="Reset demo data")
    expect(reset).to_be_disabled()
    page.get_by_label("Type reset to confirm").fill("Reset")
    expect(reset).to_be_disabled()
    page.get_by_label("Type reset to confirm").fill("reset")
    reset.click()
    expect(page.get_by_text("Reset to the defaults.")).to_be_visible()
    expect(page.get_by_label("Minimum severity")).to_have_value("HIGH")
    expect(page.get_by_text("No alerts yet.")).to_be_visible()
    expect(page.locator(".push-preview")).to_have_count(0)


# --- A13.6: fieldsets, channel cards, callouts, the save bar (DESIGN.md §5.7) -------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a13_6_settings_parts_as_designed(settings_page, scheme):
    page = settings_page(scheme=scheme)
    nested = resolved(page, css_var(page, "--nested-fill"))
    for fieldset in page.locator("fieldset").all():
        assert style(fieldset, "borderTopLeftRadius") == "18px"
        assert style(fieldset, "backgroundColor") == nested
        assert style(fieldset, "borderTopStyle") == "none"  # nested cards have no border
    channels = page.locator(".channel").all()
    assert len(channels) == 3
    for channel in channels:
        assert style(channel, "borderTopLeftRadius") == "18px"
        assert style(channel, "backgroundColor") == nested
        pill = channel.locator(".setup-pill").bounding_box()
        card = channel.bounding_box()
        assert pill and card and pill["width"] < 100 < card["width"]  # the pill hugs its text
    assert style(page.locator(".callout").first, "borderTopLeftRadius") == "14px"
    danger = page.locator(".danger-zone")
    assert style(danger, "borderTopLeftRadius") == "18px"
    assert style(danger, "borderTopColor") == resolved(page, css_var(page, "--error"), "color")
    for card in page.locator("section.card").all():
        assert style(card, "backgroundColor") == resolved(page, css_var(page, "--surface"))
        assert style(card, "borderTopLeftRadius") == "26px"


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_a13_6_save_bar_floats_at_the_bottom_clear_of_patch(settings_page, width):
    page = settings_page(width=width)
    bar = page.locator(".save-bar")
    assert style(bar, "position") == "sticky"
    assert style(bar, "borderTopLeftRadius") == "20px"
    assert "rgba(108, 76, 245, 0.16)" in style(bar, "boxShadow")
    page.get_by_label("Minimum severity").select_option("LOW")  # the bar shows wherever the page is scrolled
    page.evaluate("window.scrollTo(0, 0)")
    box = bar.bounding_box()
    assert box and box["y"] + box["height"] <= 900
    tab_bar = page.locator(".sidenav").bounding_box()
    if width == PHONE:
        assert tab_bar and box["y"] + box["height"] <= tab_bar["y"]  # above the tab bar, not behind it
    for name in ("Discard", "Save changes"):
        button = page.get_by_role("button", name=name).bounding_box()
        assert button and not overlaps(button, patch_button_box(width)), name  # never behind Patch
    message = page.locator(".save-bar output").bounding_box()
    assert message and not overlaps(message, patch_button_box(width))
    expect(bar).to_contain_text("Unsaved changes")


# --- A13.7: reduced motion --------------------------------------------------------------------------------------------

# Reduced motion: in the shared check, test_reduced_motion.py (scene a13_7).


# --- A13.8: light and dark, phone and desktop -------------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a13_8_works_in_both_themes_at_both_widths(settings_page, browser_name, width, scheme):
    page = settings_page(width=width, scheme=scheme, reduced=True)
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    cards = page.locator("section.card")
    expect(cards).to_have_count(6)  # with "Patch's answers" (A19) and "Priority and due dates" (A16)
    one_column = len({round(c.bounding_box()["x"]) for c in cards.all()}) == 1
    assert one_column == (width == PHONE)  # one column of cards at ≤ 900px (DESIGN.md §4.2)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a13-{browser_name}-{width}-{scheme}-settings.png", full_page=True)


# --- A13.9: keyboard and names ----------------------------------------------------------------------------------------

def test_a13_9_every_control_reachable_by_keyboard_with_visible_focus(settings_page):
    page = settings_page()
    page.get_by_label("Send alerts").focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")  # focus by keyboard, so :focus-visible applies
    seen = []
    for _ in range(40):
        seen.append(page.evaluate("""(() => { const a = document.activeElement;
            const label = a.labels && a.labels[0] ? a.labels[0].textContent : '';
            return (a.getAttribute('aria-label') || label || a.textContent || '').trim() })()"""))
        # Chromium's time input has its own clock button, focused inside the browser's shadow DOM: the input then
        # doesn't match :focus and the browser draws its own ring there. Every other stop must show ours.
        outline = page.evaluate("""(() => { const a = document.activeElement; const s = getComputedStyle(a);
            return [a.matches(':focus'), s.outlineStyle, s.outlineWidth] })()""")
        if outline[0]:
            assert outline[1] != "none" and float(outline[2].rstrip("px")) >= 2, seen[-1]
        page.keyboard.press("Tab")
    text = " | ".join(seen)
    for name in ("Send alerts", "Minimum severity", "Check for new CVEs every", "Quiet hours start",
                 "Send test alert by email", "Preview an alert", "Type reset to confirm"):
        assert name in text, (name, seen)


def test_a13_9_buttons_have_accessible_names(settings_page):
    page = settings_page()
    for name in ("Send test alert by desktop notification", "Send test alert by email",
                 "Send test alert by phone push (ntfy)", "Preview an alert (send nothing)",
                 "Check for new CVEs now", "Reset demo data", "Discard", "Save changes"):
        expect(page.get_by_role("button", name=name, exact=True)).to_have_count(1)
    unnamed = page.evaluate("""[...document.querySelectorAll('main button')].filter(b =>
        !(b.getAttribute('aria-label') || b.textContent).trim()).length""")
    assert unnamed == 0

"""Browser check for #144: the dashboard's Recent alerts card shows the last 5 real alerts, no test alerts and no
channel results; the full log (the last 20) is in Settings: Delivery for the owner, with each channel's result, and
the Alerts card for anyone else, without. Check ids: F144.n (an issue-only fix, no spec ticket).

The alerts log is the browser's: `/alerts` answers LOG, a mix of real alerts, test alerts and failed sends, newest
first. Another user is the browser told so (open_as, as test_settings_dev_polish.py B50.9 does). Expected looks:
docs/design/DESIGN.md §5.11. Screenshots go to screenshots/, untracked, for the owner's review.
"""
import re

import pytest
from playwright.sync_api import BrowserContext, Page, expect

from test_settings_dev_polish import card, open_as  # noqa: F401 (a fixture)
from test_settings_layout import as_rgb
from test_settings_over_env import server_defaults  # noqa: F401 (a fixture)
from test_shell import DESKTOP, PHONE, SHOTS, contrast, no_sideways_scroll, settled

SENT = {"channel": "ntfy", "sent": True, "error": None, "error_code": None}
FAILED = {"channel": "ntfy", "sent": False, "error": "429 Too Many Requests", "error_code": "notify_failed",
          "tries": 3, "retry": False}
DESKTOP_ONLY = {"channel": "desktop", "sent": False, "error": None, "error_code": None}


def alert(n: int, kind: str = "alert", channels=None, **over) -> dict:
    cve = f"CVE-2026-{10000 + n}"
    return {"at": f"2026-10-{22 - n // 2:02d}T{9 + n % 2:02d}:00:00+00:00", "kind": kind, "cve": cve,
            "reason": "kev", "title": f"In CISA KEV: Product {n}", "body": f"{cve} · critical 9.8", "priority": 5,
            "tags": [], "click": None, "alerts": [{"cve": cve, "reason": "kev", "priority": 5}],
            "channels": [SENT] if channels is None else channels, **over}


def a_test_alert(n: int, channels=None) -> dict:
    return alert(n, "test", channels=[DESKTOP_ONLY] if channels is None else channels, cve=None, reason=None,
                 title=f"Test · In CISA KEV: Langflow ({n})", alerts=[])


# 20 entries, newest first: test alerts on top (as on the live app), a failed send, a digest, then older alerts
LOG = [a_test_alert(0), a_test_alert(1, [FAILED]), alert(2, channels=[FAILED, DESKTOP_ONLY]), a_test_alert(3),
       alert(4, "digest", cve=None, reason=None, title="3 alerts for your watchlist", body="2 new · 1 in CISA KEV"),
       alert(5), a_test_alert(6), alert(7), alert(8), alert(9), *[alert(n) for n in range(10, 20)]]
REAL_TITLES = ["In CISA KEV: Product 2", "3 alerts for your watchlist", "In CISA KEV: Product 5",
               "In CISA KEV: Product 7", "In CISA KEV: Product 8"]
# Anyone else's: recorded in Patch only, no channels (B09), so their own test alerts are previews
THEIRS = [{**e, "channels": [], "in_app_only": True} for e in LOG]


def with_log(log: list[dict]):
    def setup(ctx: BrowserContext) -> None:
        ctx.route(re.compile(r".*/alerts$"), lambda route: route.fulfill(json={"alerts": log}))
    return setup


def recent(page: Page):
    return page.locator("section#recent-alerts")


def dashboard(open_as, who: str, log: list[dict], **kw) -> Page:  # noqa: F811
    page = open_as(who, path="/", setup=with_log(log), **kw)
    expect(recent(page).locator(".alert-log > li")).to_have_count(5)
    return page


def text_contrast(page: Page, el, on) -> float:
    fg = as_rgb(page, el.evaluate("e => getComputedStyle(e).color"))
    bg = as_rgb(page, on.evaluate("e => getComputedStyle(e).backgroundColor"))
    return contrast(fg, bg)


def shoot(locator, name: str) -> None:
    """The card once its entrance has finished, without the fixed parts over it (Patch's button, the phone's tab
    bar, the save bar)."""
    SHOTS.mkdir(exist_ok=True)
    settled(locator.page.locator("main"))
    locator.screenshot(path=SHOTS / f"f144-{name}.png",
                       style=".patch-fab, .sidenav, .save-bar { visibility: hidden !important; }")


# --- F144.5: the dashboard card: the last 5 real alerts, no test alerts, no channel results ------------------------

@pytest.mark.parametrize("who", ["owner", "viewer"])
def test_f144_5_the_dashboard_shows_the_last_five_real_alerts_without_pills(open_as, who):  # noqa: F811
    page = dashboard(open_as, who, LOG if who == "owner" else THEIRS)
    titles = [t.strip() for t in recent(page).locator(".alert-log > li > :first-child").all_inner_texts()]
    assert titles == REAL_TITLES
    expect(recent(page)).not_to_contain_text("Test alert")
    expect(recent(page).locator(".channel-results")).to_have_count(0)
    first = recent(page).locator(".alert-log > li").first
    expect(first.get_by_role("link", name="In CISA KEV: Product 2")).to_have_attribute("href", "/cves/CVE-2026-10002")
    expect(first).to_contain_text(re.compile(r"In CISA KEV · \d{4}-\d{2}-\d{2} \d{2}:\d{2} UTC"))
    expect(recent(page).locator(".alert-log > li").nth(1)).to_contain_text("2 new · 1 in CISA KEV")  # the digest


def test_f144_5_only_test_alerts_leave_the_card_empty(open_as):  # noqa: F811
    page = open_as(path="/", setup=with_log([a_test_alert(0), a_test_alert(1)]))
    expect(recent(page)).to_contain_text("No alerts yet. The snapshot never changes, so no check finds any. "
                                         "Test alerts show in Settings.")


# --- F144.6: the footer link, by role, by keyboard, to the card with the full log ---------------------------------

@pytest.mark.parametrize("who, words, anchor, heading", [
    ("owner", "Alerts and delivery in Settings", "delivery", "Alerts and delivery"),
    ("viewer", "All your alerts in Settings", "alerts", "Your alerts"),
])
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_f144_6_the_footer_link_opens_the_full_log_by_keyboard(open_as, who, words, anchor, heading,  # noqa: F811
                                                               width):
    page = dashboard(open_as, who, LOG if who == "owner" else THEIRS, width=width)
    link = recent(page).get_by_role("link", name=words)
    expect(link).to_have_attribute("href", f"/settings#{anchor}")
    link.focus()
    expect(link).to_be_focused()
    page.keyboard.press("Enter")
    expect(page).to_have_url(re.compile(rf"/settings#{anchor}$"))
    full = page.get_by_role("list", name=heading)
    expect(full.get_by_role("listitem")).to_have_count(5)  # the last 5 first; the rest behind "Show all 20" (F144.9)
    page.wait_for_function(f"() => {{ const r = document.getElementById('{anchor}')?.getBoundingClientRect();"
                           " return r && r.top >= 0 && r.top < 120 }")


# --- F144.7: Settings' full log: the owner's in Delivery with each channel's result; anyone else's without -------

def test_f144_7_delivery_lists_the_last_twenty_with_test_alerts_and_results(open_as):  # noqa: F811
    page = open_as(setup=with_log(LOG + [alert(20), alert(21)]))
    delivery = card(page, "Delivery")
    items = delivery.get_by_role("list", name="Alerts and delivery").get_by_role("listitem")
    expect(items).to_have_count(5)  # the first 5; the rest behind the toggle (F144.9)
    toggle = delivery.get_by_role("button", name="Show all 20")
    expect(toggle).to_have_attribute("aria-expanded", "false")
    toggle.focus()
    page.keyboard.press("Enter")
    expect(items).to_have_count(20)
    expect(delivery.get_by_role("button", name="Show the last 5")).to_be_focused()  # focus stays on the toggle
    expect(delivery.get_by_role("button", name="Show the last 5")).to_have_attribute("aria-expanded", "true")
    expect(items.first).to_contain_text("Test alert · ")
    expect(items.nth(1)).to_contain_text("ntfy: failed (3 tries)")
    expect(items.nth(2).locator(".channel-results .result")).to_have_text(["ntfy: failed (3 tries)",
                                                                          "desktop: recorded only"])
    expect(delivery).not_to_contain_text("on the dashboard")  # the old link to the dashboard's card is gone
    # The owner's own Alerts card has no list: their log is here
    expect(card(page, "Alerts").locator(".alert-log")).to_have_count(0)


def test_f144_7_anyone_elses_alerts_card_lists_their_last_twenty_without_results(open_as):  # noqa: F811
    page = open_as("viewer", setup=with_log(THEIRS))
    alerts = card(page, "Alerts")
    items = alerts.get_by_role("list", name="Your alerts").get_by_role("listitem")
    expect(items).to_have_count(5)
    alerts.get_by_role("button", name="Show all 20").click()
    expect(items).to_have_count(20)
    expect(items.first).to_contain_text("Test alert · ")  # their previews
    expect(alerts.locator(".channel-results")).to_have_count(0)
    expect(page.get_by_role("heading", name="Delivery", exact=True)).to_have_count(0)


# --- F144.8: both themes, both widths: contrast and no sideways scroll; screenshots for the owner -----------------

SIZES = [(PHONE, "light"), (PHONE, "dark"), (DESKTOP, "light"), (DESKTOP, "dark")]


@pytest.mark.parametrize("width, scheme", SIZES)
@pytest.mark.parametrize("who", ["owner", "viewer"])
def test_f144_8_the_dashboard_card_in_both_themes_and_widths(open_as, browser_name, who, width, scheme):  # noqa: F811
    page = dashboard(open_as, who, LOG if who == "owner" else THEIRS, width=width, scheme=scheme)
    panel = recent(page)
    for el in (panel.locator(".alert-log a").first, panel.locator(".alert-log .meta").first,
               panel.locator(".edit-link")):
        assert text_contrast(page, el, panel) >= 4.5
    assert no_sideways_scroll(page)
    shoot(panel, f"{browser_name}-dashboard-{who}-{scheme}-{width}")


@pytest.mark.parametrize("width, scheme", SIZES)
@pytest.mark.parametrize("who", ["owner", "viewer"])
def test_f144_8_settings_full_log_in_both_themes_and_widths(open_as, browser_name, who, width, scheme):  # noqa: F811
    page = open_as(who, setup=with_log(LOG if who == "owner" else THEIRS), width=width, scheme=scheme)
    box = card(page, "Delivery" if who == "owner" else "Alerts")
    log = box.locator(".alert-log")
    expect(log.locator("> li")).to_have_count(5)
    box.get_by_role("button", name="Show all 20").click()  # all 20, so every result tone is on the page
    checks = [box.locator(".alerts-show-all")]  # the toggle, now "Show the last 5"
    expect(log.locator("> li")).to_have_count(20)
    checks += [log.locator("a").first, log.locator(".meta").first]
    if who == "owner":
        checks += [log.locator(".result.error").first, log.locator(".result.muted").first, log.locator(".result.ok").first]
    for el in checks:
        fill = el.evaluate("e => getComputedStyle(e).backgroundColor")
        assert text_contrast(page, el, box if fill in ("rgba(0, 0, 0, 0)", "transparent") else el) >= 4.5
    assert no_sideways_scroll(page)
    shoot(box, f"{browser_name}-settings-{who}-{scheme}-{width}")

"""Browser check (seam 3) for the owner's server settings on Settings: live or snapshot, the quiet hours' time zone,
the alert link address and the channels' secrets. Check ids: B26.n, from #70.

The snapshot pair (sign-in off: the one local user is the owner) switches to live and back; the live pair starts with
DATA_MODE=live in its environment, so its switch shows "set in the server's environment". No real alert is sent:
run.sh sets NOTIFY_DRY_RUN=1, so a test by ntfy is recorded only. A reset of the demo data keeps the server settings,
so every test puts them back itself.
"""
import re

import pytest
from playwright.sync_api import Browser, Page, expect

from test_dashboard import api
from test_settings import panel
from test_shell import DESKTOP, PHONE, contrast, css_var, no_sideways_scroll
from reduced_motion import scene, still

TOPIC = "patch-e2e-topic-7c1d"  # a made-up topic: never reaches ntfy (NOTIFY_DRY_RUN)
CLEAR = {k: None for k in ("data_mode", "alert_tz", "app_url", "ntfy_url", "smtp_port", "smtp_starttls",
                           "ntfy_topic", "ntfy_token", "smtp_host", "smtp_user", "smtp_password", "alert_email_from",
                           "alert_email_to", "nvd_api_key")}


@pytest.fixture
def server_defaults(api_url: str):
    """The snapshot pair's server settings and demo data back to the defaults, before and after."""
    def reset():
        api(api_url, "/settings/server", "PUT", CLEAR)
        api(api_url, "/state/reset", "POST", {"confirm": "reset"})

    reset()
    yield api_url
    reset()


@pytest.fixture
def open_settings(browser: Browser, ui_url: str, server_defaults):
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False, zone="Asia/Tokyo", base=None) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, timezone_id=zone,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto((base or ui_url) + "/settings")
        expect(page.get_by_role("heading", name="Data", exact=True)).to_be_visible()
        expect(page.get_by_text("All changes saved")).to_be_visible()  # loaded, and nothing is dirty on arrival
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def save(page: Page) -> None:
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_text("✓ Changes saved")).to_be_visible()


def delivery(page: Page):
    return panel(page, "Delivery")


# --- B26.9: live or snapshot, switched on the Data card ---------------------------------------------------------

def test_b26_9_the_owner_switches_to_live_data_and_back_with_no_restart(open_settings, api_url):
    page = open_settings()
    data = panel(page, "Data")
    expect(data.get_by_label("Snapshot")).to_be_checked()
    data.get_by_label("Live").check()
    save(page)
    expect(page.locator(".side-card strong")).to_have_text("Live data")  # the app's status follows
    expect(data.get_by_text("Live data from NVD, CISA KEV, EPSS and OSV")).to_be_visible()
    assert api(api_url, "/health")["mode"] == "live"

    page.get_by_role("button", name="Dashboard", exact=True).click()
    expect(page.get_by_role("button", name="Check now")).to_be_visible()  # the freshness card follows the switch

    page.get_by_role("button", name="Settings", exact=True).click()
    panel(page, "Data").get_by_label("Snapshot").check()
    save(page)
    expect(page.locator(".side-card strong")).to_have_text("Snapshot")
    assert api(api_url, "/health")["mode"] == "snapshot"


def test_b26_9_a_setting_from_the_environment_is_shown_and_cant_be_changed(open_settings, live_ui_url):
    page = open_settings(base=live_ui_url)  # the live pair: DATA_MODE=live in its environment
    data = panel(page, "Data")
    expect(data.get_by_label("Live")).to_be_checked()
    expect(data.get_by_label("Live")).to_be_disabled()
    expect(data.get_by_text("Set in the server's environment (DATA_MODE), which wins.")).to_be_visible()


# --- B26.10: secrets are write-only; the tap link says what it does ------------------------------------------------

def test_b26_10_a_secret_is_saved_never_shown_and_can_be_removed(open_settings, api_url):
    page = open_settings()
    d = delivery(page)
    topic = d.get_by_label("Topic", exact=True)
    expect(topic).to_have_attribute("type", "password")
    expect(d.get_by_text("Not set.").first).to_be_visible()
    topic.fill(TOPIC)
    expect(page.get_by_text("Unsaved changes")).to_be_visible()
    save(page)
    expect(topic).to_have_value("")  # never shown back
    expect(d.locator("#srv-ntfy_topic-state")).to_have_text("Saved. Type a new one to replace it.")
    expect(d.locator(".channel").filter(has_text="Phone push").locator(".setup-pill")).to_have_text("ready")
    assert TOPIC not in page.content()
    assert api(api_url, "/settings")["server"]["secrets"]["ntfy_topic"] == {"set": True, "source": "saved"}

    d.get_by_role("button", name="Remove the saved topic").click()
    expect(d.locator("#srv-ntfy_topic-state")).to_have_text("Removed when you save.")
    save(page)
    expect(d.locator("#srv-ntfy_topic-state")).to_have_text("Not set.")
    expect(d.locator(".channel").filter(has_text="Phone push").locator(".setup-pill")).to_have_text("not set up")


def test_b26_10_a_test_alert_says_whether_tapping_it_opens_patch(open_settings):
    page = open_settings()
    d = delivery(page)
    d.get_by_label("Topic", exact=True).fill(TOPIC)
    save(page)
    address = d.get_by_label("App address for alert links")
    expect(address).to_have_value("http://localhost:5173")
    expect(d.locator(".tap-line")).to_contain_text("A phone can't open this address")
    d.get_by_role("button", name="Send test alert by phone push (ntfy)").click()
    expect(page.get_by_test_id("tap-line")).to_contain_text("opens the message in the ntfy app")

    address.fill("http://192.168.1.20:5173")
    expect(d.locator(".tap-line")).to_contain_text("tapping an alert opens Patch at the CVE")
    save(page)
    d.get_by_role("button", name="Send test alert by phone push (ntfy)").click()
    expect(page.get_by_test_id("tap-line")).to_have_text(re.compile(r"^Tapping it opens Patch at CVE-\d{4}-\d+\.$"))


# --- B26.11: the quiet hours' time zone ------------------------------------------------------------------------------

def test_b26_11_the_time_zone_starts_as_the_browsers_and_is_saved_with_the_quiet_hours(open_settings, api_url):
    page = open_settings(zone="Asia/Tokyo")
    alerts = panel(page, "Alerts")
    expect(alerts.get_by_label("Quiet hours are in")).to_have_value("Asia/Tokyo")
    expect(alerts.get_by_text("Your browser's time zone. Saved with your quiet hours")).to_be_visible()
    alerts.get_by_label("Quiet hours start").fill("22:00")
    alerts.get_by_label("Quiet hours end").fill("07:00")
    save(page)
    body = api(api_url, "/settings")
    assert body["alert_tz"] == "Asia/Tokyo" and body["server"]["fields"]["alert_tz"]["source"] == "saved"
    expect(alerts.get_by_text("Alerts found in quiet hours are held")).to_be_visible()
    # the page shows what was saved: the settings' save after the server's keeps the server's new state
    expect(alerts.get_by_label("Quiet hours are in")).to_have_value("Asia/Tokyo")
    expect(page.get_by_text("✓ Changes saved")).to_be_visible()

    alerts.get_by_label("Quiet hours are in").select_option("Europe/London")
    save(page)
    assert api(api_url, "/settings")["alert_tz"] == "Europe/London"


# --- B26.12: light and dark, phone width, keyboard ------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b26_12_the_new_fields_fit_a_phone_and_their_notes_pass_contrast(open_settings, scheme):
    page = open_settings(width=PHONE, scheme=scheme)
    d = delivery(page)
    for label in ("App address for alert links", "Topic", "SMTP server", "Password"):
        box = d.get_by_label(label, exact=True).bounding_box()
        card = d.bounding_box()
        assert box and card and box["x"] >= card["x"] and box["x"] + box["width"] <= card["x"] + card["width"], label
    assert no_sideways_scroll(page)
    tap = d.locator(".tap-line")
    colour = tap.evaluate("el => getComputedStyle(el).color")
    surface = page.evaluate("getComputedStyle(document.querySelector('.settings-card')).backgroundColor")
    assert contrast(colour, surface) >= 4.5  # --text with the warn colour as an edge (§5.7)
    assert css_var(page, "--warn") != ""


def test_b26_12_secrets_by_keyboard(open_settings):
    page = open_settings()
    d = delivery(page)
    d.get_by_label("Topic", exact=True).focus()
    page.keyboard.type(TOPIC)
    page.keyboard.press("Tab")  # to the token's box: Remove only shows for a saved secret
    expect(d.get_by_label("Access token (optional)")).to_be_focused()
    save(page)
    remove = d.get_by_role("button", name="Remove the saved topic")
    remove.focus()
    page.keyboard.press("Enter")
    expect(d.get_by_role("button", name="Keep the saved topic")).to_be_visible()
    d.get_by_role("button", name="Keep the saved topic").focus()
    page.keyboard.press("Enter")
    expect(d.locator("#srv-ntfy_topic-state")).to_have_text("Saved. Type a new one to replace it.")


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) ------------------------------------

@scene
def b26_13_server_settings(fx):
    api_url = fx("api_url")
    try:
        page = fx("open_settings")(reduced=True)
        d = delivery(page)
        d.get_by_label("Topic", exact=True).fill(TOPIC)
        d.get_by_label("App address for alert links").fill("http://192.168.1.20:5173")
        still(page, "the server settings, edited")
        save(page)
        d.get_by_role("button", name="Remove the saved topic").click()
        still(page, "a saved secret to be removed")
    finally:
        api(api_url, "/settings/server", "PUT", CLEAR)

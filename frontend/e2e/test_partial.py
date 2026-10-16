"""Browser check for partial success and retry (B20, #57). Check ids: B20.n.

The partial refresh runs on the live pair (fake feeds, NVD switched to fail by the fake-only route); the failed tool
card on the snapshot pair (search_security switched to fail by the dev panel's route). Each test switches its
failure off again. Expected looks: docs/design/DESIGN.md §5.10 (the banner) and §6.2 (the tool card).
"""
import re

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from test_chat import ask, open_chat, window
from test_dashboard import api
from test_live import SHOTS, card, line, live_reset, open_live  # noqa: F401 (fixtures)
from test_settings import panel, settings_page  # noqa: F401 (fixture)
from test_shell import DESKTOP, PHONE, contrast, no_sideways_scroll, open_app  # noqa: F401 (fixture)
from reduced_motion import scene, still

PARTIAL_Q = "Is CVE-2025-3248 in CISA KEV, and how do I defend against code injection?"
BANNER = re.compile(r"^3 of 4 sources updated at \d\d:\d\d UTC · NVD didn't answer · next try \d\d:\d\d UTC$")


@pytest.fixture
def nvd_down(live_api_url: str, live_reset):  # noqa: F811
    api(live_api_url, "/refresh/fake-feeds", "POST", {"fail": ["nvd"]})
    yield
    api(live_api_url, "/refresh/fake-feeds", "POST", {"fail": []})


@pytest.fixture
def search_down(api_url: str):
    api(api_url, "/dev/fail-tools", "POST", {"tools": ["search_security"]})
    yield
    api(api_url, "/dev/fail-tools", "POST", {"tools": []})


# A computed colour as rgb(): Firefox gives color-mix() fills (the tool card's --nested-fill) as color(srgb …), which
# test_shell.contrast can't read. A canvas pixel is rgb in every browser.
TEXT_AND_FILL = """(el, fillOf) => {
  const rgb = (c) => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c;
    x.fillRect(0, 0, 1, 1); const [r, g, b] = x.getImageData(0, 0, 1, 1).data; return `rgb(${r}, ${g}, ${b})` };
  const fill = fillOf ? el.closest(fillOf) : el;
  return [rgb(getComputedStyle(el).color), rgb(getComputedStyle(fill).backgroundColor)] }"""


def text_contrast(el: Locator, fill_of: str | None = None) -> float:
    return contrast(*el.evaluate(TEXT_AND_FILL, fill_of))


def banner(page: Page) -> Locator:
    return card(page).locator(".run-banner")


def partial_check(page: Page) -> None:
    """Check now with NVD down: the line says it was done in part, the banner says what didn't answer."""
    card(page).get_by_role("button", name="Check now").click()
    expect(line(page)).to_contain_text("Done in part:")
    expect(banner(page).locator(".run-banner-text")).to_have_text(BANNER)


def failed_card(page: Page) -> Locator:
    answer = ask(page, PARTIAL_Q)
    expect(answer).to_contain_text("didn't finish: search_security")
    answer.get_by_role("button", name=re.compile("Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    return answer.locator(".tool-card").nth(1)


# --- B20.11: the partial banner and Retry on the dashboard ---------------------------------------------------------

def test_b20_11_a_partial_check_shows_what_updated_what_didnt_and_retry(open_live, nvd_down):  # noqa: F811
    page = open_live()
    expect(banner(page)).to_have_count(0)  # never checked: no banner
    partial_check(page)
    expect(banner(page)).to_contain_text("NVD: The fake nvd feed is set to fail.")
    expect(card(page)).to_contain_text("Not checked in full yet")  # last checked moves only when every feed answered

    page.reload()  # the banner comes from the last run, not just this page's click
    expect(banner(page).locator(".run-banner-text")).to_have_text(BANNER)
    banner(page).get_by_role("button", name="Retry").click()  # within 5 minutes: the server refuses, and says when
    expect(line(page)).to_contain_text("Checked less than 5 minutes ago. The next check is allowed at")


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b20_11_the_banner_in_both_themes_on_a_phone_and_by_keyboard(open_live, nvd_down, scheme, width):  # noqa: F811
    page = open_live(width=width, scheme=scheme)
    partial_check(page)
    assert text_contrast(banner(page).locator(".run-banner-text"), ".run-banner") >= 4.5
    edge = banner(page).evaluate("el => getComputedStyle(el).borderLeftWidth")
    assert edge == "3px", edge
    retry = banner(page).get_by_role("button", name="Retry")
    retry.focus()
    page.keyboard.press("Enter")
    expect(line(page)).to_contain_text("Checked less than 5 minutes ago")
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    card(page).screenshot(path=SHOTS / f"b20-partial-{scheme}-{width}.png")


# --- B20.12: a tool that fails mid-answer: the card says so, and Try again runs only that step --------------------

def test_b20_12_the_failed_step_is_marked_and_try_again_runs_it(open_app, search_down):  # noqa: F811
    page = open_app()
    open_chat(page)
    tool = failed_card(page)
    expect(tool.locator(".status")).to_have_text("Didn't finish")
    expect(tool.locator(".tool-error")).to_have_text("didn't finish: search_security timed out before it answered.")
    first = page.locator(".tool-card").first
    expect(first.locator(".status")).to_have_text("OK")  # the lookup that worked keeps its result
    expect(first.locator(".cve-card")).to_contain_text("CVE-2025-3248")

    tool.get_by_role("button", name="Try again").click()
    expect(tool.locator(".status")).to_have_text("OK on retry")
    expect(tool.locator(".retry-note")).to_contain_text("The answer above was written without it")
    expect(tool.get_by_role("button", name="Try again")).to_have_count(0)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b20_12_the_failed_card_in_both_themes_on_a_phone_and_by_keyboard(open_app, search_down, scheme, width):  # noqa: F811
    page = open_app(width=width, scheme=scheme)
    open_chat(page)
    tool = failed_card(page)
    assert text_contrast(tool.locator(".tool-error"), ".tool-card") >= 4.5
    tool.get_by_role("button", name="Try again").focus()
    page.keyboard.press("Enter")
    note = tool.locator(".retry-note")
    expect(note).to_be_visible()
    assert text_contrast(note) >= 4.5
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    tool.screenshot(path=SHOTS / f"b20-tool-card-{scheme}-{width}.png")


# --- B20.13: your work is kept when a send or a save fails --------------------------------------------------------

def test_b20_13_a_failed_send_puts_the_message_back_in_the_box(open_app):  # noqa: F811
    page = open_app()
    open_chat(page)
    page.route("**/chat", lambda route: route.fulfill(status=500, json={"error": {"code": "internal_error",
                                                                                   "message": "Server down."}}))
    box = window(page).get_by_role("textbox", name="Message")
    box.fill("What is prompt injection?")
    box.press("Enter")
    expect(window(page).locator(".message.error")).to_contain_text("Server down.")
    expect(box).to_have_value("What is prompt injection?")
    page.unroute("**/chat")


@pytest.fixture
def state_reset(api_url: str):
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


def test_b20_13_a_failed_save_keeps_the_edits_and_shows_the_error_in_the_card(settings_page, state_reset):  # noqa: F811
    page = settings_page()

    def fail(route: Route) -> None:
        if route.request.method == "PUT":
            route.fulfill(status=500, json={"error": {"code": "internal_error", "message": "Server down."}})
        else:
            route.continue_()

    page.route("**/settings", fail)
    answers = panel(page, "Patch's answers")
    answers.get_by_role("radio", name="Simple").check()
    page.get_by_role("button", name="Save changes").click()
    expect(answers.get_by_role("alert")).to_have_text(
        "Not saved: Server down. Your changes are still here; Save changes tries again.")
    expect(answers.get_by_role("radio", name="Simple")).to_be_checked()
    expect(panel(page, "Alerts").get_by_role("alert")).to_have_count(0)  # only the card with unsaved edits

    page.unroute("**/settings")
    page.get_by_role("button", name="Save changes").click()
    expect(answers.get_by_role("alert")).to_have_count(0)
    expect(page.locator(".save-message")).to_have_text("✓ Changes saved")


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def b20_14_partial_and_try_again(fx):
    fx("nvd_down")
    page = fx("open_live")(reduced=True)
    partial_check(page)
    still(page, "the partial banner")
    fx("search_down")
    page = fx("open_app")(reduced=True)
    open_chat(page)
    tool = failed_card(page)
    still(page, "the failed tool card")
    tool.get_by_role("button", name="Try again").click()
    expect(tool.locator(".retry-note")).to_be_visible()
    still(page, "the step done on retry")

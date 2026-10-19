"""Browser check (seam 4): a person who isn't approved sees nothing of the app (B46, #81). Check ids: B46.n.

The owner's report (2026-10-19): a second account, approved, then removed, asked again, refused; on Check again it
saw the app's shell with empty pages. The owner's rule: anyone not approved (none, waiting, refused, removed) sees
no shell, no navigation, no page names; only their access card and the landing page's content.

As in test_access.py, the browser answers `/access` (`FakeAccess`); `not_approved` routes a 403 for every other API
route, as the backend answers once the owner removes or refuses someone (backend/tests/test_access.py B46.1).
"""
import json
import re

from playwright.sync_api import BrowserContext, Page, expect

from test_access import NEW, PHONE, FakeAccess, fits, heading, open_as  # noqa: F401 (open_as: a fixture)
from test_shell import no_sideways_scroll, settled

APPROVED = {**NEW, "status": "approved"}


def not_approved(ctx: BrowserContext, api_url: str, status: str) -> None:
    """Every API route but /access and /health answers 403 not_approved, as the backend does after a removal or a
    refusal."""
    body = json.dumps({"error": {"code": "not_approved", "status": status,
                                 "message": "Ask the owner for access first: Patch opens once they approve you."}})
    pattern = re.compile(re.escape(api_url) + r"/(?!access|health)[^?]*(\?.*)?$")
    ctx.route(pattern, lambda route: route.fulfill(status=403, content_type="application/json", body=body))


def none_of_the_app(page: Page) -> None:
    expect(page.get_by_role("navigation")).to_have_count(0)
    expect(page.locator("aside, .topbar, .main-col")).to_have_count(0)
    for name in ("Dashboard", "CVEs", "Settings", "Dev"):
        expect(page.get_by_text(name, exact=True)).to_have_count(0)


def go_to_cves(page: Page) -> None:
    """Opens CVEs, so the app makes a call. In the page, not Playwright's click: one of the app's own calls may get
    the 403 first and take the shell away, and then there's nothing left to click."""
    page.evaluate("[...document.querySelectorAll('aside nav button')].find(b => b.textContent.startsWith('CVEs'))"
                  "?.click()")


# --- B46.1: an open tab whose approval goes (removed, refused) leaves the app at once ------------------------------

def test_b46_1_a_403_not_approved_swaps_the_shell_for_the_access_card(open_as, api_url):
    fake = FakeAccess(APPROVED)
    page = open_as(fake)
    expect(heading(page, "Dashboard")).to_be_visible()
    # the owner refuses the person while their tab shows the app; the next call the app makes gets the 403
    # B49's chat kept for the tab (chatStore.ts): it must not outlive their access either
    page.evaluate("sessionStorage.setItem('chat', JSON.stringify({user: 'local', messages: [{role: 'user', "
                  "content: 'Am I affected?'}]}))")
    fake.me = {**fake.me, "status": "refused"}
    not_approved(page.context, api_url, "refused")
    go_to_cves(page)
    expect(heading(page, "Your request wasn't approved")).to_be_visible()
    none_of_the_app(page)
    assert page.evaluate("sessionStorage.getItem('chat')") is None


def test_b46_1_removed_shows_the_ask_screen(open_as, api_url):
    fake = FakeAccess(APPROVED)
    page = open_as(fake)
    expect(heading(page, "Dashboard")).to_be_visible()
    fake.me = {**NEW}
    not_approved(page.context, api_url, "none")
    go_to_cves(page)
    expect(heading(page, "Ask to join Patch")).to_be_visible()
    none_of_the_app(page)


def test_b46_1_a_role_refusal_keeps_the_app(open_as, api_url):
    """B45's 403 `not_allowed` (a Viewer on a Dev route) is about one route, not access: the app stays."""
    page = open_as(FakeAccess(APPROVED))
    expect(heading(page, "Dashboard")).to_be_visible()
    body = json.dumps({"error": {"code": "not_allowed", "message": "Your role can't use this."}})
    page.context.route(re.compile(re.escape(api_url) + r"/(?!access|health)[^?]*(\?.*)?$"),
                       lambda route: route.fulfill(status=403, content_type="application/json", body=body))
    go_to_cves(page)
    expect(heading(page, "CVEs")).to_be_visible()
    expect(page.locator("aside nav")).to_be_visible()


# --- B46.2: coming back to the tab asks /access again -------------------------------------------------------------

def test_b46_2_back_to_the_tab_checks_access_again(open_as):
    fake = FakeAccess(APPROVED)
    page = open_as(fake)
    expect(heading(page, "Dashboard")).to_be_visible()
    fake.me = {**fake.me, "status": "refused"}  # no API call from the page: only coming back can tell
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    expect(heading(page, "Your request wasn't approved")).to_be_visible()
    none_of_the_app(page)


def test_b46_2_the_waiting_screen_checks_again_when_the_tab_comes_back(open_as):
    fake = FakeAccess({**NEW, "status": "waiting"})
    page = open_as(fake)
    expect(heading(page, "Your request is waiting for the owner")).to_be_visible()
    fake.me = {**fake.me, "status": "refused"}
    page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")
    expect(heading(page, "Your request wasn't approved")).to_be_visible()


# --- B46.3: the access screens show the landing page's content, never the app's -----------------------------------

def test_b46_3_what_is_patch_opens_the_landing_content_and_comes_back(open_as):
    fake = FakeAccess({**NEW, "status": "waiting", "note": "hi"})
    page = open_as(fake)
    expect(heading(page, "Your request is waiting for the owner")).to_be_visible()
    page.get_by_role("link", name="What is Patch?").click()
    expect(page).to_have_url(re.compile(r"/about$"))
    expect(heading(page, "Security flaws in your LLM stack, tracked for you")).to_be_visible()
    expect(page.get_by_role("link", name="Sign in")).to_have_count(0)  # signed in already
    none_of_the_app(page)
    page.get_by_role("link", name="Back to your request").first.click()
    expect(heading(page, "Your request is waiting for the owner")).to_be_visible()
    page.go_back()
    expect(heading(page, "Security flaws in your LLM stack, tracked for you")).to_be_visible()


def test_b46_3_any_app_address_shows_the_access_card(open_as):
    page = open_as(FakeAccess({**NEW, "status": "refused"}), path="/settings")
    expect(heading(page, "Your request wasn't approved")).to_be_visible()
    none_of_the_app(page)


def test_b46_3_the_link_and_the_page_fit_a_phone_in_dark_by_keyboard(open_as):
    page = open_as(FakeAccess({**NEW, "status": "refused"}), width=PHONE, scheme="dark")
    link = page.get_by_role("link", name="What is Patch?")
    expect(link).to_be_visible()
    settled(page.locator(".signin-card"))
    fits(page, PHONE, "refused, with the link")
    link.focus()
    page.keyboard.press("Enter")
    expect(heading(page, "Security flaws in your LLM stack, tracked for you")).to_be_visible()
    assert no_sideways_scroll(page)
    none_of_the_app(page)

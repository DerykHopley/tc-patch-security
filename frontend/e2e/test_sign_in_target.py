"""Browser check for sign-in keeping where you were going (B60, #107). Check ids: B60.n.

A signed-out visitor opens an in-app address (an alert's `/cves/<id>`): the landing page, then the sign-in form, and
after sign-in the app opens that address, not the dashboard.

How it's driven, without Clerk: signed out is test_sign_in.py's `open_signed_out` setup (sign-in on, a made-up key,
Clerk unreachable). "Signed in" is the next page load with /health saying sign-in is off, so the app opens as it does
for a signed-in person. That load is at `/`, where Clerk lands after sign-in without a target (its fallback), or at
the form's address, where the app can start once signed in. So this checks Patch's half: the target kept per tab
across page loads (Clerk's SSO round trip leaves the page), followed once, then forgotten. Clerk's half (its form
going to the target itself, `forceRedirectUrl`) is checked in Clerk's code (docs/SOURCE-CHECKS.md, Clerk B60) and by
the owner on a real sign-in (#107).
"""
import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from test_landing import DESKTOP, PHONE, TITLE  # 390 and 1440, as the ticket asks
from test_shell import no_sideways_scroll
from test_sign_in import LOCAL, _signed_in_health

CVE = "CVE-2025-3248"
TARGET_KEY = "signInTarget"


class Visit:
    """One tab: signed out until `sign_in()`, then the app as a signed-in person sees it."""

    def __init__(self, ctx: BrowserContext, ui_url: str):
        self.ctx, self.ui_url, self.signed_in = ctx, ui_url, False
        self.page: Page = ctx.new_page()

    def health(self, route: Route) -> None:
        route.continue_() if self.signed_in else _signed_in_health(route)

    def open(self, path: str, heading: str = TITLE) -> Page:
        self.page.goto(self.ui_url + path)
        expect(self.page.get_by_role("heading", level=1, name=heading)).to_be_visible()
        return self.page

    def target(self) -> str | None:
        return self.page.evaluate(f"sessionStorage.getItem('{TARGET_KEY}')")

    def sign_in(self, lands_at: str = "/") -> Page:
        """Signed in: the next load is where Clerk lands without a target."""
        self.signed_in = True
        self.page.goto(self.ui_url + lands_at)
        return self.page


@pytest.fixture
def visit(browser: Browser, ui_url: str, api_url: str):
    contexts: list[BrowserContext] = []

    def _visit(width: int = DESKTOP) -> Visit:
        ctx = browser.new_context(viewport={"width": width, "height": 900})
        contexts.append(ctx)
        ctx.route(lambda url: not LOCAL.match(url), lambda route: route.abort())  # no network: Clerk can't load
        v = Visit(ctx, ui_url)
        ctx.route(f"{api_url}/health", v.health)
        return v

    yield _visit
    for ctx in contexts:
        ctx.close()


def on_cve_page(page: Page) -> None:
    expect(page.get_by_role("heading", level=1)).to_have_text(CVE)
    expect(page.get_by_role("region", name="Your assessment")).to_be_visible()
    assert page.evaluate("location.pathname") == f"/cves/{CVE}"


# --- B60.7: an alert's link, signed out: landing page, sign-in form, then the CVE page ------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b60_7_after_sign_in_an_alert_link_opens_its_cve_not_the_dashboard(visit, width):
    v = visit(width)
    page = v.open(f"/cves/{CVE}")  # the landing page, at the alert's address
    assert v.target() == f"/cves/{CVE}"
    page.get_by_role("link", name="Sign in", exact=True).first.click()
    expect(page.get_by_role("heading", level=1, name="Sign in to Patch")).to_be_visible()
    assert v.target() == f"/cves/{CVE}"  # the landing page's button keeps it
    page = v.sign_in()
    on_cve_page(page)
    assert no_sideways_scroll(page)
    assert v.target() is None  # used once
    page.reload()
    on_cve_page(page)  # a reload stays: nothing left to follow


def test_b60_7_the_target_survives_a_page_load_on_the_way(visit):
    """Clerk's SSO round trip leaves Patch and comes back to the form's address: the target is still there, and the
    app may start signed in at the form's address."""
    v = visit()
    v.open(f"/cves/{CVE}")
    v.open("/sign-in#/sso-callback", heading="Sign in to Patch")  # back from the provider: a fresh page load
    assert v.target() == f"/cves/{CVE}"
    on_cve_page(v.sign_in(lands_at="/sign-in"))


def test_b60_7_request_access_keeps_the_requests_card(visit):
    """The access-request alert links to Settings' Requests card; a sign-up (then approval) opens it there."""
    v = visit()
    page = v.open("/settings#requests")
    page.get_by_role("link", name="Request access").first.click()
    expect(page.get_by_role("heading", level=1, name="Request access to Patch")).to_be_visible()
    page = v.sign_in()
    expect(page.get_by_role("heading", level=1, name="Settings")).to_be_visible()
    assert page.evaluate("location.pathname + location.hash") == "/settings#requests"


# --- B60.8: no target: the dashboard, as before ---------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b60_8_without_a_target_sign_in_opens_the_dashboard(visit, width):
    v = visit(width)
    page = v.open("/")
    assert v.target() is None
    page.get_by_role("link", name="Sign in", exact=True).first.click()
    expect(page.get_by_role("heading", level=1, name="Sign in to Patch")).to_be_visible()
    page = v.sign_in()
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()
    assert page.evaluate("location.pathname") == "/"
    assert no_sideways_scroll(page)


def test_b60_8_coming_to_the_front_page_forgets_an_older_target(visit):
    v = visit()
    v.open(f"/cves/{CVE}")
    v.open("/")  # the visitor went on to Patch's own address
    assert v.target() is None
    expect(v.sign_in().get_by_role("heading", level=1, name="Dashboard")).to_be_visible()


def test_b60_8_an_unknown_address_is_not_kept(visit):
    v = visit()
    v.open("/nope")
    assert v.target() is None


# --- B60.9: a planted target that would leave Patch is never followed ----------------------------------------------

@pytest.mark.parametrize("planted", ["https://evil.example/", "//evil.example", "/\\evil.example",
                                     "javascript:alert(1)"])
def test_b60_9_a_target_that_leaves_patch_is_never_followed(visit, planted):
    v = visit()
    v.ctx.add_init_script(f"try {{ sessionStorage.setItem('{TARGET_KEY}', {planted!r}) }} catch {{}}")
    page = v.sign_in()
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()
    assert page.evaluate("location.origin + location.pathname") == v.ui_url + "/"

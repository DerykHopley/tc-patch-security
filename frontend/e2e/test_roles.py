"""Browser check (seam 4) for roles: Viewer, Trusted and Reviewer, set by the owner (B45, #90). Check ids: B45.n.

The pairs run.sh starts have sign-in off (the browser is the owner), so, as test_access.py does, these checks answer
`/access` and `/access/requests` in the browser (FakeAccess), and give `/dev/settings` the role the server would give
a reviewer. Every other route is the real throwaway backend. What each role may do on the server (403s, the
reviewer's own copy) is checked by backend/tests/test_roles.py. Expected looks come from DESIGN.md §5.6.4 and §5.7.
"""
import re

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from reduced_motion import scene, still
from test_access import DESKTOP, OWNER, PHONE, SIZES, FakeAccess, person, requests_card, show_details
from test_shell import SHOTS, contrast, no_sideways_scroll

REVIEWER_NOTE = ("Your settings apply only to you: your chat and the playground use them, everyone else keeps the "
                 "owner's.")


def as_role(role: str) -> dict:
    return {**OWNER, "owner": False, "role": role}


class FakeReviewer:
    """GET /dev/settings as the server answers a reviewer (`own_copy` as given); POST /dev/settings/owners drops the
    copy. The settings themselves are the real backend's."""

    def __init__(self, own_copy: bool):
        self.own_copy = own_copy
        self.sent: list[str] = []

    def route(self, ctx: BrowserContext, api_url: str) -> None:
        ctx.route(re.compile(re.escape(api_url) + r"/dev/settings(/owners)?$"), self.answer)

    def answer(self, route: Route) -> None:
        req = route.request
        if req.method == "POST" and req.url.endswith("/owners"):
            self.sent.append("owners")
            self.own_copy = False
        elif req.method != "GET":
            return route.continue_()
        real = route.fetch(url=req.url.removesuffix("/owners"), method="GET")
        route.fulfill(response=real, json=real.json() | {"role": "reviewer", "yours": True, "own_copy": self.own_copy})


@pytest.fixture
def open_role(browser: Browser, ui_url: str, api_url: str):
    """Opens Patch at `path` as `me` (FakeAccess), with `dev` answering the Dev settings when given."""
    contexts: list[BrowserContext] = []

    def _open(fake: FakeAccess, dev: FakeReviewer | None = None, width=DESKTOP, scheme="light", reduced=False,
              path="/") -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        fake.route(ctx, api_url)
        if dev:
            dev.route(ctx, api_url)
        page = ctx.new_page()
        page.goto(ui_url + path)
        page.evaluate("document.fonts.ready.then(() => null)")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def people() -> list[dict]:
    return [person("user_alice", "waiting", "Alice Example"),
            person("user_bob", "approved", "Bob", by="user_owner", role="trusted")]


def text_on_fill(loc) -> tuple[str, str]:
    """The element's text colour and the first opaque background behind it, as rgb(): Firefox gives color-mix()
    fills (--nested-fill) as color(srgb …), which test_shell.contrast can't read (as test_partial.py does)."""
    return loc.evaluate("""el => {
        const rgb = c => { const x = document.createElement('canvas').getContext('2d'); x.fillStyle = c;
            x.fillRect(0, 0, 1, 1); const [r, g, b] = x.getImageData(0, 0, 1, 1).data; return `rgb(${r}, ${g}, ${b})` }
        let e = el, bg = 'rgba(0, 0, 0, 0)'
        while (e && (bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent')) {
            bg = getComputedStyle(e).backgroundColor; e = e.parentElement }
        return [rgb(getComputedStyle(el).color), rgb(bg)] }""")


# --- B45.40: the role choice on the Requests card -------------------------------------------------------------------

def test_b45_40_the_owner_picks_a_role_when_approving_by_keyboard(open_role):
    fake = FakeAccess(OWNER, people())
    page = open_role(fake, path="/settings")
    card = requests_card(page)
    show_details(page)
    alice = card.locator(".request-row").nth(0)
    select = alice.get_by_role("combobox", name="Role for Alice Example")
    expect(select).to_have_value("viewer")  # Viewer by default
    expect(alice.locator(".request-role-hint")).to_have_text("Dashboard, CVEs, chat and their own watchlist. No Dev page.")
    select.focus()
    select.select_option("trusted")  # what a keyboard pick does: the value and a change event
    expect(alice.locator(".request-role-hint")).to_have_text("Also the Dev page, read-only, and the search playground.")
    card.get_by_role("button", name="Approve: Alice Example").focus()
    page.keyboard.press("Enter")
    expect(card.get_by_role("status")).to_contain_text("Alice Example approved")
    assert ("PUT", "/requests/user_alice", {"status": "approved", "role": "trusted"}) in fake.sent
    expect(card.locator(".request-row").nth(0).get_by_role("combobox")).to_have_value("trusted")


def test_b45_40_the_owner_changes_a_role_later_with_save_role(open_role):
    fake = FakeAccess(OWNER, people())
    page = open_role(fake, path="/settings")
    card = requests_card(page)
    show_details(page)
    bob = card.locator(".request-row").nth(1)
    expect(bob.get_by_role("combobox", name="Role for Bob")).to_have_value("trusted")
    expect(bob.get_by_role("button", name="Save role: Bob")).to_have_count(0)  # nothing to save yet
    bob.get_by_role("combobox", name="Role for Bob").select_option("reviewer")
    bob.get_by_role("button", name="Save role: Bob").click()
    expect(card.get_by_role("status")).to_have_text("Bob is now Reviewer: it applies on their next page load.")
    assert ("PUT", "/requests/user_bob", {"role": "reviewer"}) in fake.sent
    expect(bob.get_by_role("button", name="Save role: Bob")).to_have_count(0)
    expect(bob.locator(".request-status")).to_have_text("Approved")  # the status stays


def test_b45_40_a_refused_person_has_no_role_choice(open_role):
    page = open_role(FakeAccess(OWNER, [person("user_carol", "refused", None, by="user_owner")]), path="/settings")
    card = requests_card(page)
    expect(card.locator(".request-row")).to_have_count(1)
    expect(card.get_by_role("combobox")).to_have_count(0)


@pytest.mark.parametrize("width,scheme", SIZES)
def test_b45_40_the_card_with_roles_fits_in_light_and_dark(open_role, browser_name, width, scheme):
    page = open_role(FakeAccess(OWNER, people()), width=width, scheme=scheme, path="/settings")
    card = requests_card(page)
    show_details(page)
    expect(card.get_by_role("combobox")).to_have_count(2)
    card.get_by_role("combobox", name="Role for Bob").select_option("reviewer")
    expect(card.get_by_role("button", name="Save role: Bob")).to_be_visible()
    assert no_sideways_scroll(page), f"{width} {scheme}"
    for el in (card.locator(".request-role-hint").first, card.locator(".request-role label").first):
        color, fill = text_on_fill(el)
        assert contrast(color, fill) >= 4.5, (width, scheme, color, fill)
    for sel in (".request-role select", ".request-actions button"):
        box, row = card.locator(sel).last.bounding_box(), card.locator(".request-row").last.bounding_box()
        assert row["x"] <= box["x"] and box["x"] + box["width"] <= row["x"] + row["width"] + 0.5, sel
    SHOTS.mkdir(exist_ok=True)
    card.scroll_into_view_if_needed()
    card.screenshot(path=SHOTS / f"b45-{browser_name}-{width}-{scheme}-requests-roles.png")


# --- B45.41: the Dev menu item by role ----------------------------------------------------------------------------

def side_dev(page: Page):
    return page.get_by_role("navigation", name="Pages").get_by_role("button", name="Dev", exact=True)


def test_b45_41_a_viewer_has_no_dev_page(open_role):
    page = open_role(FakeAccess(as_role("viewer")))
    expect(page.get_by_role("navigation", name="Pages").get_by_role("button", name="Settings")).to_be_visible()
    expect(side_dev(page)).to_have_count(0)
    page2 = open_role(FakeAccess(as_role("viewer")), path="/dev")  # typed in: one line, no internals
    expect(page2.get_by_test_id("dev-not-yours")).to_have_text(
        "The Dev page is for people the owner trusts with Patch's internals. Ask the owner if you need it.")
    expect(page2.get_by_role("heading", name="Model", exact=True)).to_have_count(0)


@pytest.mark.parametrize("role", ["trusted", "reviewer"])
def test_b45_41_trusted_and_reviewers_have_the_dev_page(open_role, role):
    page = open_role(FakeAccess(as_role(role)))
    expect(side_dev(page)).to_be_visible()


def test_b45_41_on_a_phone_the_tab_bar_follows_the_role_too(open_role):
    page = open_role(FakeAccess(as_role("viewer")), width=PHONE)
    expect(page.get_by_role("navigation", name="Pages").get_by_role("button", name="Settings")).to_be_visible()
    expect(side_dev(page)).to_have_count(0)


# --- B45.42: the reviewer's Dev page ------------------------------------------------------------------------------

def open_dev(open_role, dev: FakeReviewer, **kw) -> Page:
    page = open_role(FakeAccess(as_role("reviewer")), dev, path="/dev", **kw)
    expect(page.get_by_role("heading", name="Model", exact=True)).to_be_visible()
    return page


@pytest.mark.parametrize("width,scheme", SIZES)
def test_b45_42_a_reviewer_sees_the_note_and_their_own_form(open_role, browser_name, width, scheme):
    page = open_dev(open_role, FakeReviewer(own_copy=True), width=width, scheme=scheme, reduced=True)
    main = page.get_by_role("main")
    note = main.get_by_test_id("reviewer-note")
    expect(note.locator("p")).to_have_text(f"{REVIEWER_NOTE} You've changed them.")
    expect(note.get_by_role("button", name="Back to the owner's settings")).to_be_visible()
    expect(main.get_by_role("radio", name="FakeLLM")).to_be_visible()  # the form: theirs to change
    expect(main.get_by_role("button", name="Reset to the defaults")).to_be_visible()
    expect(main.get_by_role("button", name="Run search")).to_be_visible()
    for name in ("Run model check", "Run retrieval check"):  # the owner's key: never a reviewer's
        expect(main.get_by_role("button", name=name)).to_have_count(0)
    expect(main.get_by_test_id("owner-runs")).to_have_count(2)
    expect(main.get_by_test_id("owners-choices")).to_have_count(0)
    color, fill = text_on_fill(note.locator("p"))
    assert contrast(color, fill) >= 4.5, (color, fill)
    edge = note.evaluate("el => [getComputedStyle(el).borderLeftWidth, getComputedStyle(el).borderLeftColor]")
    accent = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()")
    assert edge[0] == "3px"
    assert contrast(edge[1], accent) == pytest.approx(1, abs=0.01)  # the --accent edge
    assert no_sideways_scroll(page), f"{width} {scheme}"
    box = note.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b45-{browser_name}-{width}-{scheme}-dev-reviewer.png", full_page=True)


def test_b45_42_back_to_the_owners_settings_by_keyboard(open_role):
    dev = FakeReviewer(own_copy=True)
    page = open_dev(open_role, dev)
    back = page.get_by_role("button", name="Back to the owner's settings")
    back.focus()
    page.keyboard.press("Enter")
    note = page.get_by_test_id("reviewer-note")
    expect(note.locator("p")).to_have_text(f"{REVIEWER_NOTE} They start as the owner's.")
    expect(back).to_have_count(0)
    assert dev.sent == ["owners"]
    expect(page.get_by_text("✓ Changes saved")).to_be_visible()  # applied at once: nothing left to save


def test_b45_42_without_a_copy_there_is_nothing_to_go_back_to(open_role):
    page = open_dev(open_role, FakeReviewer(own_copy=False), width=PHONE, scheme="dark")
    expect(page.get_by_test_id("reviewer-note").locator("p")).to_have_text(f"{REVIEWER_NOTE} They start as the owner's.")
    expect(page.get_by_role("button", name="Back to the owner's settings")).to_have_count(0)


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) -----------------------------------

@scene
def b45_43_requests_card_with_roles(fx):
    page = fx("open_role")(FakeAccess(OWNER, people()), reduced=True, path="/settings")
    expect(requests_card(page).get_by_role("combobox")).to_have_count(2)
    still(page, "the Requests card with roles")


@scene
def b45_43_reviewers_dev_page(fx):
    page = fx("open_role")(FakeAccess(as_role("reviewer")), FakeReviewer(own_copy=True), reduced=True, path="/dev")
    expect(page.get_by_test_id("reviewer-note")).to_be_visible()
    still(page, "the reviewer's Dev page")

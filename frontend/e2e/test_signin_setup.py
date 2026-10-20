"""Browser check (seam 4) for the sign-in setup (B31, #78; open sign-up B38, #81). Check ids: B31.n, B38.n.

Sign-in on, Clerk unreachable (test_sign_in.py's `open_signed_out`): the views Patch picks from the address Clerk
sends a visitor to. Sign-up is open (B38): Clerk's sign-up steps (`#/create`) are headed "Request access to Patch",
with Clerk's form (loading here, since Clerk can't load), and nothing navigates to Clerk's hosted pages
(`accounts.dev`). There are no invitations any more: an old invitation link is the sign-in screen. The real round
trip with an SSO provider needs Clerk and the provider: the owner's step (#81).
"""
from playwright.sync_api import Page, expect

from reduced_motion import scene, still
from test_shell import no_sideways_scroll, settled
from test_sign_in import loading_note, open_signed_out  # noqa: F401 (fixture)

PHONE, DESKTOP = 390, 1440


def never_left(page: Page, ui_url: str, went: list[str]) -> None:
    assert page.url.startswith(ui_url)
    assert not [u for u in went if "accounts.dev" in u]


def watch_navigations(page: Page) -> list[str]:
    went: list[str] = []
    page.on("framenavigated", lambda f: went.append(f.url) if f == page.main_frame else None)
    page.on("request", lambda r: went.append(r.url) if r.is_navigation_request() else None)
    return went


# --- B38.25: a sign-up is a request for access, on Patch's screen, never Clerk's hosted page ----------------------

def test_b38_25_a_sign_up_is_headed_request_access_on_patchs_screen(open_signed_out, ui_url):
    page, asked = open_signed_out(path="/#/create", heading="Request access to Patch")
    went = watch_navigations(page)
    card = page.locator(".signin-card")
    expect(card).to_contain_text("Make an account first. Then you ask the owner to let you in.")
    expect(card.locator("svg.robot")).to_be_visible()
    expect(loading_note(page)).to_be_visible()  # Clerk's sign-up form goes here (unreachable in this check)
    expect(page.get_by_role("alert")).to_have_count(0)  # no refusal: sign-up is open
    never_left(page, ui_url, went)
    assert [p for p in asked if p != "/health"] == []


def test_b38_25_the_sign_up_screen_fits_a_phone_in_light_and_dark(open_signed_out):
    for width, scheme in ((PHONE, "dark"), (DESKTOP, "light")):
        page, _ = open_signed_out(path="/#/create", width=width, scheme=scheme, heading="Request access to Patch")
        settled(page.locator(".signin-card"))
        assert no_sideways_scroll(page), width
        box = page.locator(".signin-card").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, width


def test_b38_25_an_old_invitation_link_is_the_sign_in_screen(open_signed_out, ui_url):
    page, asked = open_signed_out(path="/?__clerk_ticket=test-ticket")
    went = watch_navigations(page)
    expect(loading_note(page)).to_be_visible()
    never_left(page, ui_url, went)
    assert [p for p in asked if p != "/health"] == []


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) -------------------------------------

@scene
def b38_26_request_access_sign_up(fx):
    page, _ = fx("open_signed_out")(reduced=True, path="/#/create", heading="Request access to Patch")
    expect(loading_note(page)).to_be_visible()
    still(page, "the request-access sign-up screen")

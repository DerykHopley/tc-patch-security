"""Browser check (seam 4) for the sign-in setup (B31, #78). Check ids: B31.n.

Sign-in on, Clerk unreachable (test_sign_in.py's `open_signed_out`): the views Patch picks from the address Clerk
sends a visitor to. A sign-up without an invitation (`#/create`, where Clerk's Restricted mode only ever says "access
restricted") gets Patch's own message, and nothing navigates to Clerk's hosted pages (`accounts.dev`). An invitation
link (`?__clerk_ticket=…`) gets the sign-up screen. The real round trip with an SSO provider needs Clerk and the
provider: the owner's step (#78).
"""
from playwright.sync_api import Page, expect

from reduced_motion import scene, still
from test_shell import DESKTOP, PHONE, no_sideways_scroll, settled
from test_sign_in import loading_note, open_signed_out  # noqa: F401 (fixture)

NOT_INVITED = "This account isn't invited to Patch. Ask the owner for an invitation."


def not_invited(page: Page):
    return page.get_by_role("alert").filter(has_text=NOT_INVITED)


def never_left(page: Page, ui_url: str, went: list[str]) -> None:
    assert page.url.startswith(ui_url)
    assert not [u for u in went if "accounts.dev" in u]


def watch_navigations(page: Page) -> list[str]:
    went: list[str] = []
    page.on("framenavigated", lambda f: went.append(f.url) if f == page.main_frame else None)
    page.on("request", lambda r: went.append(r.url) if r.is_navigation_request() else None)
    return went


# --- B31.9: a sign-up without an invitation: Patch's own message, never Clerk's hosted page ------------------------

def test_b31_9_a_sign_up_without_an_invitation_says_so_on_patchs_screen(open_signed_out, ui_url):
    page, asked = open_signed_out(path="/#/create")
    went = watch_navigations(page)
    card = page.locator(".signin-card")
    expect(not_invited(page)).to_be_visible()
    expect(card.locator("svg.robot")).to_be_visible()
    expect(loading_note(page)).to_have_count(0)  # no Clerk form under the message
    never_left(page, ui_url, went)
    assert [p for p in asked if p != "/health"] == []


def test_b31_9_back_to_sign_in_by_keyboard(open_signed_out, ui_url):
    page, _ = open_signed_out(path="/#/create")
    went = watch_navigations(page)
    back = page.get_by_role("button", name="Back to sign-in")
    back.focus()
    page.keyboard.press("Enter")
    expect(not_invited(page)).to_have_count(0)
    expect(loading_note(page)).to_be_visible()  # the sign-in form again (Clerk, unreachable here, is loading)
    never_left(page, ui_url, went)


def test_b31_9_the_message_fits_a_phone_in_light_and_dark(open_signed_out):
    for width, scheme in ((PHONE, "dark"), (DESKTOP, "light")):
        page, _ = open_signed_out(path="/#/create", width=width, scheme=scheme)
        note = not_invited(page)
        expect(note).to_be_visible()
        settled(page.locator(".signin-card"))
        assert no_sideways_scroll(page), width
        box = note.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, width
        # the error line's look (§5.7), as "Sign-in didn't load": a 3px edge
        assert note.evaluate("el => getComputedStyle(el).borderLeftWidth") == "3px", scheme


# --- B31.10: an invitation link opens the sign-up screen ----------------------------------------------------------

def test_b31_10_an_invitation_link_opens_the_sign_up_screen(open_signed_out, ui_url):
    page, asked = open_signed_out(path="/?__clerk_ticket=test-ticket", heading="Join Patch")
    went = watch_navigations(page)
    expect(page.locator(".signin-card")).to_contain_text("You're invited.")
    expect(loading_note(page)).to_be_visible()
    expect(not_invited(page)).to_have_count(0)
    never_left(page, ui_url, went)
    assert [p for p in asked if p != "/health"] == []


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) -------------------------------------

@scene
def b31_11_not_invited(fx):
    page, _ = fx("open_signed_out")(reduced=True, path="/#/create")
    expect(not_invited(page)).to_be_visible()
    still(page, "the not-invited message")

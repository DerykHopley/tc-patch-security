"""Browser check (seam 4) for hiding personal details on Settings (F154, #154). Check ids: F154.n.

The Requests card hides each person's name, email and note until the owner presses "Show details"; every page load
starts hidden, so a screen share is safe. Hidden means not in the page at all (text and accessible names). As in
test_access.py, `/access` and `/access/requests` are answered in the browser (FakeAccess); every other route is the
real throwaway backend. The Connected accounts card needs a real Clerk user, which the browser check has none of:
its hiding is checked by `npm test` (F154.2). Expected looks come from DESIGN.md §5.7.
"""
from collections.abc import Callable

import pytest
from playwright.sync_api import Page, expect

from reduced_motion import scene, still
from test_access import OWNER, FakeAccess, open_as, person, requests_card  # noqa: F401 (fixture)
from test_roles import text_on_fill
from test_shell import DESKTOP, PHONE, SHOTS, contrast, no_sideways_scroll

SIZES = [(PHONE, "light"), (PHONE, "dark"), (DESKTOP, "light"), (DESKTOP, "dark")]
PERSONAL = ["Alice Example", "alice@example.com", "I run vLLM at work", "Bob", "bob@example.com"]


def people() -> list[dict]:
    return [person("user_alice", "waiting", "Alice Example", note="I run vLLM at work."),
            person("user_bob", "approved", "Bob", by="user_owner")]


def open_card(open_as, **kw) -> tuple[Page, FakeAccess]:
    fake = FakeAccess(OWNER, people())
    page = open_as(fake, path="/settings", **kw)
    expect(requests_card(page).locator(".request-row")).to_have_count(2)
    return page, fake


def toggle(page: Page):
    return requests_card(page).get_by_role("button", name="Show details")


def personal_on_card(page: Page) -> list[str]:
    """The personal details found in the card's text or in any accessible name or description inside it."""
    found = requests_card(page).evaluate("""el => [el.innerText, ...[...el.querySelectorAll('*')].flatMap(e =>
        ['aria-label', 'aria-description', 'title', 'value'].map(a => e.getAttribute(a) || ''))].join('\\n')""")
    return [p for p in PERSONAL if p in found]


# --- F154.3: hidden by default ------------------------------------------------------------------------------------

def test_f154_3_names_emails_and_notes_are_hidden_on_arrival(open_as):
    page, _ = open_card(open_as)
    card = requests_card(page)
    assert personal_on_card(page) == []
    expect(toggle(page)).to_have_attribute("aria-pressed", "false")
    alice, bob = card.locator(".request-row").nth(0), card.locator(".request-row").nth(1)
    expect(alice.locator(".request-name")).to_have_text("Request 1 · id …lice")
    expect(alice).to_contain_text("(with a note)")
    expect(alice.locator(".request-note")).to_have_count(0)  # not in the DOM, not just invisible
    expect(alice.locator(".request-email")).to_have_count(0)
    expect(bob.locator(".request-name")).to_have_text("Request 2 · id …_bob")
    expect(bob).not_to_contain_text("(with a note)")
    expect(alice.locator(".request-status")).to_have_text("Waiting")  # what isn't personal stays
    page.reload()  # not remembered: a new load starts hidden again
    expect(card.locator(".request-row")).to_have_count(2)
    assert personal_on_card(page) == []


# --- F154.4: the toggle, by keyboard -------------------------------------------------------------------------------

def test_f154_4_the_toggle_shows_and_hides_the_details_by_keyboard(open_as):
    page, _ = open_card(open_as)
    card = requests_card(page)
    toggle(page).focus()
    page.keyboard.press("Enter")
    hide = card.get_by_role("button", name="Hide details")
    expect(hide).to_have_attribute("aria-pressed", "true")
    expect(hide).to_be_focused()  # the same button: focus stays on it
    alice = card.locator(".request-row").nth(0)
    expect(alice.locator(".request-name")).to_have_text("Alice Example")
    expect(alice.locator(".request-email")).to_have_text("alice@example.com")
    expect(alice.locator(".request-note")).to_have_text("I run vLLM at work.")
    expect(alice).not_to_contain_text("(with a note)")
    expect(card.get_by_role("button", name="Approve: Alice Example")).to_be_visible()
    page.keyboard.press("Space")
    expect(toggle(page)).to_have_attribute("aria-pressed", "false")
    assert personal_on_card(page) == []


# --- F154.5: the actions work while hidden -------------------------------------------------------------------------

def test_f154_5_approve_and_remove_work_while_hidden_and_name_no_one(open_as):
    page, fake = open_card(open_as)
    card = requests_card(page)
    card.get_by_role("button", name="Approve: Request 1 · id …lice").click()
    expect(card.get_by_role("status")).to_have_text("Request 1 · id …lice approved: Patch opens for them on their next visit.")
    assert ("PUT", "/requests/user_alice", {"status": "approved", "role": "viewer"}) in fake.sent
    card.get_by_role("combobox", name="Role for Request 2 · id …_bob").select_option("reviewer")
    card.get_by_role("button", name="Save role: Request 2 · id …_bob").click()
    expect(card.get_by_role("status")).to_contain_text("Request 2 · id …_bob is now Reviewer")
    card.get_by_role("button", name="Remove: Request 2 · id …_bob").click()
    expect(card.locator(".request-row")).to_have_count(1)
    assert personal_on_card(page) == []


# --- F154.6: light and dark, phone and desktop ---------------------------------------------------------------------

@pytest.mark.parametrize("width,scheme", SIZES)
def test_f154_6_the_card_fits_hidden_and_shown_in_light_and_dark(open_as, browser_name, width, scheme):
    page, _ = open_card(open_as, width=width, scheme=scheme)
    card = requests_card(page)
    expect(page.locator("html")).to_have_attribute("data-theme", scheme)
    SHOTS.mkdir(exist_ok=True)
    for state in ("hidden", "shown"):
        if state == "shown":
            toggle(page).click()
            expect(card.locator(".request-email").first).to_be_visible()
        assert no_sideways_scroll(page), (width, scheme, state)
        box, button = card.bounding_box(), card.locator(".details-toggle").bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= width, state
        assert box["x"] <= button["x"] and button["x"] + button["width"] <= box["x"] + box["width"], state
        for el in (card.locator(".request-name").first, card.locator(".details-toggle"),
                   card.locator(".request-note, .request-has-note").first):
            color, fill = text_on_fill(el)
            assert contrast(color, fill) >= 4.5, (width, scheme, state, color, fill)
        card.scroll_into_view_if_needed()
        card.screenshot(path=SHOTS / f"f154-{browser_name}-{width}-{scheme}-requests-{state}.png")


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) -------------------------------------

@scene
def f154_7_show_details(fx: Callable):
    page = fx("open_as")(FakeAccess(OWNER, people()), reduced=True, path="/settings")
    expect(requests_card(page).locator(".request-row")).to_have_count(2)
    toggle(page).click()
    expect(requests_card(page).get_by_role("button", name="Hide details")).to_be_visible()
    still(page, "the Requests card with its details shown")

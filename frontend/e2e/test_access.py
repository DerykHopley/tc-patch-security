"""Browser check (seam 4) for sign-up requests (B38, #81). Check ids: B38.n.

The pairs run.sh starts have sign-in off, and Clerk can't load in the browser check, so these checks answer the
access routes themselves (`page.route`): `/access` says what the backend would say to a signed-in person who isn't
approved yet, or to the owner with sign-in on; `/access/requests` gives the owner's Requests card its people. Every
other route is the real throwaway backend. What the backend does with a request (403s, one alert, the owner's
approval) is checked by backend/tests/test_access.py; the real round trip with Clerk is the owner's check on #81.
"""
import json
import re
from collections.abc import Callable

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from reduced_motion import scene, still
from test_shell import no_sideways_scroll, settled

PHONE, DESKTOP = 390, 1440
SIZES = [(PHONE, "light"), (PHONE, "dark"), (DESKTOP, "light"), (DESKTOP, "dark")]

OWNER = {"status": "approved", "owner": True, "role": "owner", "sign_in": True, "note": None, "at": None}
NEW = {"status": "none", "owner": False, "role": "viewer", "sign_in": True, "note": None, "at": None}


def person(user_id: str, status: str, name: str | None, **over) -> dict:
    return {"user_id": user_id, "status": status, "note": None, "by": None, "at": "2026-10-19T08:00:00+00:00",
            "requested_at": "2026-10-19T08:00:00+00:00", "migrated": False, "name": name,
            "email": f"{user_id.removeprefix('user_')}@example.com" if name else None, "role": "viewer", **over}


class FakeAccess:
    """The access routes, answered in the browser. `me`: what /access says; `people`: the Requests card's list.
    Records every request and change the page sends."""

    def __init__(self, me: dict, people: list[dict] | None = None):
        self.me, self.people = dict(me), people or []
        self.sent: list[tuple[str, str, dict | None]] = []

    def route(self, ctx: BrowserContext, api_url: str) -> None:
        ctx.route(re.compile(re.escape(api_url) + r"/access(/.*)?$"), self.answer)

    def answer(self, route: Route) -> None:
        req = route.request
        path = req.url.split("/access", 1)[1]
        body = req.post_data_json if req.post_data else None
        self.sent.append((req.method, path, body))
        if path == "" and req.method == "GET":
            return self.json(route, self.me)
        if path == "/request":
            self.me = {**self.me, "status": "waiting", "note": (body or {}).get("note")}
            return self.json(route, self.me)
        if path == "/requests":
            return self.json(route, {"requests": self.people, "names": True, "you": "user_owner"})
        uid = path.split("/")[2]
        if path.endswith("/remove"):
            self.people = [p for p in self.people if p["user_id"] != uid]
        else:
            for p in self.people:
                if p["user_id"] == uid and "status" in body:
                    p.update(status=body["status"], by="user_owner", at="2026-10-19T09:30:00+00:00")
                if p["user_id"] == uid and "role" in body:  # B45
                    p.update(role=body["role"])
        return self.json(route, {})

    @staticmethod
    def json(route: Route, body: dict) -> None:
        route.fulfill(status=200, content_type="application/json", body=json.dumps(body))


@pytest.fixture
def open_as(browser: Browser, ui_url: str, api_url: str):
    """Opens Patch at `path` with the access routes answered by `fake`."""
    contexts: list[BrowserContext] = []

    def _open(fake: FakeAccess, width=DESKTOP, scheme="light", reduced=False, path="/") -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        fake.route(ctx, api_url)
        page = ctx.new_page()
        page.goto(ui_url + path)
        page.evaluate("document.fonts.ready.then(() => null)")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def heading(page: Page, name: str | re.Pattern):
    return page.get_by_role("heading", level=1, name=name)


def fits(page: Page, width: int, what: str) -> None:
    assert no_sideways_scroll(page), what
    box = page.locator(".signin-card").bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width, what


# --- B38.40: a new account asks, with an optional note ------------------------------------------------------------

def test_b38_40_a_new_account_sees_only_the_request_screen(open_as):
    fake = FakeAccess(NEW)
    page = open_as(fake)
    expect(heading(page, "Ask to join Patch")).to_be_visible()
    expect(page.get_by_role("navigation")).to_have_count(0)  # none of the app
    card = page.locator(".signin-card")
    expect(card.locator("svg.robot")).to_have_attribute("data-mood", "idle")
    expect(page.get_by_label("A note for the owner (optional)")).to_be_visible()
    expect(card).to_contain_text("280 characters left")


def test_b38_40_sending_with_a_note_by_keyboard_shows_the_waiting_screen(open_as):
    fake = FakeAccess(NEW)
    page = open_as(fake)
    note = page.get_by_label("A note for the owner (optional)")
    note.fill("I look after our Ollama servers.")
    expect(page.locator(".access-count")).to_contain_text("248 characters left")
    page.get_by_role("button", name="Send request").focus()
    page.keyboard.press("Enter")
    expect(heading(page, "Your request is waiting for the owner")).to_be_visible()
    expect(heading(page, "Your request is waiting for the owner")).to_be_focused()  # the new step is announced
    expect(page.locator(".access-mine")).to_contain_text("I look after our Ollama servers.")
    assert ("POST", "/request", {"note": "I look after our Ollama servers."}) in fake.sent


def test_b38_40_a_note_over_280_characters_is_refused_in_the_page(open_as):
    fake = FakeAccess(NEW)
    page = open_as(fake)
    page.get_by_label("A note for the owner (optional)").fill("x" * 285)
    expect(page.locator(".access-count")).to_contain_text("5 characters too many")
    page.get_by_role("button", name="Send request").click()
    expect(page.get_by_role("alert")).to_contain_text("at most 280 characters")
    assert not [s for s in fake.sent if s[1] == "/request"]  # nothing sent


@pytest.mark.parametrize("width,scheme", SIZES)
def test_b38_40_the_request_screen_fits_and_follows_the_theme(open_as, width, scheme):
    page = open_as(FakeAccess(NEW), width=width, scheme=scheme)
    expect(heading(page, "Ask to join Patch")).to_be_visible()
    settled(page.locator(".signin-card"))
    expect(page.locator("html")).to_have_attribute("data-theme", scheme)
    fits(page, width, f"{width} {scheme}")
    robot = page.locator(".signin-card svg.robot").bounding_box()
    card = page.locator(".signin-card").bounding_box()
    assert robot["y"] < card["y"] < robot["y"] + robot["height"]  # Patch's head over the card's edge


# --- B38.41: waiting, then approved ------------------------------------------------------------------------------

@pytest.mark.parametrize("width,scheme", SIZES)
def test_b38_41_the_waiting_screen_fits_with_the_note(open_as, width, scheme):
    fake = FakeAccess({**NEW, "status": "waiting", "note": "A long note " * 20})
    page = open_as(fake, width=width, scheme=scheme)
    expect(heading(page, "Your request is waiting for the owner")).to_be_visible()
    expect(page.get_by_label("A note for the owner (optional)")).to_have_count(0)  # one request: no form
    settled(page.locator(".signin-card"))
    fits(page, width, f"{width} {scheme}")


def test_b38_41_check_again_opens_the_app_once_approved(open_as):
    fake = FakeAccess({**NEW, "status": "waiting"})
    page = open_as(fake)
    check = page.get_by_role("button", name="Check again")
    check.click()
    expect(page.get_by_role("status").filter(has_text="Still waiting")).to_be_visible()
    fake.me = {**fake.me, "status": "approved"}
    check.click()
    expect(heading(page, "Dashboard")).to_be_visible()


# --- B38.42: refused ---------------------------------------------------------------------------------------------

def test_b38_42_a_refused_account_sees_a_polite_no_and_cannot_ask_again(open_as):
    page = open_as(FakeAccess({**NEW, "status": "refused"}), width=PHONE, scheme="dark")
    expect(heading(page, "Your request wasn't approved")).to_be_visible()
    expect(page.locator(".signin-card")).to_contain_text("Thanks for asking.")
    expect(page.get_by_role("button", name="Send request")).to_have_count(0)
    expect(page.get_by_role("button", name="Check again")).to_have_count(0)
    settled(page.locator(".signin-card"))
    fits(page, PHONE, "refused")


# --- B38.43: the owner's Requests card ----------------------------------------------------------------------------

def people() -> list[dict]:
    return [
        person("user_alice", "waiting", "Alice Example", note="<b>Hi</b> I run vLLM\nat work."),
        person("user_bob", "approved", "Bob", by="user_owner"),
        person("user_carol", "refused", None, by="user_owner"),
    ]


def requests_card(page: Page):
    return page.locator("section#requests")


def test_b38_43_the_card_is_the_owners_only(open_as):
    page = open_as(FakeAccess({**OWNER, "owner": False}, people()), path="/settings")
    expect(heading(page, "Settings")).to_be_visible()
    expect(page.locator("section.settings-card").first).to_be_visible()
    expect(requests_card(page)).to_have_count(0)
    # and with sign-in off (no requests at all) it isn't there for the owner either
    page2 = open_as(FakeAccess({**OWNER, "sign_in": False}, people()), path="/settings")
    expect(page2.locator("section.settings-card").first).to_be_visible()
    expect(requests_card(page2)).to_have_count(0)


def test_b38_43_the_card_lists_people_with_their_note_as_plain_text(open_as):
    page = open_as(FakeAccess(OWNER, people()), path="/settings")
    card = requests_card(page)
    rows = card.locator(".request-row")
    expect(rows).to_have_count(3)
    alice = rows.nth(0)
    expect(alice).to_contain_text("Alice Example")
    expect(alice).to_contain_text("alice@example.com")
    expect(alice.locator(".request-status")).to_have_text("Waiting")
    note = alice.locator(".request-note")
    expect(note).to_have_text("<b>Hi</b> I run vLLM\nat work.")  # the tags as text: never HTML
    expect(note.locator("b")).to_have_count(0)
    expect(rows.nth(1)).to_contain_text("Approved by you")
    expect(rows.nth(2)).to_contain_text("user_carol")  # no name from Clerk: the id
    expect(card.get_by_role("button", name="Approve: Alice Example")).to_be_visible()
    expect(card.get_by_role("button", name="Refuse: Alice Example")).to_be_visible()
    expect(card.get_by_role("button", name="Remove: Bob")).to_be_visible()
    expect(card.get_by_role("button", name="Undo refusal: user_carol")).to_be_visible()


def test_b38_43_approve_by_keyboard_then_undo_a_refusal(open_as):
    fake = FakeAccess(OWNER, people())
    page = open_as(fake, path="/settings")
    card = requests_card(page)
    card.get_by_role("button", name="Approve: Alice Example").focus()
    page.keyboard.press("Enter")
    expect(card.get_by_role("status")).to_contain_text("Alice Example approved")
    expect(card.locator(".request-row").nth(0).locator(".request-status")).to_have_text("Approved")
    assert ("PUT", "/requests/user_alice", {"status": "approved", "role": "viewer"}) in fake.sent  # B45: the default
    card.get_by_role("button", name="Undo refusal: user_carol").click()
    expect(card.locator(".request-row").nth(2).locator(".request-status")).to_have_text("Waiting")
    card.get_by_role("button", name="Remove: Bob").click()
    expect(card.locator(".request-row")).to_have_count(2)
    assert ("POST", "/requests/user_bob/remove", None) in fake.sent


def test_b38_43_an_alert_link_lands_on_the_card(open_as):
    page = open_as(FakeAccess(OWNER, people()), path="/settings#requests", width=PHONE)
    card = requests_card(page)
    expect(card.locator(".request-row")).to_have_count(3)
    # in view once the cards above it have loaded (they grow and push it down)
    page.wait_for_function("() => { const r = document.getElementById('requests')?.getBoundingClientRect();"
                           " return r && r.top > -1 && r.top < innerHeight / 2 }")


@pytest.mark.parametrize("width,scheme", SIZES)
def test_b38_43_the_card_fits_in_light_and_dark(open_as, width, scheme):
    page = open_as(FakeAccess(OWNER, people()), width=width, scheme=scheme, path="/settings")
    card = requests_card(page)
    expect(card.locator(".request-row")).to_have_count(3)
    expect(page.locator("html")).to_have_attribute("data-theme", scheme)
    assert no_sideways_scroll(page), f"{width} {scheme}"
    box = card.bounding_box()
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    # the status is a word with an edge colour, in --text: readable in both themes
    pill = card.locator(".request-status").first
    text, body = pill.evaluate("el => [getComputedStyle(el).color, getComputedStyle(document.body).color]")
    assert text == body


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) -----------------------------------

def _fx_open(fx: Callable, me: dict, path: str = "/", ppl: list[dict] | None = None) -> Page:
    return fx("open_as")(FakeAccess(me, ppl), reduced=True, path=path)


@scene
def b38_44_request_screen(fx):
    page = _fx_open(fx, NEW)
    expect(heading(page, "Ask to join Patch")).to_be_visible()
    still(page, "the request screen")


@scene
def b38_44_requests_card(fx):
    page = _fx_open(fx, OWNER, "/settings", people())
    expect(requests_card(page).locator(".request-row")).to_have_count(3)
    still(page, "the Requests card")

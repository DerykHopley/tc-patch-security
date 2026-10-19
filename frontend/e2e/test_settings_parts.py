"""Browser check (seam 4) for Settings in two parts (B48, #97; the Profile card of #77). Check ids: B48.n.

"Yours" for everyone (the owner too): Watchlist, Profile, Alerts, Patch's answers, Priority and due dates, Demo data.
"This Patch" for the owner only: Requests first (top of its right column), Refresh runs and Data under it; Delivery on
the left.

The pairs run.sh starts have sign-in off, so the one local user is the owner. Another user is the browser told so:
`/settings` says `owner: false` (no server settings, the schedule not theirs), as the backend says to them
(backend/tests/test_profile.py B48.6), and `/access` says a signed-in Viewer. The owner's Requests card needs sign-in
on, so `/access` says that too (test_access.py's FakeAccess). Connected accounts needs a real Clerk user: not here.

Screenshots for the owner's review go to E2E_SHOTS (a folder) when it is set; nothing is written otherwise.
"""
import os
import re

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from reduced_motion import scene, still
from test_access import OWNER, FakeAccess, person
from test_settings_layout import as_rgb
from test_settings_over_env import api, server_defaults  # noqa: F401 (a fixture)
from test_shell import contrast, no_sideways_scroll

PHONE, DESKTOP = 390, 1440
SIZES = [(PHONE, "light"), (PHONE, "dark"), (DESKTOP, "light"), (DESKTOP, "dark")]
VIEWER = {**OWNER, "owner": False, "role": "viewer"}
YOURS = ["Watchlist", "Profile", "Alerts", "Patch's answers", "Priority and due dates", "Demo data"]
THIS_PATCH = ["Requests", "Refresh runs", "Data", "Delivery"]  # DOM order: the right column (Requests) first
NOTE = "Your alerts show here in Patch (Recent alerts, the New badge). Phone and email alerts go to the owner."
SHOTS = os.environ.get("E2E_SHOTS")


def people() -> list[dict]:
    return [person("user_alice", "waiting", "Alice Example", note="I run Ollama at work."),
            person("user_bob", "approved", "Bob", role="trusted")]


def not_the_owner(ctx: BrowserContext, api_url: str) -> None:
    """/settings as the backend answers anyone but the owner: no server settings, the owner's schedule."""
    def answer(route: Route) -> None:
        if route.request.method != "GET":
            route.continue_()
            return
        response = route.fetch()
        body = response.json()
        body.update(owner=False, server=None)
        body["schedule"]["yours"] = False
        body["settings"]["alerts"]["channels"] = []
        route.fulfill(response=response, json=body)
    ctx.route(f"{api_url}/settings", answer)


@pytest.fixture
def open_settings_as(browser: Browser, ui_url: str, api_url: str, server_defaults):  # noqa: F811
    contexts: list[BrowserContext] = []

    def _open(who: str = "owner", width=DESKTOP, scheme="light", reduced=False, path="/settings") -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        FakeAccess(OWNER if who == "owner" else VIEWER, people()).route(ctx, api_url)
        if who != "owner":
            not_the_owner(ctx, api_url)
        page = ctx.new_page()
        page.goto(ui_url + path)
        expect(page.get_by_role("heading", name="Yours", exact=True)).to_be_visible()
        expect(page.get_by_text("All changes saved")).to_be_visible()  # loaded, and nothing is dirty on arrival
        if who == "owner":
            expect(page.locator("section#requests .request-row")).to_have_count(2)
        page.evaluate("document.fonts.ready.then(() => null)")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()
    api(api_url, "/profile", "PUT", {"name": None})  # a name isn't demo data: reset keeps it, so clear it here


def part(page: Page, name: str):
    return page.locator("section.settings-part", has=page.get_by_role("heading", level=2, name=name, exact=True))


def titles(section) -> list[str]:
    return section.locator("section.card .card-title").all_inner_texts()


def box(page: Page, title: str) -> dict:
    return page.locator("section.card", has=page.get_by_role("heading", level=3, name=title, exact=True)).bounding_box()


def shot(page: Page, name: str) -> None:
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        page.screenshot(path=os.path.join(SHOTS, f"{name}.png"), full_page=True)


# --- B48.30: the owner sees both parts; each card under its part's heading -------------------------------------------

def test_b48_30_the_owner_sees_yours_then_this_patch(open_settings_as):
    page = open_settings_as()
    assert page.get_by_role("heading", level=2).all_inner_texts() == ["Yours", "This Patch"]
    assert titles(part(page, "Yours")) == YOURS
    assert titles(part(page, "This Patch")) == THIS_PATCH
    expect(part(page, "This Patch")).to_contain_text("Only you see this part")


# --- B48.31: Requests at the top of "This Patch"'s right column; first on a phone; the alert link lands on it ------

RUN = {"trigger": "schedule", "started": "2026-10-19T06:00:00+00:00", "finished": "2026-10-19T06:02:00+00:00",
       "result": "ok", "duration_s": 120.0, "counts": {"new": 2, "updated": 1, "kev_added": 0, "rescored": 0},
       "new_cves": [], "version": 3, "feeds": [], "errors": [], "alerts_sent": 1, "alerts_recorded": 0,
       "alerts_failed": 0, "alerts_held": 0, "reason": None, "next_allowed": None, "times": 1}
DIGEST = {"at": "2026-10-19T06:59:00+00:00", "kind": "digest", "cve": None, "reason": None, "title": "271 alerts",
          "body": "271 overdue", "priority": 3, "tags": [], "click": None, "alerts": [],
          "channels": [{"channel": "ntfy", "sent": True, "error": None}]}


def busy(page: Page, api_url: str) -> None:
    """The owner's page in daily use (live mode): 20 refresh runs and 20 recent alerts, the two lists that grow."""
    def runs(route: Route) -> None:
        response = route.fetch()
        route.fulfill(response=response, json={**response.json(), "mode": "live", "runs": [RUN] * 20})
    page.context.route(f"{api_url}/refresh/runs", runs)
    page.context.route(f"{api_url}/alerts", lambda route: route.fulfill(json={"alerts": [DIGEST] * 20}))
    page.reload()
    expect(page.locator(".run-list > li")).to_have_count(20)
    expect(page.locator(".alert-log > li")).to_have_count(20)


def test_b48_31_requests_tops_the_right_column_and_the_columns_balance(open_settings_as, api_url):
    page = open_settings_as(width=DESKTOP)
    busy(page, api_url)
    req, runs, data, delivery = (box(page, t) for t in THIS_PATCH)
    assert req["x"] > delivery["x"] + delivery["width"] - 1  # the right column
    assert abs(req["y"] - delivery["y"]) <= 1  # its top: level with the left column's first card
    assert abs(runs["x"] - req["x"]) <= 1 and req["y"] < runs["y"] < data["y"]
    # Balanced: neither column ends far below the other (Delivery and Refresh runs are the tall ones). With Delivery
    # and Data on the left, the left one ended about 1,080px lower (measured, 2026-10-19)
    left_end, right_end = delivery["y"] + delivery["height"], data["y"] + data["height"]
    tallest = max(left_end, right_end) - req["y"]
    assert abs(left_end - right_end) < 0.25 * tallest, (left_end, right_end)
    assert no_sideways_scroll(page)


def test_b48_31_on_a_phone_requests_comes_first_in_this_patch(open_settings_as):
    page = open_settings_as(width=PHONE)
    head = part(page, "This Patch").get_by_role("heading", level=2).bounding_box()
    boxes = [box(page, t) for t in THIS_PATCH]
    assert boxes[0]["y"] > head["y"] and [b["y"] for b in boxes] == sorted(b["y"] for b in boxes)
    assert len({round(b["x"]) for b in boxes}) == 1
    assert no_sideways_scroll(page)


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b48_31_the_requests_link_lands_on_the_card(open_settings_as, width):
    page = open_settings_as(width=width, path="/settings#requests")
    page.wait_for_function("() => { const r = document.getElementById('requests')?.getBoundingClientRect();"
                           " return r && r.top >= 0 && r.top < 120 }")


# --- B48.32: anyone else sees only "Yours", their alerts in Patch only ----------------------------------------------

@pytest.mark.parametrize("width, scheme", SIZES)
def test_b48_32_another_user_sees_only_yours(open_settings_as, width, scheme):
    page = open_settings_as("viewer", width=width, scheme=scheme)
    assert page.get_by_role("heading", level=2).all_inner_texts() == ["Yours"]
    assert titles(part(page, "Yours")) == YOURS
    for owners in THIS_PATCH:
        expect(page.get_by_role("heading", name=owners, exact=True)).to_have_count(0)
    alerts = page.locator("section.card", has=page.get_by_role("heading", name="Alerts", exact=True))
    note = alerts.get_by_test_id("in-patch-note")
    expect(note).to_have_text(NOTE)
    expect(alerts.get_by_test_id("owners-schedule")).to_have_text(
        "Patch reads a snapshot that never changes, so it checks for no new CVEs (set by the owner).")
    expect(page.get_by_label("Quiet hours start")).to_have_count(0)  # nothing is sent, so nothing to hold
    expect(page.get_by_role("checkbox", name=re.compile("Desktop notification|Email|Phone push"))).to_have_count(0)
    colour, fill = note.evaluate("e => [getComputedStyle(e).color, getComputedStyle(e).backgroundColor]")
    assert contrast(as_rgb(page, colour), as_rgb(page, fill)) >= 4.5
    assert note.evaluate("e => getComputedStyle(e).borderLeftWidth") == "3px"
    assert no_sideways_scroll(page)
    shot(page, f"settings-viewer-{width}-{scheme}")


def test_b48_32_the_dashboard_has_no_schedule_link_for_another_user(browser, live_ui_url, live_api_url):
    ctx = browser.new_context(viewport={"width": DESKTOP, "height": 900})
    try:
        def not_yours(route: Route) -> None:
            response = route.fetch()
            body = response.json()
            body["data"]["schedule"]["yours"] = False
            route.fulfill(response=response, json=body)
        ctx.route(f"{live_api_url}/dashboard**", not_yours)
        page = ctx.new_page()
        page.goto(live_ui_url + "/")
        expect(page.get_by_role("button", name="Check now")).to_be_visible()
        expect(page.get_by_role("link", name=re.compile("Schedule and refresh runs"))).to_have_count(0)
    finally:
        ctx.close()


@pytest.mark.parametrize("width, scheme", SIZES)
def test_b48_30_the_owners_page_in_both_themes_at_both_widths(open_settings_as, width, scheme):
    page = open_settings_as(width=width, scheme=scheme)
    for name in ("Yours", "This Patch"):
        h = part(page, name).get_by_role("heading", level=2, name=name)
        colour = h.evaluate("e => getComputedStyle(e).color")
        intro = part(page, name).locator(".page-intro")
        page_bg = as_rgb(page, page.evaluate("getComputedStyle(document.body).backgroundColor"))
        assert contrast(as_rgb(page, colour), page_bg) >= 4.5
        assert contrast(as_rgb(page, intro.evaluate("e => getComputedStyle(e).color")), page_bg) >= 4.5
    assert no_sideways_scroll(page)
    shot(page, f"settings-owner-{width}-{scheme}")


# --- B48.33: the Profile card: anonymous by default, a name saved with the save bar, removed at once ---------------

def test_b48_33_a_display_name_saves_with_the_bar_and_is_removed_at_once(open_settings_as, api_url):
    page = open_settings_as()
    name = page.get_by_label("Display name (optional)")
    expect(name).to_have_value("")
    expect(page.get_by_role("button", name="Remove my name")).to_have_count(0)
    name.fill("  Ada   Lovelace ")
    expect(page.get_by_text("Unsaved changes")).to_be_visible()
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_text("✓ Changes saved")).to_be_visible()
    assert api(api_url, "/profile") == {"name": "Ada Lovelace"}
    page.reload()
    expect(page.get_by_label("Display name (optional)")).to_have_value("Ada Lovelace")
    remove = page.get_by_role("button", name="Remove my name")
    remove.focus()
    page.keyboard.press("Enter")
    expect(page.locator(".profile-done")).to_have_text(
        'Name removed: new records say "you". Past records keep the name they were made with.')
    expect(page.get_by_label("Display name (optional)")).to_have_value("")
    assert api(api_url, "/profile") == {"name": None}
    expect(page.get_by_text("All changes saved")).to_be_visible()


def test_b48_33_a_name_over_60_characters_is_refused_in_the_page(open_settings_as, api_url):
    page = open_settings_as(width=PHONE, scheme="dark")
    page.get_by_label("Display name (optional)").fill("x" * 61)
    expect(page.get_by_role("alert")).to_have_text("A display name can be at most 60 characters: this one has 61.")
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_text("Unsaved changes")).to_be_visible()
    assert api(api_url, "/profile") == {"name": None}
    assert no_sideways_scroll(page)


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) --------------------------------------

@scene
def b48_34_settings_in_two_parts(fx):
    page = fx("open_settings_as")(reduced=True)
    still(page, "Settings, the owner's two parts")

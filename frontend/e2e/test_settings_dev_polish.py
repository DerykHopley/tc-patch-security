"""Browser check (seam 4) for the Settings and Dev polish from the page review (B50, #95). Check ids: B50.n, the issue's
items: B50.1 no "Live" chip, the Dev intro by role, one name "Dev", "Model-check report"; B50.2 the phone's save bar
only with something to say; B50.5 a link to the dashboard's Recent alerts lands on it; B50.6 Start over and
the embedding map's labels; B50.8 Pause disabled in snapshot mode; B50.9 Settings, Dev and the dashboard end to end as
a Viewer and a Reviewer.

The pairs run.sh starts have sign-in off (the browser is the owner). Another user is the browser told so, as
test_settings_parts.py and test_roles.py do: `/access` (FakeAccess) gives the role, `/settings` answers as the backend
answers anyone but the owner (backend/tests/test_profile.py B48.6, B50.1), `/dashboard` says the schedule isn't theirs,
and a reviewer's `/dev/settings` is FakeReviewer's. Expected looks come from DESIGN.md §5.5, §5.6, §5.7, §5.11.

Screenshots (Settings and Dev as owner, Viewer and Reviewer; 390px and 1440px; light and dark) go to screenshots/,
untracked.
"""
import re

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, Route, expect

from reduced_motion import scene, still
from test_access import OWNER, FakeAccess
from test_roles import FakeReviewer, as_role
from test_settings import overlaps, patch_button_box
from test_settings_layout import as_rgb
from test_settings_over_env import server_defaults  # noqa: F401 (a fixture)
from test_settings_parts import DIGEST, not_the_owner
from test_shell import SHOTS, contrast, no_sideways_scroll

PHONE, DESKTOP = 390, 1440
SIZES = [(PHONE, "light"), (PHONE, "dark"), (DESKTOP, "light"), (DESKTOP, "dark")]
NOTE = "Your alerts show here in Patch (Recent alerts, the New badge). Phone and email alerts go to the owner."


def not_the_owners_dashboard(ctx: BrowserContext, api_url: str) -> None:
    """/dashboard as anyone but the owner gets it: the schedule isn't theirs, no feeds."""
    def answer(route: Route) -> None:
        response = route.fetch()
        body = response.json()
        body["data"]["schedule"] = {**(body["data"].get("schedule") or {"hours": 6, "paused": False}), "yours": False}
        body["data"]["feeds"] = None
        route.fulfill(response=response, json=body)
    ctx.route(re.compile(re.escape(api_url) + r"/dashboard(\?.*)?$"), answer)


@pytest.fixture
def open_as(browser: Browser, ui_url: str, api_url: str, server_defaults):  # noqa: F811
    """Opens Patch at `path` as `who`: "owner", "viewer", "trusted" or "reviewer"."""
    contexts: list[BrowserContext] = []

    def _open(who: str = "owner", path: str = "/settings", width=DESKTOP, scheme="light", reduced=False,
              setup=None) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        FakeAccess(OWNER if who == "owner" else as_role(who)).route(ctx, api_url)
        if who != "owner":
            not_the_owner(ctx, api_url)
            not_the_owners_dashboard(ctx, api_url)
        if who == "reviewer":
            FakeReviewer(own_copy=False).route(ctx, api_url)
        if setup:
            setup(ctx)
        page = ctx.new_page()
        page.goto(ui_url + path)
        if path == "/settings":
            expect(page.get_by_role("heading", name="Yours", exact=True)).to_be_visible()
        if path == "/dev" and who != "viewer":
            expect(page.get_by_role("heading", name="Model", exact=True)).to_be_visible()
        page.evaluate("document.fonts.ready.then(() => null)")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def card(page: Page, title: str):
    return page.locator("section.card", has=page.get_by_role("heading", name=title, exact=True))


def shot(page: Page, browser_name: str, name: str) -> None:
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b50-{browser_name}-{name}.png", full_page=True)


# --- B50.1: no "Live" chip; the Dev page's intro says who sees it; one name, "Dev"; "Model-check report" -----------

def test_b50_1_no_card_on_settings_or_dev_has_a_status_chip(open_as):
    page = open_as()
    expect(page.locator("main section.card").first).to_be_visible()
    expect(page.locator("main .status-chip")).to_have_count(0)
    page = open_as(path="/dev")
    expect(page.locator("main .status-chip")).to_have_count(0)


def test_b50_1_the_dev_page_is_named_dev_and_its_intro_says_who_sees_it(open_as):
    page = open_as(path="/dev")
    expect(page.get_by_role("heading", level=1)).to_have_text("Dev")
    expect(page.locator(".topbar, header").first).not_to_contain_text("Dev panel")
    intro = page.get_by_test_id("owner-intro")
    expect(intro).to_contain_text("Trusted people read it and use the playground")
    expect(intro).to_contain_text("Reviewers change their own copy")
    expect(intro).to_contain_text("Viewers don't see it")
    expect(intro).not_to_contain_text("DEV_PANEL")
    expect(page.get_by_role("heading", name="Model-check report", exact=True)).to_be_visible()
    expect(page.get_by_text("Evaluation report")).to_have_count(0)


# --- B50.2: the save bar on a phone shows only with something to say ---------------------------------------------

@pytest.mark.parametrize("path, field", [("/settings", "Minimum severity"), ("/dev", "Sources per search")])
def test_b50_2_on_a_phone_the_save_bar_shows_only_with_unsaved_changes(open_as, path, field):
    page = open_as(path=path, width=PHONE)
    bar = page.locator(".save-bar")
    expect(bar).to_have_class(re.compile(r"\bidle\b"))
    box = bar.bounding_box()
    assert box and box["height"] <= 1 and box["width"] <= 1  # takes no room
    expect(bar.get_by_role("status")).to_have_text("All changes saved")  # still read out, for a screen reader
    control = page.get_by_label(field)
    if path == "/settings":
        control.select_option("LOW")
    else:
        control.fill("7")
    expect(bar).not_to_have_class(re.compile(r"\bidle\b"))
    expect(bar.get_by_role("status")).to_have_text("Unsaved changes")
    box = bar.bounding_box()
    assert box and box["height"] > 30
    assert not overlaps(bar.get_by_role("button", name="Save changes").bounding_box(), patch_button_box(PHONE))
    page.get_by_role("button", name="Discard").click()
    expect(bar).to_have_class(re.compile(r"\bidle\b"))  # nothing to say again
    assert no_sideways_scroll(page)


def test_b50_2_on_a_desktop_the_save_bar_always_shows(open_as):
    page = open_as(width=DESKTOP)
    box = page.locator(".save-bar").bounding_box()
    assert box and box["height"] > 30
    expect(page.locator(".save-bar")).to_contain_text("All changes saved")


# --- B50.5: a link to the dashboard's Recent alerts (/#recent-alerts) lands on the card ----------------------------
# Until #144 Delivery showed the last 3 and linked here; now Delivery has the full log (test_alerts_split.py F144.7)
# and the card the last 5 real alerts. The anchor stays, so an older link still lands.

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b50_5_a_link_to_recent_alerts_lands_on_the_card(open_as, api_url, width):
    def twenty(ctx: BrowserContext) -> None:
        ctx.route(f"{api_url}/alerts", lambda route: route.fulfill(json={"alerts": [DIGEST] * 20}))
    page = open_as(path="/#recent-alerts", width=width, setup=twenty)
    alerts = page.locator("section#recent-alerts")
    expect(alerts.locator(".alert-log > li")).to_have_count(5)  # #144: the last 5
    page.wait_for_function("() => { const r = document.getElementById('recent-alerts')?.getBoundingClientRect();"
                           " return r && r.top >= 0 && r.top < 120 }")


# --- B56: the card stays in view when the charts draw after the alerts are in ------------------------------------

# A chart sizes itself to its card (a ResizeObserver, charts.tsx useWidth), then draws: it grows from ~80px to
# ~260px. Here every chart hears its size 50 ms late, so it draws just after the alerts are in and the card is in
# view: the order CI's slower runner sometimes took. Before the fix, 20, 50 and 100 ms each failed every run in both
# browsers (0 ms and 200 ms passed: checked, why 200 ms passes is unverified). The delay is in the page, not the test.
CHARTS_DRAW_LATE = """(() => {
  const Native = window.ResizeObserver;
  window.ResizeObserver = class extends Native {
    constructor(callback) {
      super((entries, observer) => {
        if (entries.some((e) => e.target.closest('.chart'))) setTimeout(() => callback(entries, observer), 50);
        else callback(entries, observer);
      });
    }
  };
})()"""

# Once every chart has drawn: where the card's top is two frames later (what a person sees, not a settled end).
CARD_TOP_AFTER_THE_CHARTS = """() => new Promise((done) => {
  const drawn = () => [...document.querySelectorAll('.dash-main .chart')].every((c) => c.querySelector('svg'));
  const look = () => drawn()
    ? requestAnimationFrame(() => requestAnimationFrame(() =>
        done(document.getElementById('recent-alerts').getBoundingClientRect().top)))
    : requestAnimationFrame(look);
  look();
})"""


def test_b56_recent_alerts_stays_in_view_when_the_charts_draw_late(open_as, api_url):
    """At 1440px Recent alerts heads the right column, the page's tallest, so the charts growing on the left leave
    the page's height alone (keepInView watched only that) while the browser's scroll anchoring keeps a chart in
    place and scrolls the card off the top. CI's B50.5 failures, 6 runs (B56)."""
    def late(ctx: BrowserContext) -> None:
        ctx.route(f"{api_url}/alerts", lambda route: route.fulfill(json={"alerts": [DIGEST] * 20}))
        ctx.add_init_script(CHARTS_DRAW_LATE)
    page = open_as(path="/#recent-alerts", width=DESKTOP, setup=late)
    expect(page.locator("section#recent-alerts .alert-log > li")).to_have_count(5)  # #144: the last 5
    top = page.evaluate(CARD_TOP_AFTER_THE_CHARTS)
    assert 0 <= top < 120, f"Recent alerts' top at {top:.0f}px once the charts drew"


# --- B50.6: Start over, its own warning card at the end of "Yours" -------------------------------------------------

@pytest.mark.parametrize("width, scheme", SIZES)
def test_b50_6_start_over_says_what_it_deletes_in_a_warning_card(open_as, width, scheme):
    page = open_as(width=width, scheme=scheme)
    start = card(page, "Start over")
    yours = page.locator("section.settings-part").first
    assert yours.locator("section.card .card-title").all_inner_texts()[-1] == "Start over"  # the last of "Yours"
    expect(start).to_contain_text("Every CVE status you set, with its whole decision history")
    expect(start).to_contain_text("everyone's chat goes back to the default model")  # the owner's Dev choices
    expect(start).to_contain_text("Kept: your display name and the server settings")
    expect(start).to_contain_text("It can't be undone.")
    expect(start.get_by_role("button", name="Reset all my data")).to_be_disabled()
    edge = start.evaluate("e => getComputedStyle(e).boxShadow")
    error = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--error').trim()")
    assert "inset" in edge and "2px" in edge and as_rgb(page, error) in edge  # the 2px --error edge
    surface = as_rgb(page, start.evaluate("e => getComputedStyle(e).backgroundColor"))
    for item in start.locator(".reset-list li").all():
        assert contrast(as_rgb(page, item.evaluate("e => getComputedStyle(e).color")), surface) >= 4.5
    if width == DESKTOP:  # across both columns, like the Watchlist
        watch, mine = card(page, "Watchlist").bounding_box(), start.bounding_box()
        assert abs(watch["x"] - mine["x"]) <= 1 and abs(watch["width"] - mine["width"]) <= 1
    assert no_sideways_scroll(page)


@pytest.mark.parametrize("role, dev_line", [("viewer", False), ("trusted", False), ("reviewer", True)])
def test_b50_6_start_over_lists_what_this_role_has(open_as, role, dev_line):
    start = card(open_as(role), "Start over")
    expect(start).to_contain_text("whole decision history")
    expect(start).not_to_contain_text("everyone's chat")
    expect(start).to_contain_text("Kept: your display name.")
    expect(start.get_by_text("Your own copy of the Dev settings")).to_have_count(1 if dev_line else 0)


# --- B50.6: the embedding map's labels never overlap and stay inside the map --------------------------------------

LABELS = """() => { const svg = document.querySelector('.emap-box svg').getBoundingClientRect();
    return [...document.querySelectorAll('.emap-label')].map(t => { const r = t.getBoundingClientRect();
      return {x: r.left - svg.left, y: r.top - svg.top, width: r.width, height: r.height, svgW: svg.width,
              svgH: svg.height} }) }"""


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b50_6_map_labels_apart_and_inside(open_as, width):
    page = open_as(path="/dev", width=width)
    expect(page.locator(".emap-label")).to_have_count(3)
    boxes = page.evaluate(LABELS)
    for i, a in enumerate(boxes):
        assert a["x"] >= 0 and a["y"] >= 0 and a["x"] + a["width"] <= a["svgW"] and a["y"] + a["height"] <= a["svgH"]
        for b in boxes[i + 1:]:
            assert not overlaps(a, b), (a, b)


# --- B50.8: Pause the schedule can't be ticked where nothing is scheduled ------------------------------------------

def test_b50_8_pause_is_disabled_in_snapshot_mode_with_the_reason(open_as):
    page = open_as()
    pause = page.get_by_label("Pause the schedule")
    expect(pause).to_be_disabled()
    expect(pause).to_have_accessible_description(
        "Only in live mode: the snapshot never changes, so no check is scheduled to pause.")


def test_b50_8_pause_works_in_live_mode(browser: Browser, live_ui_url: str):
    ctx = browser.new_context(viewport={"width": DESKTOP, "height": 900})
    try:
        page = ctx.new_page()
        page.goto(live_ui_url + "/settings")
        pause = page.get_by_label("Pause the schedule")
        expect(pause).to_be_enabled()
        expect(pause).to_have_accessible_description("No scheduled check starts. Check now and Patch's check still work.")
    finally:
        ctx.close()


# --- B50.9: anyone but the owner, end to end: no channel anywhere, the in-Patch note, their own words --------------

@pytest.mark.parametrize("role", ["viewer", "reviewer"])
@pytest.mark.parametrize("width, scheme", SIZES)
def test_b50_9_settings_for_a_viewer_and_a_reviewer(open_as, browser_name, role, width, scheme):
    page = open_as(role, width=width, scheme=scheme)
    expect(page.get_by_test_id("in-patch-note")).to_have_text(NOTE)
    expect(page.get_by_role("checkbox", name=re.compile("Desktop notification|Email|Phone push"))).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile("Send test|Preview an alert"))).to_have_count(0)
    expect(page.get_by_role("heading", name="Delivery")).to_have_count(0)
    expect(page.locator("main .status-chip")).to_have_count(0)
    for name in ("SMTP", "ntfy", "notify-send", "backend/.env"):
        expect(page.get_by_role("main")).not_to_contain_text(name)
    assert no_sideways_scroll(page)
    shot(page, browser_name, f"settings-{role}-{width}-{scheme}")


@pytest.mark.parametrize("width, scheme", SIZES)
def test_b50_9_settings_and_dev_for_the_owner(open_as, browser_name, width, scheme):
    page = open_as(width=width, scheme=scheme)
    assert no_sideways_scroll(page)
    shot(page, browser_name, f"settings-owner-{width}-{scheme}")
    page = open_as(path="/dev", width=width, scheme=scheme)
    intro = page.get_by_test_id("owner-intro")
    page_bg = as_rgb(page, page.evaluate("getComputedStyle(document.body).backgroundColor"))
    assert contrast(as_rgb(page, intro.evaluate("e => getComputedStyle(e).color")), page_bg) >= 4.5
    assert no_sideways_scroll(page)
    shot(page, browser_name, f"dev-owner-{width}-{scheme}")


@pytest.mark.parametrize("width, scheme", SIZES)
def test_b50_9_dev_for_a_reviewer_and_none_for_a_viewer(open_as, browser_name, width, scheme):
    page = open_as("reviewer", path="/dev", width=width, scheme=scheme)
    expect(page.get_by_test_id("reviewer-note")).to_be_visible()
    expect(page.get_by_test_id("owner-intro")).to_have_count(0)
    expect(page.locator("main .status-chip")).to_have_count(0)
    assert no_sideways_scroll(page)
    shot(page, browser_name, f"dev-reviewer-{width}-{scheme}")
    page = open_as("viewer", path="/dev", width=width, scheme=scheme)
    expect(page.get_by_test_id("dev-not-yours")).to_be_visible()
    shot(page, browser_name, f"dev-viewer-{width}-{scheme}")


@pytest.mark.parametrize("role", ["viewer", "reviewer"])
def test_b50_9_the_dashboard_for_another_user_offers_no_test_alert(open_as, role):
    page = open_as(role, path="/")
    alerts = page.locator("section#recent-alerts")
    expect(alerts).to_contain_text("No alerts yet. The snapshot never changes, so no check finds any.")
    expect(alerts).not_to_contain_text("test alerts")


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) -----------------------------------

@scene
def b50_10_start_over_and_the_phone_save_bar(fx):
    page = fx("open_as")(width=PHONE, reduced=True)
    page.get_by_label("Minimum severity").select_option("LOW")
    expect(page.locator(".save-bar")).to_contain_text("Unsaved changes")
    card(page, "Start over").scroll_into_view_if_needed()
    still(page, "Start over and the phone's save bar")

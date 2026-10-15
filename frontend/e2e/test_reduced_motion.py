"""The shared reduced-motion check (DESIGN.md §7.2): with `prefers-reduced-motion: reduce` nothing moves, anywhere.

One place for every ticket's scene (review item 19): each scene drives one part of the app into the states that
would animate with normal motion, and `still()` checks that no CSS animation or transition runs. A ticket that adds
motion adds its scene here, not a test of its own. Each scene keeps its check id. The "normal motion does move"
checks stay with their tickets.
"""
import re

import pytest
from playwright.sync_api import Page, expect

from test_affected import set_stack
from test_chat import (
    OPTIONS, Q3, ask, has_face, head_bot, hold_chat, pick, release, send, to_alert, to_thinking, window)
from test_chat import open_chat as open_bubble
from test_chat_layout import ALERT_CVE, PIN, UNPIN, divider, head_button
from test_cves_page import open_cves  # noqa: F401 (fixture)
from test_dashboard import TILES, api, clean_state, confirm, open_dash, rows, tile  # noqa: F401 (fixtures)
from test_dashboard_charts import BY_PRODUCT, banner, chart
from test_decisions import FIXABLE
from test_dev import dev_page, run_search  # noqa: F401 (fixture)
from test_explain_levels import settings_group, switch
from test_fix_first import FIX_FIRST, VIEW, chip, fix_card, table_ids
from test_fix_first import open_chat as open_chat_by_key
from test_live import DONE, check_now_running, line, live_reset, open_live  # noqa: F401 (fixtures)
from test_live import release as release_refresh
from test_priority import open_settings  # noqa: F401 (fixture)
from test_research_web import ASK as WEB_ASK, details as web_details
from test_settings import settings_page  # noqa: F401 (fixture)
from test_shell import CURSOR_OPACITIES, WIDTHS_DURING_COLLAPSE, open_app  # noqa: F401 (fixture)
from test_snapshot_additions import RECENT, table
from test_watchlist import card, chip_button, open_watchlist, save  # noqa: F401 (fixture)

RUNNING = "document.getAnimations().map(a => a.animationName || a.transitionProperty || 'script animation')"


def still(page: Page, where: str = "") -> None:
    """The shared check: no CSS animation or transition is running on the page."""
    assert page.evaluate(RUNNING) == [], where


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    """Every scene starts from the defaults and leaves them (state, settings, decision history, dev settings)."""
    def reset():
        api(api_url, "/state/reset", "POST", {"confirm": "reset"})
        api(api_url, "/dev/settings", "PUT", api(api_url, "/dev/settings")["defaults"])

    reset()
    yield
    reset()


# --- The scenes, by ticket ---------------------------------------------------------------------------------------

def a02_10_shell(fx):
    page = fx("open_app")(reduced=True)
    assert page.evaluate(CURSOR_OPACITIES)["seen"] == ["1"]  # the cursor stays put
    widths = page.evaluate(WIDTHS_DURING_COLLAPSE)
    assert all(w == 78 for w in widths), widths  # jumps straight to the rail
    still(page, "Patch, the sidebar")


def a04_9_dashboard(fx):
    page = fx("open_dash")(reduced=True)
    chip_button(page, "Langflow").click()  # a reload must not animate either (the product filter, A15b)
    expect(page.locator(".chart").first.locator(".bar-row")).to_have_count(1)
    still(page, "after a reload")
    transforms = tile(page, TILES[2][0]).evaluate("""async el => { const seen = new Set();
        for (let i = 0; i < 10; i++) { seen.add(getComputedStyle(el).transform); await new Promise(r => setTimeout(r, 50)) }
        return [...seen] }""")
    assert transforms == ["none"]  # the KEV tile doesn't wiggle


def a04b_9_cves_page(fx):
    open_page = fx("open_cves")
    page = open_page(reduced=True)
    still(page, "the page")
    page.get_by_role("combobox", name="Severity").select_option("HIGH")
    expect(page).to_have_url(re.compile("severity=HIGH"))
    page.get_by_role("button", name=f"Mark {rows(page)[0]} fixed").click()
    confirm(page)
    expect(page.locator("table.cves tbody tr").first).to_be_visible()
    still(page, "after Mark fixed")
    still(open_page(width=400, reduced=True), "at phone width")


def a05_8_charts_and_banner(fx):
    page = fx("open_dash")(reduced=True)
    expect(banner(page).locator("svg.robot")).to_be_visible()
    expect(chart(page, BY_PRODUCT).locator(".fill").first).to_be_visible()
    still(page, "charts and banner")
    names = page.locator(".chart .fill, .hello .robot *").evaluate_all(
        "els => [...new Set(els.map(el => getComputedStyle(el).animationName))]")
    assert names == ["none"]
    # Bars are drawn at full length straight away (Patch in the banner: scene a06b_7).
    full = chart(page, BY_PRODUCT).locator(".fill").first.evaluate(
        "el => Math.abs(el.getBoundingClientRect().width - el.getBBox().width) < 0.6")
    assert full


def a06_8_chat(fx):
    page = fx("open_app")(reduced=True)
    still(page, "Patch on the button")
    chat = open_bubble(page)
    held = hold_chat(page)
    send(page, Q3)
    expect(head_bot(page)).to_have_class(re.compile("mood-thinking"))
    still(page, "no pop, no thinking motion")
    release(page, held)
    expect(head_bot(page)).to_have_class(re.compile("mood-happy"))
    still(page, "no waving")
    page.route("**/chat", lambda route: route.fulfill(
        status=502, headers={"Access-Control-Allow-Origin": "*"}, json={"error": {"code": "x", "message": "Down."}}))
    send(page, Q3)
    expect(head_bot(page)).to_have_class(re.compile("mood-alert"))
    still(page, "no shake")
    assert chat.evaluate("el => getComputedStyle(el).animationName") == "none"


def a06b_7_patch_variants(fx):
    """All 16 of Patch's animations stand still, each in a pose that keeps its face (arc eyes, wide eyes, ...)."""
    for option in range(4):
        page = fx("open_app")(reduced=True, init_script=pick(option))
        places = [page.locator(".patch-fab svg.robot"), page.locator(".hello svg.robot"),
                  page.locator(".side-card svg.robot")]
        for robot in places:
            expect(robot).to_have_attribute("data-variant", OPTIONS["idle"][option])
        still(page, f"idle {OPTIONS['idle'][option]}: the button, the banner, the snapshot card")
        has_face(places[0], OPTIONS["idle"][option])
        open_bubble(page)
        held = to_thinking(page)
        still(page, f"thinking {OPTIONS['thinking'][option]}")
        has_face(head_bot(page), OPTIONS["thinking"][option])
        release(page, held)
        expect(head_bot(page)).to_have_attribute("data-mood", "happy")
        still(page, f"happy {OPTIONS['happy'][option]}")
        has_face(head_bot(page), OPTIONS["happy"][option])
        to_alert(page)
        still(page, f"alert {OPTIONS['alert'][option]}")
        has_face(head_bot(page), OPTIONS["alert"][option])
        # The still pose shows every part: nothing is left at a keyframe's scale(0) or opacity 0.
        hidden = head_bot(page).evaluate("""el => [...el.querySelectorAll('*')].filter(c => {
            const s = getComputedStyle(c); return s.transform.startsWith('matrix(0, 0, 0, 0') || s.opacity === '0' })
            .length""")
        assert hidden == 0


def a07_8_chat_layout(fx):
    page = fx("open_app")(reduced=True, query=f"#cve={ALERT_CVE}")
    still(page, "the alert banner")
    page.keyboard.press("Control+k")
    expect(window(page)).to_be_visible()
    still(page, "no pop")
    window(page).get_by_role("group", name="Explain level").get_by_role("radio", name="Deep dive").check()
    still(page, "the explain-level switch's pills")
    head_button(page, "Make larger").click()
    still(page, "Make larger")
    head_button(page, PIN).click()
    expect(head_button(page, UNPIN)).to_be_visible()
    still(page, "the pin icon jumps to 0°")
    assert head_button(page, UNPIN).locator("svg").evaluate("el => getComputedStyle(el).transitionDuration") == "0s"
    divider(page).hover()
    divider(page).focus()
    page.keyboard.press("ArrowLeft")
    still(page, "the divider's colour")
    head_button(page, UNPIN).click()
    still(page, "Unpin")
    page.keyboard.press("Escape")
    expect(window(page)).to_have_count(0)
    still(page, "closed")


def a11_7_dev_page(fx):
    page = fx("dev_page")(reduced=True)
    page.get_by_label("Sources per search").fill("4")
    run_search(page)
    page.get_by_role("button", name="Show all").click()
    page.locator(".emap .hit").first.hover(force=True)
    page.get_by_role("button", name="Discard").hover()
    still(page, "the dev page")


def a13_7_settings(fx):
    page = fx("settings_page")(reduced=True)
    page.get_by_label("Minimum severity").select_option("LOW")
    page.get_by_role("button", name="Preview an alert (send nothing)").click()
    expect(page.locator(".push-preview")).to_be_visible()
    page.get_by_role("button", name="Discard").hover()
    still(page, "the settings page")


def a14_12_snapshot_additions(fx):
    page = fx("open_cves")(RECENT, reduced=True)
    page.get_by_role("combobox", name="Product").select_option(label="Langflow")
    # Wait for Langflow's rows: the page opens on every product's recent CVEs, which have possible matches too, and
    # styles read from rows React is replacing come back empty.
    expected = api(fx("api_url"), "/cves?product=langflow&published_since=2026-09-14&limit=25")["rows"]
    expect(table(page).locator("tbody tr td:first-child a")).to_have_text([r["id"] for r in expected])
    expect(table(page).locator(".chip.possible").first).to_be_visible()
    expect(page.locator(".epss-credit")).to_be_visible()
    still(page, "possible match, EPSS")
    moving = page.locator(".chip.possible, td.epss, .epss-credit, .freshness-notice").evaluate_all(
        "els => els.filter(el => { const s = getComputedStyle(el);"
        " return s.animationName !== 'none' || (s.transitionDuration.split(',').some(d => parseFloat(d) > 0)"
        " && s.transitionProperty !== 'none') })")
    assert moving == []


def a15_9_verdict(fx):
    open_page, open_stack = fx("open_cves"), fx("open_watchlist")  # first: their set-up resets the watchlist
    set_stack(fx("api_url"), langflow={"version": "99.0.0"})
    page = open_page("?product=langflow", reduced=True)
    page.get_by_role("combobox", name="Verdict").select_option("not_affected")
    # The filter reloads the table: a row read before that may be an unfiltered one with no suggestion (CI race, run #62).
    expect(page).to_have_url(re.compile(r"verdict=not_affected"))
    first_suggestion = page.locator("table.cves tbody tr").first.get_by_role(
        "button", name=re.compile(r"Suggested by the version check$"))
    expect(first_suggestion).to_be_visible()
    first_suggestion.click()
    expect(page.get_by_role("dialog")).to_be_visible()
    still(page, "the decision dialog (A16b)")
    confirm(page)
    expect(page.locator("table.cves tbody tr").first).to_be_visible()
    still(page, "after the decision")
    settings = open_stack(reduced=True)  # the watchlist's fields, on Settings since A15b
    card(settings).get_by_label("Dify", exact=True).check()
    card(settings).get_by_role("group", name="Langflow").get_by_label("Internet-facing").check()
    save(settings)
    still(settings, "the watchlist card")


def a15b_8_watchlist(fx):
    open_board, open_stack = fx("open_dash"), fx("open_watchlist")
    dash = open_board(reduced=True)
    for name in ("Langflow", "Ollama", "All"):
        chip_button(dash, name).click()
        expect(chip_button(dash, name)).to_have_attribute("aria-pressed", "true")
        still(dash, f"the product filter at {name}")
    settings = open_stack(reduced=True)
    card(settings).get_by_label("vLLM", exact=True).check()
    expect(card(settings).get_by_role("group", name="vLLM")).to_be_visible()
    still(settings, "a new product's fields")
    card(settings).get_by_role("group", name="Ollama").get_by_label("Version").fill("latest")
    settings.get_by_role("button", name="Save changes").click()
    expect(card(settings).get_by_role("alert")).to_be_visible()
    still(settings, "the card's error")


def a16_12_priority(fx):
    open_page, open_board, open_policy = fx("open_cves"), fx("open_dash"), fx("open_settings")  # before set_stack
    set_stack(fx("api_url"), langflow={"internet_facing": True, "version": "99.0.0"})
    page = open_page(reduced=True)
    expect(page.locator("table.cves .chip.priority").first).to_be_visible()
    expect(page.locator("table.cves .overdue").first).to_be_visible()
    still(page, "priority chips, overdue")
    dash = open_board(reduced=True)
    expect(dash.locator(".top-cves .chip.priority").first).to_be_visible()
    still(dash, "the Top 5")
    settings = open_policy(reduced=True)
    settings.get_by_label("Urgent", exact=True).fill("60")
    expect(settings.get_by_role("alert").filter(has_text="urgent ≤ high")).to_be_visible()
    still(settings, "the policy card's error")


def a16b_13_decisions(fx):
    page = fx("open_cves")("?product=langflow&kev=1", reduced=True)
    page.get_by_role("button", name=f"Accept the risk of {FIXABLE}", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    still(page, "the decision dialog")
    page.keyboard.press("Escape")
    page.get_by_role("button", name=f"Mark {FIXABLE} not affected", exact=True).click()
    still(page, "the not-affected dialog")


def a18_6_fix_first(fx):
    page = fx("open_cves")(VIEW, reduced=True)
    open_chat_by_key(page)
    still(page, "the chat with the page context")
    answer = ask(page, FIX_FIRST)
    fix_card(answer)
    still(page, "the prioritise card")
    cve = table_ids(page, 1)[0]
    page.get_by_role("button", name=f"Ask about this: {cve}").click()
    expect(chip(page)).to_contain_text(cve)
    still(page, "the selected row")


def a19_6_explain_levels(fx):
    page = fx("open_app")(reduced=True)
    open_bubble(page)
    for name in ("Simple", "Deep dive", "Normal"):
        switch(page).get_by_role("radio", name=name).check()
        still(page, f"the switch at {name}")
    page.get_by_role("button", name="Settings", exact=True).click()
    settings_group(page).get_by_role("radio", name="Simple").check()
    still(page, "the saved level on Settings")


def b08_13_research_web(fx):
    page = fx("open_app")(reduced=True)
    open_bubble(page)
    answer = ask(page, WEB_ASK)
    web_details(answer, "Tool calls")
    expect(answer.locator(".research-card")).to_be_visible()
    still(page, "the research_web card")
    answer.get_by_role("tab", name="Sources", exact=False).click()
    expect(answer.locator(".source .chip.web-unverified")).to_have_count(3)
    still(page, "the web sources")


def b02_9_check_now(fx):
    page = fx("open_live")(reduced=True)
    held = check_now_running(page)  # the spinner is on screen, and must stand still
    still(page, "Check now running")
    release_refresh(page, held)
    expect(line(page)).to_have_text(DONE)
    still(page, "the result line")


def b21_9_proposal_card(fx):
    page = fx("open_app")(reduced=True)
    open_bubble(page)
    card = ask(page, "Mark CVE-2024-8309 as fixed").locator(".proposal-card")
    expect(card).to_be_visible()
    still(page, "the proposal card")
    card.get_by_role("button", name="Edit", exact=True).click()
    still(page, "the edit form")
    card.get_by_role("button", name="Back", exact=True).click()
    card.get_by_role("button", name="Approve", exact=True).click()
    expect(card.locator("output.proposal-line")).to_contain_text("Done:")
    still(page, "the done line")


SCENES = {f.__name__: f for f in (
    a02_10_shell, a04_9_dashboard, a04b_9_cves_page, a05_8_charts_and_banner, a06_8_chat, a06b_7_patch_variants,
    a07_8_chat_layout, a11_7_dev_page, a13_7_settings, a14_12_snapshot_additions, a15_9_verdict, a15b_8_watchlist,
    a16_12_priority, a16b_13_decisions, a18_6_fix_first, a19_6_explain_levels, b02_9_check_now,
    b08_13_research_web, b21_9_proposal_card,
)}


@pytest.mark.parametrize("scene", SCENES)
def test_reduced_motion_nothing_moves(request, browser, scene):  # browser: run in each browser of the run
    SCENES[scene](request.getfixturevalue)

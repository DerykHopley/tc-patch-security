"""Browser check (seam 3) for the page for one CVE: /cves/CVE-… (B35, #85). Check ids: B35.n.

Opened from the list, the dashboard's Top 5, an alert and the chat; Back returns to the list in place; the actions
work on the page; an unknown id says "No such CVE". Light and dark, phone and desktop, keyboard, reduced motion.
Runs in Firefox and Chromium (run.sh). Expected values come from the backend's API (GET /cves/{id}, tested on its own in
backend/tests/test_cve_page.py) and from docs/design/DESIGN.md §5.15.
"""
import re
from urllib.parse import urlparse

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from test_chat import ask, window
from test_dashboard import DESKTOP, PHONE, SHOTS, api, clean_state, confirm  # noqa: F401 (fixture)
from test_shell import contrast
from reduced_motion import scene, still

CVE = "CVE-2025-3248"  # Langflow: watched, open, critical, in KEV, fixed in 1.3.0, OWASP A05
NOT_WATCHED = "CVE-2026-109311"  # vLLM: not on the default watchlist
UNKNOWN = "CVE-1999-0001"


@pytest.fixture
def open_at(browser: Browser, ui_url: str, clean_state):
    """Opens the app at a path in a fresh context and waits for the page title."""
    contexts = []

    def _open(path: str, width=DESKTOP, scheme="light", reduced=False) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(ui_url + path)
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        page.evaluate("document.fonts.ready.then(() => null)")  # late web fonts move the layout (CI race)
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def title(page: Page) -> Locator:
    return page.get_by_role("heading", level=1)


def assessment(page: Page) -> Locator:
    return page.get_by_role("region", name="Your assessment")


def on_cve_page(page: Page, cve: str) -> None:
    expect(title(page)).to_have_text(cve)
    expect(assessment(page)).to_be_visible()
    assert page.evaluate("location.pathname") == f"/cves/{cve}"


def next_page(page: Page) -> None:
    """The list's second page of rows, once its rows are in (the pager's words change before they arrive)."""
    first = page.locator("table.cves tbody tr").first.locator(".cve-cell a").first
    expect(first).to_be_visible()
    before = first.inner_text()
    page.get_by_role("button", name="Next page").click()
    expect(page.locator(".pager .meta")).to_contain_text("26–")
    expect(first).not_to_have_text(before)


def no_sideways_scroll(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


# --- B35.10: the page holds everything about one CVE ---------------------------------------------------------------

def test_b35_10_the_page_has_the_full_summary_facts_assessment_and_links(open_at, api_url):
    d = api(api_url, f"/cves/{CVE}")
    page = open_at(f"/cves/{CVE}")
    on_cve_page(page, CVE)
    expect(page.locator(".crumb-path")).to_have_text("Pages / CVEs")
    expect(page.get_by_role("navigation", name="Pages").get_by_role("button", name="CVEs")).to_have_attribute(
        "aria-current", "page")
    head = page.get_by_role("region", name=CVE)
    expect(head).to_contain_text(d["description"])  # in full, not cut to two lines
    expect(head).to_contain_text("Langflow")
    expect(head.locator(".chip.kev")).to_have_text("KEV")
    expect(head.get_by_role("link", name="NVD")).to_have_attribute("href", f"https://nvd.nist.gov/vuln/detail/{CVE}")
    expect(head.get_by_role("link", name="OSV.dev")).to_have_attribute("href", f"https://osv.dev/vulnerability/{CVE}")
    facts = page.get_by_role("region", name="Facts")
    expect(facts).to_contain_text(d["owasp"]["title"])
    expect(facts).to_contain_text("OWASP Top 10 2025 (web applications)")
    expect(facts).to_contain_text(f"KEV deadline {d['kev']['deadline']}")
    expect(facts).to_contain_text("percentile")
    versions = page.get_by_role("region", name="Product and versions")
    expect(versions).to_contain_text("every version before 1.3.0")
    a = assessment(page)
    expect(a).to_contain_text("Open")
    expect(a.locator(".chip.priority")).to_be_visible()
    expect(a).to_contain_text(d["row"]["due_date"])
    expect(a.locator(".chip.verdict")).to_be_visible()
    expect(page.get_by_role("region", name="Decision history")).to_contain_text("No decisions yet.")


def test_b35_10_a_cve_off_the_watchlist_has_no_status_actions(open_at):
    page = open_at(f"/cves/{NOT_WATCHED}")
    on_cve_page(page, NOT_WATCHED)
    expect(page.get_by_role("region", name=NOT_WATCHED).locator(".chip.not-watched")).to_have_text(
        "Not on your watchlist")
    a = assessment(page)
    expect(a.get_by_role("button", name=re.compile("^Mark "))).to_have_count(0)
    expect(a.get_by_role("button", name=f"Ask Patch about {NOT_WATCHED}")).to_be_visible()
    expect(a.get_by_role("link", name=re.compile("^Watch vLLM in Settings"))).to_be_visible()
    expect(page.get_by_role("region", name="Decision history")).to_have_count(0)


# --- B35.11: an unknown id says so, with a link back to the list ---------------------------------------------------

@pytest.mark.parametrize("path, shown", [(UNKNOWN, UNKNOWN), ("%3Cimg%20src%3Dx%3E", "<IMG SRC=X>")])
def test_b35_11_an_unknown_or_malformed_id_says_no_such_cve(open_at, path, shown):
    page = open_at(f"/cves/{path}")
    missing = page.get_by_role("region", name="No such CVE")
    expect(missing).to_contain_text(f"{shown} isn't in Patch's data.")  # shown as text, never as markup
    expect(page.locator("img[src=x]")).to_have_count(0)
    missing.get_by_role("link", name="Back to the CVEs list").click()
    expect(page.locator("table.cves tbody tr").first).to_be_visible()
    assert page.evaluate("location.pathname") == "/cves"


# --- B35.12: opened from the list; Back returns to the list in place ------------------------------------------------

def test_b35_12_from_the_list_and_back_to_the_same_filters_page_and_scroll(open_at):
    page = open_at("/cves?severity=HIGH")
    next_page(page)
    row = page.locator("table.cves tbody tr").nth(20)
    row.scroll_into_view_if_needed()
    cve = row.locator(".cve-cell a").first.inner_text()
    y = page.evaluate("window.scrollY")
    assert y > 200
    row.get_by_role("link", name=cve).click()
    on_cve_page(page, cve)
    assert page.evaluate("window.scrollY") == 0  # a new page starts at the top
    page.go_back()
    expect(page.locator(".pager .meta")).to_contain_text("26–")  # the same page of rows
    expect(page.locator("table.cves tbody tr").nth(20).locator(".cve-cell a").first).to_have_text(cve)
    assert "severity=HIGH" in page.url
    page.wait_for_function(f"Math.abs(window.scrollY - {y}) < 40", timeout=5000)  # the same scroll


def test_b35_12_the_page_back_link_returns_to_the_list_in_place_too(open_at):
    page = open_at("/cves?severity=HIGH")
    next_page(page)
    first = page.locator("table.cves tbody tr").first.locator(".cve-cell a").first
    cve = first.inner_text()
    first.click()
    on_cve_page(page, cve)
    page.get_by_role("link", name="CVEs on your watchlist").click()
    expect(page.locator(".pager .meta")).to_contain_text("26–")
    assert "severity=HIGH" in page.url
    page.go_forward()  # Back was a real step back: forward returns to the CVE
    on_cve_page(page, cve)


def test_b35_12_the_back_link_from_a_shared_link_opens_the_list(open_at):
    page = open_at(f"/cves/{CVE}")
    page.get_by_role("link", name="CVEs on your watchlist").click()
    expect(page.locator("table.cves tbody tr").first).to_be_visible()
    assert page.evaluate("location.pathname") == "/cves"


def test_b35_12_from_the_dashboards_top_5(open_at):
    page = open_at("/")
    link = page.locator(".top-cves li").first.locator("a.cve-id")
    cve = link.inner_text()
    link.click()
    on_cve_page(page, cve)
    page.go_back()
    expect(page.locator(".top-cves li").first).to_be_visible()


# --- B35.13: opened from an alert ------------------------------------------------------------------------------------

def test_b35_13_an_alerts_link_opens_its_cve_page(open_at, api_url):
    # The notification's link (a test alert's, recorded only). The dashboard's "Recent alerts" entry links to the
    # same page: B04.12 in test_alerts_panel.py, on the live pair, where real alerts are sent.
    sent = api(api_url, "/alerts/test", "POST", {"channel": "preview"})
    path = urlparse(sent["alert"]["click"]).path
    cve = path.rsplit("/", 1)[1]
    assert path == f"/cves/{cve}"
    page = open_at(path)
    on_cve_page(page, cve)


# --- B35.14: opened from a chat answer and a tool card; the chat stays open ------------------------------------------

def test_b35_14_a_cve_id_in_an_answer_and_on_its_tool_card_opens_the_page(open_at):
    page = open_at("/")
    page.keyboard.press("Control+k")
    answer = ask(page, f"Explain {CVE} and how to defend against it.")
    link = answer.locator(".answer-text").get_by_role("link", name=CVE).first
    expect(link).to_have_attribute("href", f"/cves/{CVE}")
    expect(link).not_to_have_attribute("target", "_blank")
    link.click()
    on_cve_page(page, CVE)
    expect(window(page)).to_be_visible()  # the chat stays open
    page.go_back()
    expect(title(page)).to_have_text("Dashboard")
    answer.get_by_role("button", name=re.compile("^Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    answer.locator(".cve-card").get_by_role("link", name=CVE).click()
    on_cve_page(page, CVE)


def test_b35_14_the_chat_is_told_the_cve_of_the_page(open_at):
    page = open_at(f"/cves/{CVE}")
    page.keyboard.press("Control+k")
    expect(window(page).locator(".context-chip")).to_contain_text(CVE)


# --- B35.15: the actions work on the page -----------------------------------------------------------------------------

def test_b35_15_mark_fixed_then_reopen_on_the_page(open_at, api_url):
    page = open_at(f"/cves/{CVE}")
    a = assessment(page)
    a.get_by_role("button", name=f"Mark {CVE} fixed").click()
    page.get_by_role("dialog").get_by_label(re.compile("^Note")).fill("Upgraded to 1.3.0")
    confirm(page)
    expect(a.locator(".status")).to_have_text("Fixed")
    expect(a.locator(".chip.priority")).to_have_count(0)  # priority and due date are for open CVEs (B33 seam)
    history = page.get_by_role("region", name="Decision history")
    expect(history.locator("li")).to_have_count(1)
    expect(history).to_contain_text("Upgraded to 1.3.0")
    assert api(api_url, f"/cves/{CVE}")["row"]["status"] == "fixed"
    a.get_by_role("button", name=f"Reopen {CVE}").click()
    confirm(page)
    expect(a.locator(".status")).to_have_text("Open")
    expect(a.locator(".chip.priority")).to_be_visible()  # back with the reopen
    expect(history.locator("li")).to_have_count(2)


def test_b35_15_accept_risk_and_not_affected_open_their_dialogs(open_at):
    page = open_at(f"/cves/{CVE}")
    a = assessment(page)
    a.get_by_role("button", name=f"Accept the risk of {CVE}").click()
    expect(page.get_by_role("dialog")).to_contain_text(f"Accept the risk of {CVE}")
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)
    a.get_by_role("button", name=f"Mark {CVE} not affected").click()
    confirm(page, "Component not present")
    expect(a.locator(".status")).to_have_text("Not affected")


def test_b35_15_ask_patch_asks_about_this_cve(open_at):
    page = open_at(f"/cves/{CVE}")
    assessment(page).get_by_role("button", name=f"Ask Patch about {CVE}").click()
    expect(window(page).locator(".message.user")).to_have_text(f"Explain {CVE} and how to defend against it.")


def test_b35_15_keyboard_reaches_the_back_link_links_and_actions_with_visible_focus(open_at):
    page = open_at(f"/cves/{CVE}")
    seen = []
    for _ in range(40):
        page.keyboard.press("Tab")
        name = page.evaluate("document.activeElement.getAttribute('aria-label') || document.activeElement.innerText")
        seen.append(name.strip())
        if name.strip() == f"Mark {CVE} fixed":
            outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
            assert outline != "none"
            break
    assert any("CVEs on your watchlist" in s for s in seen), seen
    assert "NVD" in seen and "OSV.dev" in seen, seen
    assert seen[-1] == f"Mark {CVE} fixed", seen
    page.keyboard.press("Enter")
    expect(page.get_by_role("dialog")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.get_by_role("dialog")).to_have_count(0)


# --- B35.16: light and dark, phone and desktop -----------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b35_16_light_dark_phone_and_desktop(open_at, browser_name, width, scheme):
    page = open_at(f"/cves/{CVE}", width=width, scheme=scheme, reduced=True)
    on_cve_page(page, CVE)
    assert no_sideways_scroll(page)
    for chip in (page.locator(".cve-head .chip.kev"), assessment(page).locator(".chip.priority")):
        colour, fill = chip.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
        assert contrast(colour, fill) >= 4.5, (colour, fill)
    back = page.get_by_role("link", name="CVEs on your watchlist")
    page_bg = page.evaluate("getComputedStyle(document.documentElement).getPropertyValue('--bg').trim()")
    assert contrast(back.evaluate("el => getComputedStyle(el).color"), page_bg) >= 4.5
    text = page.locator(".cve-description")
    colour = text.evaluate("el => getComputedStyle(el).color")
    surface = page.locator(".cve-head").evaluate("el => getComputedStyle(el).backgroundColor")
    assert contrast(colour, surface) >= 4.5
    for button in assessment(page).get_by_role("button").all():
        b = button.bounding_box()
        assert b and b["x"] >= 0 and b["x"] + b["width"] <= width
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b35-{browser_name}-{width}-{scheme}.png", full_page=True)
    # the unknown id too
    page.goto(page.url.replace(CVE, UNKNOWN))
    expect(page.get_by_role("region", name="No such CVE")).to_be_visible()
    assert no_sideways_scroll(page)


def test_b35_16_the_pinned_chat_leaves_one_column(open_at):
    page = open_at(f"/cves/{CVE}", reduced=True)
    page.keyboard.press("Control+k")
    window(page).get_by_role("button", name="Make larger").click()
    window(page).get_by_role("button", name="Pin: dock the chat beside the page").click()
    expect(window(page).get_by_role("button", name="Unpin: float the chat over the page")).to_be_visible()
    assert no_sideways_scroll(page)
    cols = page.locator(".cve-grid").evaluate("el => getComputedStyle(el).gridTemplateColumns.split(' ').length")
    assert cols == 1


# --- B35.17: motion: the cards fade up once, like the CVEs page's card -----------------------------------------------

def test_b35_17_the_cards_fade_up(open_at):
    page = open_at(f"/cves/{CVE}")
    on_cve_page(page, CVE)
    timing = "el => [getComputedStyle(el).animationName, getComputedStyle(el).animationDuration, " \
             "getComputedStyle(el).animationDelay]"
    assert page.get_by_role("region", name=CVE).evaluate(timing) == ["fade-up", "0.45s", "0s"]
    assert assessment(page).evaluate(timing) == ["fade-up", "0.45s", "0s"]
    assert page.get_by_role("region", name="Facts").evaluate(timing) == ["fade-up", "0.45s", "0.12s"]


@scene
def b35_17_cve_page(fx):
    page = fx("open_at")(f"/cves/{CVE}", reduced=True)
    expect(assessment(page)).to_be_visible()
    still(page, "the CVE page")
    assessment(page).get_by_role("button", name=f"Mark {CVE} fixed").click()
    expect(page.get_by_role("dialog")).to_be_visible()
    still(page, "the decision dialog on the CVE page")
    page.keyboard.press("Escape")
    page.goto(page.url.replace(CVE, UNKNOWN))
    expect(page.get_by_role("region", name="No such CVE")).to_be_visible()
    still(page, "No such CVE")

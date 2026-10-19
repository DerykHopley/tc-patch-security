"""Browser check (seam 3) for the CVE list and page polish (B44, #94). Check ids: B44.n (B44.1 is the API test in
backend/tests/test_cve_polish.py; B44.2 to B44.5 are the unit tests in src/tips.test.ts, src/decisionWho.test.ts and
src/cveView.test.ts).

Tooltips work by mouse, keyboard and touch (DESIGN.md §5.18): the column headings that need explaining, the OWASP code
and the "Possible match" chip. On a phone the filters fold behind "Filters (n on)". The KEV deadline shows once per
row. Your own decisions say "by you". At 390px and 1440px, light and dark; runs in Firefox and Chromium (run.sh).
"""
import re

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from test_cves_page import pin
from test_dashboard import SHOTS, api, clean_state  # noqa: F401 (fixture)
from test_shell import contrast, no_sideways_scroll

PHONE = {"width": 390, "height": 844}
DESKTOP = {"width": 1440, "height": 900}
KEV_CVE = "CVE-2025-3248"  # Langflow, open, in KEV; the default policy adopts the KEV deadline 2025-05-26 as due date
TIPPED = {"Priority": "fixed rules", "Due": "Your due date", "OWASP": "OWASP Top 10 category", "EPSS": "Exploit Prediction",
          "Verdict": "version check"}
PLAIN = ["CVE", "Product", "Severity", "Published", "Status"]


@pytest.fixture
def open_page(browser: Browser, ui_url: str, clean_state):
    contexts = []

    def _open(path="/cves", viewport=DESKTOP, scheme="light", touch=False) -> Page:
        ctx = browser.new_context(viewport=viewport, color_scheme=scheme, has_touch=touch, reduced_motion="reduce")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(f"{ui_url}{path}")
        if path.startswith("/cves?") or path == "/cves":
            expect(page.locator("table.cves tbody tr").first).to_be_visible()
        page.evaluate("document.fonts.ready.then(() => null)")  # late web fonts move the layout (CI race)
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def heading(page: Page, name: str) -> Locator:
    return page.locator("table.cves thead th").filter(has_text=re.compile(rf"^{name}$", re.I))


def tip(page: Page) -> Locator:
    return page.get_by_role("tooltip")  # the open one: closed tips are hidden


def inside_window(page: Page, loc: Locator) -> None:
    b = loc.bounding_box()
    vw = page.evaluate("document.documentElement.clientWidth")
    vh = page.evaluate("innerHeight")
    assert b and b["x"] >= 0 and b["y"] >= 0 and b["x"] + b["width"] <= vw and b["y"] + b["height"] <= vh, b


def tip_contrast(loc: Locator) -> float:
    fg, bg = loc.evaluate("el => { const s = getComputedStyle(el); return [s.color, s.backgroundColor] }")
    return contrast(fg, bg)


def possible_match_cve(api_url: str) -> str:
    rows = api(api_url, "/cves?status=all&limit=200&product=langflow")["rows"]
    return next(r["id"] for r in rows if r["possible_match"])


# --- B44.6: the headings' tips by mouse, keyboard and touch; no underline where there's nothing to explain --------

def test_b44_6_heading_tips_by_mouse_and_keyboard(open_page):
    page = open_page()
    for name, words in TIPPED.items():
        anchor = heading(page, name).locator(".tip-anchor")
        anchor.hover()
        expect(tip(page)).to_contain_text(words)
        inside_window(page, tip(page))
        expect(anchor).to_have_accessible_description(re.compile(words))  # read by screen readers too
    page.mouse.move(5, 5)
    expect(tip(page)).to_have_count(0)  # moving away closes it
    # Keyboard: Tab to the Priority heading shows its tip; Esc closes it and keeps the focus
    page.locator(".filters").get_by_role("checkbox", name="In CISA KEV only").focus()
    anchor = heading(page, "Priority").locator(".tip-anchor")
    for _ in range(5):
        page.keyboard.press("Tab")
        if anchor.evaluate("el => el === document.activeElement"):
            break
    expect(anchor).to_be_focused()
    expect(tip(page)).to_contain_text("fixed rules")
    ring = anchor.evaluate("el => getComputedStyle(el).outlineStyle")
    assert ring != "none", ring  # the global focus ring (DESIGN.md §10)
    page.keyboard.press("Escape")
    expect(tip(page)).to_have_count(0)
    expect(anchor).to_be_focused()
    page.keyboard.press("Tab")  # on to the next tipped heading
    expect(tip(page)).to_contain_text("Your due date")


def test_b44_6_heading_tips_by_touch(open_page):
    page = open_page(touch=True)
    anchor = heading(page, "EPSS").locator(".tip-anchor")
    anchor.tap()
    expect(tip(page)).to_contain_text("Exploit Prediction")
    anchor.tap()  # a second tap closes it
    expect(tip(page)).to_have_count(0)
    anchor.tap()
    expect(tip(page)).to_be_visible()
    page.locator(".cves-card h2").tap()  # a tap elsewhere closes it
    expect(tip(page)).to_have_count(0)


def test_b44_6_only_headings_with_a_tip_are_underlined(open_page):
    page = open_page()
    for name in TIPPED:
        style = heading(page, name).locator(".tip-anchor").evaluate(
            "el => getComputedStyle(el).textDecorationLine + ' ' + getComputedStyle(el).textDecorationStyle")
        assert style == "underline dotted", (name, style)
    for name in PLAIN:
        th = heading(page, name)
        expect(th.locator(".tip-anchor, abbr")).to_have_count(0)
        assert th.evaluate("el => getComputedStyle(el).textDecorationLine") == "none", name


# --- B44.7: the OWASP code's tip names the category and its list ---------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("viewport", [DESKTOP, PHONE], ids=["1440", "390"])
def test_b44_7_owasp_tip_by_mouse_keyboard_and_touch(open_page, browser_name, viewport, scheme):
    page = open_page(viewport=viewport, scheme=scheme, touch=viewport is PHONE)
    row = page.locator("table.cves tbody tr").filter(has=page.get_by_role("link", name=KEV_CVE, exact=True))
    code = row.locator('td[data-label="OWASP"] .tip-anchor')
    expect(code).to_have_text("A05")
    want = "A05:2025 Injection, from the OWASP Top 10 2025 (web applications)"
    if viewport is PHONE:
        code.tap()
    else:
        code.hover()
    expect(tip(page)).to_have_text(want)
    inside_window(page, tip(page))
    assert tip_contrast(tip(page)) >= 4.5
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b44-owasp-tip-{browser_name}-{viewport['width']}-{scheme}.png")
    assert no_sideways_scroll(page)
    page.keyboard.press("Escape")
    expect(tip(page)).to_have_count(0)
    code.focus()  # keyboard: focus shows it
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    expect(code).to_be_focused()
    expect(tip(page)).to_have_text(want)


# --- B44.8: "Possible match" says what it means ---------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b44_8_possible_match_tip_on_the_list_and_the_page(open_page, api_url, browser_name, scheme):
    cve = possible_match_cve(api_url)
    page = open_page(f"/cves/{cve}", viewport=PHONE, scheme=scheme, touch=True)
    chip = page.locator(".chip.possible")
    expect(chip).to_have_text("Possible match")
    chip.tap()
    expect(tip(page)).to_contain_text("matched the product on the description's text, not on NVD's product id (CPE)")
    inside_window(page, tip(page))
    assert tip_contrast(tip(page)) >= 4.5
    assert tip_contrast(chip) >= 4.5  # the chip keeps its own look as a button
    expect(chip).to_have_css("text-decoration-line", "none")  # a chip already looks like a thing: no underline
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b44-possible-tip-{browser_name}-{scheme}.png")
    desk = open_page(f"/cves?product=langflow&status=all&since=2026-09-14", scheme=scheme)
    first = desk.locator("table.cves .chip.possible").first
    first.hover()
    expect(tip(desk)).to_contain_text("Check before acting.")


# --- B44.9: on a phone the filters fold behind "Filters (n on)" -----------------------------------------------------

def toggle(page: Page) -> Locator:
    return page.get_by_role("button", name=re.compile(r"^Filters \(\d+ on\)$"))


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b44_9_phone_filters_fold(open_page, browser_name, scheme):
    page = open_page(viewport=PHONE, scheme=scheme)
    expect(toggle(page)).to_have_text("Filters (0 on)")
    expect(toggle(page)).to_have_attribute("aria-expanded", "false")
    expect(page.get_by_role("combobox", name="Status")).to_be_hidden()
    expect(page.locator(".cves-card .filters .meta")).to_contain_text("490 CVEs")  # the count stays in view
    # the first row starts high: the folded filters take one line, not a third of the screen
    first = page.locator("table.cves tbody tr").first.bounding_box()
    assert first and first["y"] < PHONE["height"] / 4, first
    b = toggle(page).bounding_box()
    assert b and b["height"] >= 24, b  # a target big enough to tap
    fg, bg = toggle(page).evaluate("el => { const s = getComputedStyle(el); return [s.color, s.backgroundColor] }")
    assert contrast(fg, bg) >= 4.5
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b44-filters-folded-{browser_name}-{scheme}.png")
    # Keyboard: Enter opens it, the controls follow in Tab order
    toggle(page).focus()
    page.keyboard.press("Enter")
    expect(toggle(page)).to_have_attribute("aria-expanded", "true")
    page.keyboard.press("Tab")
    expect(page.get_by_role("combobox", name="Product")).to_be_focused()
    page.get_by_role("combobox", name="Severity").select_option("HIGH")
    expect(toggle(page)).to_have_text("Filters (1 on)")
    assert no_sideways_scroll(page)
    page.screenshot(path=SHOTS / f"b44-filters-open-{browser_name}-{scheme}.png")
    toggle(page).click()  # and closes again; the filter stays on
    expect(page.get_by_role("combobox", name="Severity")).to_be_hidden()
    expect(toggle(page)).to_have_text("Filters (1 on)")
    page.reload()  # a link with filters says how many before you open it
    expect(toggle(page)).to_have_text("Filters (1 on)")


def test_b44_9_desktop_filters_unchanged(open_page):
    page = open_page("/cves?kev=1")
    expect(toggle(page)).to_be_hidden()
    for name in ("Product", "Severity", "Status", "Verdict"):
        expect(page.get_by_role("combobox", name=name)).to_be_visible()
    expect(page.get_by_role("checkbox", name="In CISA KEV only")).to_be_checked()
    # one row, as before B44: the controls and the count share the filter line
    tops = page.locator(".filters select").evaluate_all("els => els.map(e => Math.round(e.getBoundingClientRect().top))")
    assert len(set(tops)) == 1, tops
    pin(page)  # beside the pinned chat a desktop keeps its filters open (the fold goes by the window's width)
    expect(toggle(page)).to_be_hidden()
    expect(page.get_by_role("combobox", name="Status")).to_be_visible()


# --- B44.10: the KEV deadline shows once in a row --------------------------------------------------------------------

def test_b44_10_the_kev_deadline_once_per_row(open_page):
    page = open_page()
    row = page.locator("table.cves tbody tr").filter(has=page.get_by_role("link", name=KEV_CVE, exact=True))
    expect(row.locator(".due-cell")).to_contain_text("2025-05-26")
    expect(row.locator(".due-cell")).to_contain_text("KEV deadline")
    assert "2025-05-26" not in (row.locator(".chip.kev").get_attribute("title") or "")
    html = row.evaluate("el => el.outerHTML")
    assert html.count("2025-05-26") == 1, "the KEV date shows once, in the Due cell"


# --- B44.11: your own decisions say "by you" ----------------------------------------------------------------------

def test_b44_11_history_says_by_you(open_page, api_url):
    api(api_url, f"/cves/{KEV_CVE}", "PATCH", {"status": "fixed", "note": "Upgraded"})
    page = open_page(f"/cves/{KEV_CVE}")
    history = page.get_by_role("region", name="Decision history")
    # the last record is this one (clean_state's own reopenings may come before it: they're yours too)
    expect(history.locator("li").last).to_contain_text("Fixed · Upgraded · by you, on the CVEs page")
    expect(history).not_to_contain_text("by owner")

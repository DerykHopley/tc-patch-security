"""Browser check for the dashboard polish from the page review. Check ids: B43.n (#93; item 6 closes #25).

Runs in Firefox and Chromium (run.sh). The snapshot pair for most checks; the live pair (test_live.py's fixture) for
"See the N new CVEs". Expected numbers come from the backend's API (backend/tests/test_dashboard.py,
test_new_until_seen.py B43.1, B43.2); expected looks from docs/design/DESIGN.md §5.4, §5.8, §5.9, §5.10, §5.17, §6.1.
"""
import pathlib
import re

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from reduced_motion import scene, still
from test_dashboard import api, clean_state, open_dash  # noqa: F401 (fixtures)
from test_live import NEW, card as freshness, live_reset, open_live  # noqa: F401 (fixtures)
from test_shell import contrast, eventually, no_sideways_scroll

SHOTS = pathlib.Path(__file__).parent / "screenshots"
PHONE, DESKTOP = 390, 1440
OWASP = "Open CVEs by OWASP Top 10 (web, 2025)"
SOURCES = re.compile(r"^Sources and licences \(\d+\)$")


def box(loc: Locator) -> dict:
    b = loc.bounding_box()
    assert b, loc
    return b


def patch_box(page: Page) -> dict:
    """Patch's button with the robot on it, whose head reaches 8px above it (DESIGN.md §6.1)."""
    fab, bot = box(page.locator(".patch-fab")), box(page.locator(".patch-fab svg.robot"))
    top = min(fab["y"], bot["y"])
    return {"x": fab["x"], "y": top, "width": fab["width"], "height": fab["y"] + fab["height"] - top}


def overlaps(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"]
            and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"])


def sources(page: Page) -> Locator:
    return freshness(page).locator("details.sources")


# --- B43.5 (item 1): on a phone the product filter sits above the tiles; on a desktop beside the charts ------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b43_5_the_product_filter_comes_before_the_tiles(open_dash, width):
    page = open_dash(width=width, reduced=True)
    watch, tiles = page.get_by_role("region", name="Watchlist", exact=True), page.locator(".tiles")
    w, t, main = box(watch), box(tiles), box(page.locator(".dash-main"))
    if width == PHONE:  # one column: the pills above the numbers they narrow
        assert w["y"] + w["height"] <= t["y"], (w, t)
        pills = watch.get_by_role("button")
        rows = {round(box(p)["y"]) for p in pills.all()}
        assert 1 < len(rows) <= 3, rows  # one row that wraps
    else:  # as before: the top of the side column, beside the charts, under the tiles
        assert w["x"] >= main["x"] + main["width"] and w["y"] >= t["y"] + t["height"]
        assert abs(w["y"] - main["y"]) < 1
    # Tab order: the banner's Ask Patch, then the filter, then the tiles it narrows
    page.locator(".hello").get_by_role("button", name="Ask Patch").focus()
    page.keyboard.press("Tab")
    expect(watch.get_by_role("button", name="All", exact=True)).to_be_focused()
    assert no_sideways_scroll(page)


# --- B43.6 (item 2): the sources and licences are folded after the status --------------------------------------------

def test_b43_6_sources_and_licences_are_folded_and_open_by_keyboard(open_dash, api_url):
    page = open_dash(reduced=True)
    n = len(api(api_url, "/dashboard")["freshness"])
    summary = sources(page).locator("summary")
    expect(summary).to_have_text(f"Sources and licences ({n})")
    items = sources(page).locator(".side-list > li")
    expect(items.first).to_be_hidden()  # closed at first: the status comes first
    order = freshness(page).evaluate("el => [...el.querySelectorAll('.checked-line, details.sources')]"
                                     ".map(e => e.className)")
    assert order == ["meta checked-line", "sources"], order
    summary.focus()
    page.keyboard.press("Enter")
    expect(items).to_have_count(n)
    expect(items.first).to_be_visible()
    outline = summary.evaluate("el => [getComputedStyle(el).outlineStyle, getComputedStyle(el).outlineWidth]")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2
    page.keyboard.press("Enter")
    expect(items.first).to_be_hidden()


# --- B43.7 (item 3): "See the N new CVEs →" after a check, to the new CVEs you haven't seen ---------------------------

def test_b43_7_see_the_new_cves_links_to_them_and_goes_once_seen(open_live, live_api_url):
    page = open_live()
    link = freshness(page).get_by_role("link", name=re.compile(r"^See the .*new CVE"))
    expect(link).to_have_count(0)  # before any check nothing is new
    freshness(page).get_by_role("button", name="Check now").click()
    expect(link).to_have_text(f"See the {len(NEW)} new CVEs →")
    expect(link).to_have_attribute("href", "/cves?status=all&new=1")
    link.click()
    expect(page).to_have_url(re.compile(r"/cves\?status=all&new=1$"))
    expect(page.locator("table.cves tbody tr")).to_have_count(len(NEW))
    page.get_by_role("button", name="Mark all as seen").click()
    expect(page.get_by_role("button", name="Mark all as seen")).to_have_count(0)
    page.go_back()
    expect(freshness(page)).to_be_visible()
    expect(page.locator(".top-cves li").first).to_be_visible()
    expect(link).to_have_count(0)  # seen: no link


def test_b43_7_the_link_carries_the_product_filter(open_live, live_api_url):
    assert api(live_api_url, "/refresh", "POST")["ran"]
    product = api(live_api_url, f"/cves/{NEW[0]}")["row"]["product"]
    expected = api(live_api_url, f"/dashboard?product={product}")["kpis"]["new_unseen"]
    page = open_live(path=f"/?product={product}")
    link = freshness(page).get_by_role("link", name=re.compile(r"^See the .*new CVE"))
    expect(link).to_have_attribute("href", f"/cves?product={product}&status=all&new=1")
    expect(link).to_have_text("See the new CVE →" if expected == 1 else f"See the {expected} new CVEs →")


def test_b43_7_snapshot_mode_has_no_link(open_dash):
    page = open_dash(reduced=True)
    expect(freshness(page).get_by_role("link", name=re.compile("new CVE"))).to_have_count(0)


# --- B43.8 (item 6, #25): the OWASP chart says it's the web list; codes on the axis, names in the tooltip ----------

def test_b43_8_owasp_chart_codes_on_the_axis_full_names_in_the_tooltip(open_dash, api_url):
    page = open_dash(width=PHONE, reduced=True)
    d = api(api_url, "/dashboard")
    chart = page.get_by_role("region", name=OWASP, exact=True)
    expect(chart.locator("svg .axis-label")).to_have_text([o["code"] for o in d["by_owasp"]])
    expect(chart).to_contain_text("The web list, not the LLM Top 10")
    expect(chart).to_contain_text("a CVE in two categories counts in both")
    a05 = next(o for o in d["by_owasp"] if o["code"] == "A05")
    bar = chart.locator("svg .fill").nth(d["by_owasp"].index(a05))
    bar.focus()
    expect(page.get_by_role("tooltip")).to_have_text(f"A05 Injection: {a05['count']} open CVEs")
    labels = chart.locator("svg .axis-label").evaluate_all("els => els.map(e => e.getBBox().x)")
    assert min(labels) >= 0, labels  # nothing cut off at the left


# --- B43.9 (item 7): Patch's button never covers a chart's totals or the end of a page ------------------------------

@pytest.mark.parametrize("width", [PHONE, 900])
def test_b43_9_chart_totals_stay_clear_of_patchs_button(open_dash, width):
    page = open_dash(width=width, reduced=True)
    fab = patch_box(page)
    for label in page.locator(".chart .value-label").all():  # the bars' totals and the columns' peaks
        b = box(label)
        assert b["x"] + b["width"] <= fab["x"], (label.text_content(), b, fab)  # left of the button at any scroll


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("path", ["/", "/cves", "/cves?product=ollama"])
def test_b43_9_the_end_of_a_page_scrolls_clear_of_patchs_button(browser: Browser, ui_url: str, width, path):
    ctx = browser.new_context(viewport={"width": width, "height": 844 if width == PHONE else 900},
                              reduced_motion="reduce")
    page = ctx.new_page()
    page.goto(ui_url + path)
    if path == "/":
        expect(page.locator(".top-cves li").first).to_be_visible()
    else:
        expect(page.locator(".cves-card .filters .meta")).to_contain_text("CVEs ·")
    page.evaluate("document.fonts.ready.then(() => null)")

    def at_the_end() -> bool:  # scrolled all the way down (the page may still grow as the fonts settle)
        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        return page.evaluate("Math.ceil(scrollY + innerHeight) >= document.documentElement.scrollHeight")
    eventually(page, at_the_end)
    fab = patch_box(page)
    targets = page.locator(".dash-main > .card, .dash-side > .card") if path == "/" else \
        page.locator(".cves-card :is(a, button, summary)")
    hidden = [t.evaluate("el => el.textContent.trim().slice(0, 40)") for t in targets.all()
              if t.is_visible() and overlaps(box(t), fab)]
    assert hidden == [], (hidden, fab)
    ctx.close()


# --- B43.10 (item 8): a smaller Patch in the welcome banner on a phone -----------------------------------------------

def test_b43_10_the_welcome_banner_is_shorter_on_a_phone(open_dash):
    page = open_dash(width=PHONE, reduced=True)
    hello = page.locator(".hello")
    robot, title = hello.locator("svg.robot"), hello.get_by_role("heading")
    assert round(box(robot)["width"]) == 64
    assert box(hello)["height"] <= 250, box(hello)  # about 330px with the stacked 110px Patch
    r, h, t = box(robot), box(hello), box(title)
    assert h["y"] - r["y"] >= 10  # the head still rises over the top edge
    assert t["x"] >= r["x"] + r["width"]  # beside the robot, not under it
    close = box(hello.get_by_role("button", name="Close Patch's welcome"))
    text_right = title.evaluate("""el => { const r = document.createRange(); r.selectNodeContents(el);
        return Math.max(...[...r.getClientRects()].map(c => c.right)) }""")
    assert text_right <= close["x"], (text_right, close)  # the title's words stay clear of the ✕
    assert no_sideways_scroll(page)


# --- B43.11 (item 9): the ATLAS incidents: an intro line, after the cards you act on ---------------------------------

def test_b43_11_atlas_incidents_have_an_intro_and_come_last(open_dash):
    page = open_dash(reduced=True)
    side = page.locator(".dash-side > .card h2").all_inner_texts()
    assert side == ["Recent alerts", "Data freshness", "Latest AI incidents (MITRE ATLAS)"]
    intro = page.get_by_role("region", name="Latest AI incidents (MITRE ATLAS)").locator("p.intro")
    expect(intro).to_contain_text("Real attacks on AI systems")


# --- B43.12 (item 10): a gap between "Decide by …" and the "No fix yet" chip in the Top 5 ----------------------------

def test_b43_12_no_fix_chip_has_a_gap_after_the_date(open_dash, api_url):
    products = api(api_url, "/dashboard")["watchlist"]
    product = next((p for p in products if any(r["no_fix"] for r in api(api_url, f"/cves?product={p}&limit=5")["rows"])),
                   None)
    if product is None:
        pytest.skip("no Top 5 with a CVE without a fix in this snapshot")
    page = open_dash(reduced=True)
    page.goto(page.url.split("?")[0] + f"?product={product}")
    due = page.locator(".top-cves .top-due", has=page.locator(".chip.no-fix")).first
    expect(due).to_be_visible()
    gap = due.evaluate("""el => { const chip = el.querySelector('.chip.no-fix'), date = el.querySelector('.num');
        return chip.getBoundingClientRect().left - date.getBoundingClientRect().right }""")
    assert gap >= 4, gap


# --- B43.13: both themes, a phone and a desktop: contrast, no sideways scroll, screenshots --------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b43_13_the_polished_dashboard_in_both_themes(open_dash, open_live, browser_name, width, scheme):
    page = open_dash(width=width, scheme=scheme, reduced=True)
    summary = sources(page).locator("summary")
    for loc in (summary, page.locator(".incidents .intro"), page.get_by_role("region", name=OWASP).locator("p.meta")):
        colours = loc.evaluate("""el => { let bg = 'rgba(0, 0, 0, 0)', n = el;
            while (n && bg === 'rgba(0, 0, 0, 0)') { bg = getComputedStyle(n).backgroundColor; n = n.parentElement }
            return [getComputedStyle(el).color, bg] }""")
        assert contrast(*colours) >= 4.5, colours
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b43-dashboard-{browser_name}-{width}-{scheme}.png", full_page=True)
    live = open_live(width=width, scheme=scheme)
    freshness(live).get_by_role("button", name="Check now").click()
    link = freshness(live).get_by_role("link", name=re.compile("new CVEs"))
    expect(link).to_be_visible()
    colours = link.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el.closest('.card')).backgroundColor]")
    assert contrast(*colours) >= 4.5, colours
    assert no_sideways_scroll(live)
    freshness(live).screenshot(path=SHOTS / f"b43-freshness-{browser_name}-{width}-{scheme}.png")


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def b43_14_dashboard_polish(fx):
    page = fx("open_dash")(width=PHONE, reduced=True)
    sources(page).locator("summary").click()
    expect(sources(page).locator(".side-list > li").first).to_be_visible()
    still(page, "the phone dashboard with the sources open")

"""Browser check (seam 3) for the dashboard's charts, side panels and Patch's welcome banner. Check ids: A05.n (#7).

Runs in Firefox and Chromium (run.sh). Expected numbers come from the backend's API (tested on its own in
backend/tests/test_dashboard.py); expected looks come from docs/design/DESIGN.md §5.4, §5.8, §7.1 and §8.2.
"""
import pytest
from playwright.sync_api import Page, expect

from test_dashboard import DESKTOP, PHONE, SHOTS, api, clean_state, open_dash  # noqa: F401 (fixtures)

SEV_LIGHT = {"CRITICAL": "rgb(46, 26, 128)", "HIGH": "rgb(82, 53, 214)", "MEDIUM": "rgb(123, 92, 255)",
             "LOW": "rgb(164, 139, 255)"}


def chart(page: Page, title: str):
    return page.get_by_role("region", name=title, exact=True)


BY_PRODUCT = "Open CVEs by product and severity"
PER_MONTH = "CVEs per month"
BY_OWASP = "Open CVEs by OWASP category"


# --- Open CVEs by product and severity (DESIGN.md §5.4) -----------------------------------------------------------

def test_a05_1_stacked_bars_per_product_with_severity_ramp_gaps_and_totals(open_dash, api_url):
    page = open_dash(reduced=True)
    data = api(api_url, "/dashboard")["by_product"]
    card = chart(page, BY_PRODUCT)
    expect(card.locator("svg .bar-row")).to_have_count(len(data))
    for i, p in enumerate(data):
        row = card.locator("svg .bar-row").nth(i)
        expect(row.locator(".axis-label")).to_have_text(p["name"])
        expect(row.locator(".value-label")).to_have_text(str(p["total"]))
        segs = row.locator(".fill").evaluate_all("""els => els.map(el => { const b = el.getBBox();
            return { sev: el.dataset.severity, x: b.x, w: b.width, fill: getComputedStyle(el).fill } })""")
        expected = [s for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW") if p[s] > 0]
        assert [s["sev"] for s in segs] == expected, p["name"]
        assert all(s["fill"] == SEV_LIGHT[s["sev"]] for s in segs)
        for a, b in zip(segs, segs[1:]):  # a 2px surface gap between touching segments
            assert abs(b["x"] - (a["x"] + a["w"]) - 2) < 0.6, (p["name"], a, b)
        if segs:  # the total sits just past the bar's end
            label_x = row.locator(".value-label").evaluate("el => el.getBBox().x")
            assert 0 < label_x - (segs[-1]["x"] + segs[-1]["w"]) < 12


# --- CVEs per month (DESIGN.md §5.4) -------------------------------------------------------------------------------

def test_a05_2_columns_per_month_in_series_1_with_labels_on_peaks(open_dash, api_url):
    page = open_dash(reduced=True)
    months = api(api_url, "/dashboard")["per_month"]
    card = chart(page, PER_MONTH)
    expect(card.locator("svg .hit")).to_have_count(len(months))  # one hover target per month
    expect(card.locator("svg .fill")).to_have_count(sum(m["count"] > 0 for m in months))
    fills = card.locator("svg .fill").evaluate_all("els => els.map(el => getComputedStyle(el).fill)")
    assert set(fills) == {"rgb(123, 92, 255)"}  # --series-1
    peak = max(m["count"] for m in months)
    labels = [int(t) for t in card.locator("svg .value-label").all_text_contents()]
    assert peak in labels and len(labels) <= 3, labels  # the peaks, not every column
    assert card.locator("svg .grid").first.evaluate("el => getComputedStyle(el).stroke") == "rgb(236, 238, 251)"
    axis = card.locator("svg .axis-label").first.evaluate("el => getComputedStyle(el).fontSize")
    value = card.locator("svg .value-label").first.evaluate("el => getComputedStyle(el).fontSize")
    assert axis == value == "11px"


# --- Open CVEs by OWASP category (DESIGN.md §5.4) ------------------------------------------------------------------

def test_a05_3_horizontal_bars_per_owasp_category(open_dash, api_url):
    page = open_dash(reduced=True)
    d = api(api_url, "/dashboard")
    card = chart(page, BY_OWASP)
    bars = card.locator("svg .fill")
    expect(bars).to_have_count(len(d["by_owasp"]))
    assert card.locator("svg .value-label").all_text_contents() == [str(o["count"]) for o in d["by_owasp"]]
    labels = card.locator("svg .axis-label").all_text_contents()
    assert all(lab.startswith(o["code"]) for lab, o in zip(labels, d["by_owasp"])), labels  # the code always shows
    boxes = bars.evaluate_all("els => els.map(el => [el.getBBox().x, getComputedStyle(el).fill])")
    assert len({round(b[0]) for b in boxes}) == 1  # every bar starts at the axis
    assert {b[1] for b in boxes} == {"rgb(123, 92, 255)"}
    if d["owasp_unmapped"]:
        expect(card.get_by_text(f"{d['owasp_unmapped']} open CVEs have no CWE in OWASP's lists")).to_be_visible()


# --- Every chart: title, legend, tooltips, "Show as table" (DESIGN.md §5.4) ----------------------------------------

def test_a05_4_legend_only_on_the_chart_with_several_series(open_dash):
    page = open_dash(reduced=True)
    legend = chart(page, BY_PRODUCT).locator(".legend li")
    expect(legend).to_have_text(["Critical", "High", "Medium", "Low"])
    swatches = legend.locator(".swatch").evaluate_all("els => els.map(el => getComputedStyle(el).backgroundColor)")
    assert swatches == [SEV_LIGHT[s] for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")]
    for title in (PER_MONTH, BY_OWASP):  # one series: no legend
        expect(chart(page, title).get_by_role("heading", name=title)).to_be_visible()
        expect(chart(page, title).locator(".legend")).to_have_count(0)


@pytest.mark.parametrize("title", [BY_PRODUCT, PER_MONTH, BY_OWASP])
def test_a05_4_every_bar_has_a_hover_tooltip_above_the_pointer(open_dash, title):
    page = open_dash(reduced=True)
    targets = chart(page, title).locator("svg [aria-label]:is(.fill, .hit)")
    expect(targets.first).to_be_attached()  # drawn once the chart knows its width
    count = targets.count()
    assert count > 0
    tip = page.get_by_role("tooltip")
    for i in sorted({0, count // 2, count - 1}):
        target = targets.nth(i)
        target.scroll_into_view_if_needed()
        box = target.bounding_box()
        assert box
        x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
        page.mouse.move(x, y)
        expect(tip).to_have_text(target.get_attribute("aria-label") or "")
        tb = tip.bounding_box()
        assert tb and tb["y"] + tb["height"] <= y and abs(tb["x"] + tb["width"] / 2 - x) < 2  # above, centred
        colours = tip.evaluate("el => [getComputedStyle(el).backgroundColor, getComputedStyle(el).color,"
                               " getComputedStyle(el).borderRadius]")
        assert colours == ["rgb(42, 37, 89)", "rgb(255, 255, 255)", "4px"]  # --text on --surface
    page.mouse.move(1, 1)
    expect(tip).to_have_count(0)


def test_a05_4_show_as_table_gives_the_same_numbers(open_dash, api_url):
    page = open_dash(reduced=True)
    d = api(api_url, "/dashboard")
    expected = {
        BY_PRODUCT: [[p["name"], *(str(p[s]) for s in ("CRITICAL", "HIGH", "MEDIUM", "LOW")), str(p["total"])]
                     for p in d["by_product"]],
        PER_MONTH: [[m["month"], str(m["count"])] for m in d["per_month"]],
        BY_OWASP: [[o["title"], str(o["count"])] for o in d["by_owasp"]],
    }
    for title, rows in expected.items():
        card = chart(page, title)
        table = card.get_by_role("table")
        expect(table).to_be_hidden()
        card.get_by_text("Show as table").click()
        expect(table).to_be_visible()
        got = table.locator("tbody tr").evaluate_all(
            "trs => trs.map(tr => [...tr.cells].map(c => c.textContent.trim()))")
        assert got == rows, title


# --- Patch's welcome banner (DESIGN.md §5.8, §8.2) -----------------------------------------------------------------

def banner(page: Page):
    return page.get_by_role("region", name="Hi there! I'm Patch, your security sidekick.")


def test_a05_7_welcome_banner_with_waving_patch_over_its_top_edge(open_dash):
    page = open_dash()
    hello = banner(page)
    expect(hello).to_be_visible()
    title = hello.get_by_role("heading", name="Hi there! I'm Patch, your security sidekick.")
    looks = title.evaluate("el => [getComputedStyle(el).fontFamily, getComputedStyle(el).fontSize, getComputedStyle(el).color]")
    assert looks[0].startswith("Fredoka") and looks[1] == "18.75px" and looks[2] == "rgb(108, 76, 245)"  # 1.25rem, --accent
    expect(hello.locator("p")).to_have_count(1)  # one line of help
    expect(hello.get_by_role("button", name="Ask Patch")).to_be_visible()
    box = hello.evaluate("""el => { const s = getComputedStyle(el); return [s.borderRadius, s.backgroundImage] }""")
    assert box[0] == "28px" and "linear-gradient" in box[1]
    # Above the dashboard: before the tiles.
    assert hello.evaluate("el => !!(el.compareDocumentPosition(document.querySelector('.tiles')) & 4)")
    robot = hello.locator("svg.robot")
    expect(robot).to_have_attribute("aria-hidden", "true")
    assert robot.evaluate("el => el.getAttribute('width')") == "110"
    assert "wave" in (robot.get_attribute("class") or "")
    hand = robot.locator(".bot-hand.right").evaluate("el => getComputedStyle(el).animationName")
    assert hand == "bot-wave"
    rb, hb = robot.bounding_box(), hello.bounding_box()
    # His head rises over the banner's top edge (margin −2.4rem inside the 0.9rem padding): a fifth of him sticks out.
    assert rb and hb and 20 <= hb["y"] - rb["y"] <= rb["height"] / 2, (rb, hb)


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_a05_7_closed_banner_stays_closed_in_this_browser(open_dash, width):
    page = open_dash(width=width, reduced=True)
    close = banner(page).get_by_role("button", name="Close Patch's welcome")
    size = close.evaluate("el => [getComputedStyle(el).width, getComputedStyle(el).height, getComputedStyle(el).borderRadius]")
    assert size[:2] == ["32px", "32px"] and size[2] in ("50%", "999px", "16px"), size
    close.click()
    expect(banner(page)).to_have_count(0)
    assert page.evaluate("localStorage.getItem('helloHidden')") == "1"
    page.reload()
    expect(page.locator(".tile")).to_have_count(4)
    expect(banner(page)).to_have_count(0)


def test_a05_7_ask_patch_in_the_banner_opens_the_chat(open_dash):
    page = open_dash(reduced=True)
    chat = page.get_by_role("complementary", name="Chat with Patch")
    expect(chat).to_have_count(0)
    banner(page).get_by_role("button", name="Ask Patch").click()
    expect(chat).to_be_visible()


def test_a05_7_banner_survives_blocked_storage(open_dash):
    block = "Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked') } })"
    page = open_dash(before=lambda p: p.add_init_script(block))
    banner(page).get_by_role("button", name="Close Patch's welcome").click()
    expect(banner(page)).to_have_count(0)  # closes for now, just isn't remembered


# --- Side panels ---------------------------------------------------------------------------------------------------

def test_a05_6_latest_atlas_incidents(open_dash, api_url):
    page = open_dash(reduced=True)
    incidents = api(api_url, "/dashboard")["latest_incidents"]
    assert len(incidents) == 5
    panel = page.get_by_role("region", name="Latest AI incidents (MITRE ATLAS)")
    items = panel.get_by_role("listitem")
    expect(items).to_have_count(5)
    for item, c in zip(items.all(), incidents):
        link = item.get_by_role("link", name=c["name"])
        expect(link).to_have_attribute("href", c["url"])
        expect(item).to_contain_text(f"{c['date']} · {c['id']}")
    dates = [c["date"] for c in incidents]
    assert dates == sorted(dates, reverse=True)  # newest first


def test_a05_6_data_freshness_with_date_and_licence_per_source(open_dash, api_url):
    page = open_dash(reduced=True)
    sources = api(api_url, "/dashboard")["freshness"]
    panel = page.get_by_role("region", name="Data freshness")
    items = panel.get_by_role("listitem")
    expect(items).to_have_count(len(sources))
    for item, s in zip(items.all(), sources):
        expect(item.get_by_role("link", name=s["name"])).to_have_attribute("href", s["url"])
        expect(item).to_contain_text(s["licence"])
        expect(item).to_contain_text(f"retrieved {s['retrieved']}")
    # Side column: watchlist editor, then the incidents, then freshness.
    titles = page.locator(".dash-side > .card h2").all_inner_texts()
    assert titles == ["Watchlist", "Latest AI incidents (MITRE ATLAS)", "Data freshness"]


# --- Motion (DESIGN.md §7.1) ---------------------------------------------------------------------------------------

GROWING = """el => el.getAnimations({ subtree: true }).filter(a => a.animationName?.startsWith('grow-'))
    .map(a => ({ name: a.animationName, state: a.playState, target: a.effect.target.getAttribute('class') }))"""


def test_a05_5_bars_grow_in_on_first_load_stacked_bars_as_one_piece(open_dash):
    page = open_dash()
    cards = page.locator(".dash-main > .card").evaluate_all(
        "els => els.map(el => [getComputedStyle(el).animationName, getComputedStyle(el).animationDelay])")
    assert cards == [["fade-up", d] for d in ("0s", "0.12s", "0.24s", "0.24s")]  # 3 charts, then the top 5 CVEs
    stacked = chart(page, BY_PRODUCT).locator(".chart-box")
    for title in (BY_PRODUCT, PER_MONTH, BY_OWASP):
        expect(chart(page, title).locator(".fill").first).to_be_attached()
    fills =stacked.locator(".fill").evaluate_all("""els => els.map(el => { const s = getComputedStyle(el);
        return [s.animationName, s.animationDuration, s.animationDelay, s.animationTimingFunction, s.transformBox,
                s.transformOrigin] })""")
    x0 = stacked.locator("svg").evaluate("el => el.style.getPropertyValue('--x0')")
    assert fills and all(f[:5] == ["grow-x", "0.9s", "0.2s", "cubic-bezier(0.2, 0.8, 0.2, 1)", "view-box"] for f in fills)
    # One origin for every segment, the chart's axis: the segments scale together, so no gap opens between them.
    assert {f[5].split(" ")[0] for f in fills} == {x0}, (x0, fills)
    owasp = chart(page, BY_OWASP).locator(".fill").first.evaluate("el => getComputedStyle(el).animationName")
    assert owasp == "grow-x"
    column = chart(page, PER_MONTH).locator(".fill").first.evaluate(
        "el => [getComputedStyle(el).animationName, getComputedStyle(el).transformBox, getComputedStyle(el).animationDelay]")
    assert column == ["grow-y", "fill-box", "0.2s"]

    # Mid-grow, a stacked bar's segments are still joined: each gap is 2px scaled by the same factor.
    page.wait_for_timeout(500)  # on purpose: a frame mid-grow (if the grow is already over, the bars are joined too)
    rows = stacked.locator(".bar-row").evaluate_all("""rows => rows.map(r => [...r.querySelectorAll('.fill')]
        .map(el => { const b = el.getBoundingClientRect(); return [b.left, b.right] }))""")
    full = stacked.locator(".bar-row").evaluate_all("""rows => rows.map(r => [...r.querySelectorAll('.fill')]
        .map(el => { const b = el.getBBox(); return [b.x, b.x + b.width] }))""")
    for live, final in zip(rows, full):
        if len(live) < 2:
            continue
        scale = (live[-1][1] - live[0][0]) / (final[-1][1] - final[0][0])
        assert 0 < scale < 1, "still growing"
        for (a, b), (fa, fb) in zip(zip(live, live[1:]), zip(final, final[1:])):
            assert abs((b[0] - a[1]) - (fb[0] - fa[1]) * scale) < 0.6


def test_a05_5_bars_do_not_grow_again_on_hover_resize_or_reload(open_dash, api_url):
    page = open_dash()
    dash = page.locator(".dashboard")
    assert dash.evaluate(GROWING), "the bars grow on first load"
    page.wait_for_function(f"!({GROWING})(document.querySelector('.dashboard')).length", timeout=5000)
    chart(page, BY_PRODUCT).locator(".fill").first.hover()
    page.set_viewport_size({"width": 1100, "height": 900})
    page.wait_for_timeout(100)  # on purpose: give a wrongly restarted grow time to show
    assert dash.evaluate(GROWING) == []
    # A product added to the watchlist brings a new bar: it appears at full length too.
    rows_before = chart(page, BY_PRODUCT).locator(".bar-row").count()
    editor = page.get_by_role("region", name="Watchlist", exact=True)
    editor.get_by_label("vLLM").check()
    editor.get_by_role("button", name="Save watchlist").click()
    expect(chart(page, BY_PRODUCT).locator(".bar-row")).to_have_count(rows_before + 1)
    assert dash.evaluate(GROWING) == []


def test_a05_8_reduced_motion_nothing_in_charts_or_banner_moves(open_dash):
    page = open_dash(reduced=True)
    expect(banner(page).locator("svg.robot")).to_be_visible()
    expect(chart(page, BY_PRODUCT).locator(".fill").first).to_be_visible()
    assert page.evaluate("document.getAnimations().length") == 0
    names = page.locator(".chart .fill, .hello .robot *").evaluate_all(
        "els => [...new Set(els.map(el => getComputedStyle(el).animationName))]")
    assert names == ["none"]
    # Bars are drawn at full length straight away, and Patch's waving hand stands still.
    full = chart(page, BY_PRODUCT).locator(".fill").first.evaluate(
        "el => Math.abs(el.getBoundingClientRect().width - el.getBBox().width) < 0.6")
    assert full
    hand = banner(page).locator(".bot-hand.right").evaluate("""async el => { const seen = new Set();
        for (let i = 0; i < 8; i++) { seen.add(getComputedStyle(el).transform); await new Promise(r => setTimeout(r, 60)) }
        return [...seen] }""")
    assert hand == ["none"]


# --- Light and dark, phone and desktop, keyboard (DESIGN.md §9, §4.2, §10) -----------------------------------------

SEV_DARK_CRITICAL = "rgb(217, 208, 255)"


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a05_9_light_dark_phone_and_desktop(open_dash, browser_name, width, scheme):
    page = open_dash(width=width, scheme=scheme, reduced=True)
    expect(banner(page)).to_be_visible()
    for title in (BY_PRODUCT, PER_MONTH, BY_OWASP):
        card = chart(page, title)
        expect(card.locator(".fill").first).to_be_visible()
        svg, box = card.locator("svg").bounding_box(), card.bounding_box()
        assert svg and box and svg["x"] >= box["x"] and svg["x"] + svg["width"] <= box["x"] + box["width"], title
    page.screenshot(path=SHOTS / f"a05-{browser_name}-{width}-{scheme}.png", full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    critical = chart(page, BY_PRODUCT).locator(".fill.sev-critical").first.evaluate("el => getComputedStyle(el).fill")
    assert critical == (SEV_LIGHT["CRITICAL"] if scheme == "light" else SEV_DARK_CRITICAL)
    hello = banner(page).evaluate("el => getComputedStyle(el).backgroundImage")
    assert ("rgb(255, 255, 255)" if scheme == "light" else "rgb(26, 26, 46)") in hello  # starts at --surface
    side = page.locator(".dash-side").bounding_box()
    main = page.locator(".dash-main").bounding_box()
    assert side and main
    if width == PHONE:  # one column: the side panels drop below the main column
        assert side["y"] > main["y"] + main["height"] - 1
        assert banner(page).evaluate("el => getComputedStyle(el).flexDirection") == "column"
    else:
        assert side["x"] > main["x"] + main["width"] - 1


@pytest.mark.parametrize("title", [BY_PRODUCT, PER_MONTH, BY_OWASP])
def test_a05_10_each_chart_is_one_tab_stop_with_arrow_keys_between_bars(open_dash, title):
    """Review item 20: about 50 bars were each a Tab stop. Now a chart is one stop (DESIGN.md §10): Tab lands on its
    first bar and leaves with the next Tab; arrow keys, Home and End move between bars, each with its tooltip."""
    page = open_dash(reduced=True)
    targets = chart(page, title).locator("svg [aria-label]:is(.fill, .hit)")
    expect(targets.first).to_be_attached()
    count = targets.count()
    assert count >= 2
    assert chart(page, title).locator("svg [tabindex='0']").count() == 1
    tip = page.get_by_role("tooltip")
    targets.first.focus()
    expect(tip).to_have_text(targets.first.get_attribute("aria-label") or "")
    page.keyboard.press("ArrowRight")
    expect(targets.nth(1)).to_be_focused()
    expect(tip).to_have_text(targets.nth(1).get_attribute("aria-label") or "")
    page.keyboard.press("ArrowLeft")
    expect(targets.first).to_be_focused()
    page.keyboard.press("End")
    expect(targets.last).to_be_focused()
    page.keyboard.press("ArrowDown")  # stays on the last
    expect(targets.last).to_be_focused()
    page.keyboard.press("Home")
    expect(targets.first).to_be_focused()
    page.keyboard.press("Tab")  # out of the chart in one press
    assert not chart(page, title).locator("svg").evaluate("el => el.contains(document.activeElement)")
    page.keyboard.press("Shift+Tab")  # back in: the bar last focused
    expect(targets.first).to_be_focused()


def test_a05_10_keyboard_reaches_banner_bars_tables_and_panels(open_dash):
    page = open_dash(reduced=True)
    hello = banner(page)
    hello.get_by_role("button", name="Close Patch's welcome").focus()
    page.keyboard.press("Tab")
    expect(hello.get_by_role("button", name="Ask Patch")).to_be_focused()
    # The first bar: a keyboard stop with a visible ring, and its tooltip shows.
    first_bar = chart(page, BY_PRODUCT).locator(".fill").first
    for _ in range(30):
        page.keyboard.press("Tab")
        if first_bar.evaluate("el => el === document.activeElement"):
            break
    expect(first_bar).to_be_focused()
    ring = first_bar.evaluate("el => [getComputedStyle(el).stroke, getComputedStyle(el).strokeWidth]")
    assert ring == ["rgb(42, 37, 89)", "2px"]
    expect(page.get_by_role("tooltip")).to_have_text(first_bar.get_attribute("aria-label") or "")
    # "Show as table" opens with the keyboard.
    summary = chart(page, BY_PRODUCT).get_by_text("Show as table")
    for _ in range(30):
        page.keyboard.press("Tab")
        if summary.evaluate("el => el === document.activeElement"):
            break
    expect(summary).to_be_focused()
    outline = summary.evaluate("el => [getComputedStyle(el).outlineStyle, getComputedStyle(el).outlineWidth]")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2
    page.keyboard.press("Enter")
    expect(chart(page, BY_PRODUCT).get_by_role("table")).to_be_visible()
    # The side panels' links are reachable too.
    link = page.get_by_role("region", name="Data freshness").get_by_role("link").first
    link.focus()
    expect(link).to_be_focused()

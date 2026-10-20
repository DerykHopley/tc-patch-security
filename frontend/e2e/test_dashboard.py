"""Browser check (seam 3) for the dashboard: tiles and the watchlist filter. Check ids: A04.n (#6).
The watchlist editor moved to Settings (A15b, #30): its checks (A04.8) are in test_watchlist.py.
The CVE table moved to its own page (A04b, #26): its checks are in test_cves_page.py, with their A04.n ids.

Runs in Firefox and Chromium (run.sh). Expected numbers come from the backend's API (tested on its own in
backend/tests/test_dashboard.py); expected looks come from docs/design/DESIGN.md §5.1 and §7.1.
Every test that changes state puts it back (the `clean_state` fixture), since all tests share one backend.
"""
import json
import pathlib
import re
import urllib.request

import pytest
from playwright.sync_api import Browser, Page, expect
from reduced_motion import scene, still

SHOTS = pathlib.Path(__file__).parent / "screenshots"
PHONE, DESKTOP = 400, 1400
DEFAULT_WATCHLIST = ["langchain", "langflow", "litellm", "ollama", "open-webui"]

# DESIGN.md §5.1: deep colour until 35%, then the bright colour.
TILES = [
    ("Open CVEs", (91, 63, 224), (139, 108, 255)),
    ("Open and critical", (194, 74, 10), (245, 147, 63)),
    ("Open and exploited in the wild (CISA KEV)", (196, 42, 80), (255, 107, 139)),
    ("New in the last 30 days", (38, 38, 95), (74, 74, 168)),
]


def api(api_url: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def cve_row(api_url: str, cve: str, product: str) -> dict:
    """One CVE's row on the CVEs page, any status. Page by page: closed CVEs sort after the open ones (B33), so a
    product with over 200 CVEs can put a fixed one past the first page."""
    offset = 0
    while rows := api(api_url, f"/cves?status=all&product={product}&limit=200&offset={offset}")["rows"]:
        if found := next((r for r in rows if r["id"] == cve), None):
            return found
        offset += 200
    raise KeyError(cve)


@pytest.fixture
def clean_state(api_url: str):
    """Default watchlist, default usage, version and internet-facing, and every CVE open, before and after the test."""
    def reset():
        products = [p["id"] for p in api(api_url, "/dashboard")["products"]]
        api(api_url, "/watchlist", "PUT", {"products": [{"product": p} for p in products]})  # A15: default fields
        for status in ("fixed", "not_affected", "accepted"):
            for r in api(api_url, f"/cves?status={status}&limit=200")["rows"]:
                api(api_url, f"/cves/{r['id']}", "PATCH", {"status": "open"})
        api(api_url, "/watchlist", "PUT", {"products": DEFAULT_WATCHLIST})

    reset()
    yield
    reset()


def confirm(page: Page, justification: str | None = None) -> None:
    """Every status change opens the decision dialog (A16b): pick a justification if asked, then submit it."""
    d = page.get_by_role("dialog")
    expect(d).to_be_visible()
    if justification:
        d.get_by_role("radio", name=justification).check()
    d.locator("button[type=submit]").click()
    expect(d).to_have_count(0)


@pytest.fixture
def open_dash(browser: Browser, ui_url: str, clean_state):
    """Opens the dashboard in a fresh context and waits for the tiles and the "Top 5 open CVEs" card."""
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False, before=None, fonts=True) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        if before:
            before(page)
        page.goto(ui_url)
        expect(page.locator(".tile")).to_have_count(4)
        expect(page.locator(".top-cves li").first).to_be_visible()
        if fonts:  # late web fonts move the layout (CI race); a check of the first second's motion can't wait
            page.evaluate("document.fonts.ready.then(() => null)")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def tile(page: Page, label: str):
    return page.locator(".tile", has=page.get_by_text(label, exact=True))


def tile_value(page: Page, label: str) -> int:
    return int(tile(page, label).locator(".tile-value").inner_text())


def rgb_list(css: str) -> list[tuple[int, ...]]:
    return [tuple(int(float(v)) for v in m.split(",")[:3]) for m in re.findall(r"rgba?\(([^)]*)\)", css)]


def contrast(a: tuple[int, ...], b: tuple[int, ...]) -> float:
    def lum(c):
        r, g, b_ = (x / 255 / 12.92 if x / 255 <= 0.03928 else ((x / 255 + 0.055) / 1.055) ** 2.4 for x in c)
        return 0.2126 * r + 0.7152 * g + 0.0722 * b_
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def rows(page: Page) -> list[str]:
    return page.locator("table.cves tbody tr td:first-child a").all_inner_texts()


def more_actions(page: Page, cve: str) -> None:
    """Opens a CVE row's "More" (B36): its status actions after the main one, and "Ask about this". Open stays open."""
    summary = page.get_by_label(f"More actions for {cve}", exact=True)
    if not summary.evaluate("el => el.parentElement.open"):
        # By keyboard: the open chat's head may sit over the top row's More, and a click would land on it
        summary.focus()
        page.keyboard.press("Enter")
    expect(summary.locator("xpath=..").get_by_role("button", name=f"Ask about this: {cve}")).to_be_visible()


def ask_about(page: Page, cve: str):
    """A CVE row's "Ask about this", in view: it's under the row's More (B36)."""
    more_actions(page, cve)
    return page.locator("table.cves").get_by_role("button", name=f"Ask about this: {cve}")


def expect_rows(page: Page, ids: list[str]) -> None:
    """Waits until the table shows exactly these CVEs, in this order."""
    expect(page.locator("table.cves tbody tr td:first-child a")).to_have_text(ids)


# --- Tiles (DESIGN.md §5.1) ---------------------------------------------------------------------------------------

def test_a04_6_tiles_show_the_dashboard_numbers(open_dash, api_url):
    page = open_dash()
    kpis = api(api_url, "/dashboard")["kpis"]
    assert [tile_value(page, label) for label, *_ in TILES] == [kpis["open"], kpis["critical"], kpis["kev"], kpis["new_30d"]]
    note = tile(page, TILES[2][0]).locator(".tile-note")
    expect(note).to_contain_text(kpis["kev_next_due"]["cve"])
    expect(note.locator("svg")).to_have_attribute("aria-hidden", "true")


def test_a04_6_tiles_gradients_circles_and_contrast(open_dash):
    page = open_dash(reduced=True)
    for label, deep, bright in TILES:
        t = tile(page, label)
        style = t.evaluate("""el => { const s = getComputedStyle(el); const b = getComputedStyle(el, '::before');
            const a = getComputedStyle(el, '::after'); return { bg: s.backgroundImage, radius: s.borderRadius,
            color: s.color, shadow: s.boxShadow, before: [b.width, b.height, b.right, b.top, b.backgroundColor],
            after: [a.width, a.height, a.right, a.bottom, a.backgroundColor],
            label: getComputedStyle(el.querySelector('.tile-label')).color,
            value: getComputedStyle(el.querySelector('.tile-value')) } }""")
        assert "linear-gradient(135deg" in style["bg"] and " 35%" in style["bg"], style["bg"]
        assert rgb_list(style["bg"]) == [deep, bright], label
        assert style["radius"] == "24px" and style["color"] == "rgb(255, 255, 255)"
        assert style["before"][:4] == ["120px", "120px", "-30px", "-40px"]
        assert style["after"][:4] == ["80px", "80px", "40px", "-45px"]
        assert style["before"][4] == style["after"][4] == "rgba(255, 255, 255, 0.16)"
        assert rgb_list(style["label"])[0] == (255, 255, 255) and "0.92" in style["label"]
        assert contrast((255, 255, 255), deep) >= 4.5, label  # the label sits on the deep end
    value = tile(page, TILES[0][0]).locator(".tile-value").evaluate(
        "el => [getComputedStyle(el).fontFamily, getComputedStyle(el).fontSize]")
    assert value[0].startswith("Fredoka") and value[1] == "31.5px"  # 2.1rem of 15px


def test_a04_6_kev_tile_wiggles_every_4s_only_with_open_kev(open_dash):
    page = open_dash()
    kev = tile(page, TILES[2][0])
    names = kev.evaluate("el => [getComputedStyle(el).animationName, getComputedStyle(el).animationDuration, "
                         "getComputedStyle(el).animationIterationCount]")
    assert "tile-wiggle" in names[0] and "4s" in names[1] and "infinite" in names[2], names
    assert "tile-wiggle" not in tile(page, TILES[0][0]).evaluate("el => getComputedStyle(el).animationName")

    def no_kev(p: Page):
        def handle(route):
            resp = route.fetch()
            body = resp.json()
            route.fulfill(response=resp, json={**body, "kpis": {**body["kpis"], "kev": 0, "kev_next_due": None}})
        p.route("**/dashboard", handle)

    calm = open_dash(before=no_kev)
    assert tile_value(calm, TILES[2][0]) == 0
    assert "tile-wiggle" not in tile(calm, TILES[2][0]).evaluate("el => getComputedStyle(el).animationName")
    expect(tile(calm, TILES[2][0]).locator(".tile-note")).to_have_count(0)


# --- Watchlist: A04.8's editor moved to Settings (A15b); its checks are in test_watchlist.py -------------------


# --- Motion (DESIGN.md §7.1) --------------------------------------------------------------------------------------

def test_a04_9_tiles_and_cards_fade_up_with_the_listed_delays(open_dash):
    page = open_dash()
    tiles = page.locator(".tile").evaluate_all(
        "els => els.map(el => [getComputedStyle(el).animationName, getComputedStyle(el).animationDelay])")
    assert [t[0].split(",")[0].strip() for t in tiles] == ["fade-up"] * 4
    assert [t[1].split(",")[0].strip() for t in tiles] == ["0s", "0.05s", "0.1s", "0.15s"]
    card = page.locator(".dash-side > .card").first.evaluate(
        "el => [getComputedStyle(el).animationName, getComputedStyle(el).animationDuration, getComputedStyle(el).animationDelay,"
        " getComputedStyle(el).animationTimingFunction]")
    assert card == ["fade-up", "0.45s", "0.12s", "cubic-bezier(0.2, 0.8, 0.2, 1)"]


# Reduced motion: scene a04_9 at the end of this file, in the shared check (reduced_motion.py).


# --- Light and dark, phone and desktop, keyboard ------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a04_10_light_dark_phone_and_desktop(open_dash, browser_name, width, scheme):
    page = open_dash(width=width, scheme=scheme, reduced=True)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a04-{browser_name}-{width}-{scheme}.png", full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    columns = page.locator(".tiles").evaluate("el => getComputedStyle(el).gridTemplateColumns.split(' ').length")
    assert columns == (2 if width == PHONE else 4)
    surface = page.locator(".dash-main > .card").first.evaluate("el => getComputedStyle(el).backgroundColor")
    assert surface == ("rgb(255, 255, 255)" if scheme == "light" else "rgb(26, 26, 46)")
    # The row actions' check (with and without the pinned chat) moved to the CVEs page: test_cves_page.py.


def test_a04_11_keyboard_reaches_the_watchlist_filter(open_dash):
    # The filters, row actions and paging moved to the CVEs page (test_cves_page.py keeps A04.11 for them); the
    # watchlist is a filter now (A15b): its chips and the link to Settings.
    page = open_dash()
    page.locator(".hello").get_by_role("button", name="Ask Patch").focus()  # B43: the filter comes right after the banner
    seen = []
    for _ in range(40):
        page.keyboard.press("Tab")
        seen.append(page.evaluate("(() => { const a = document.activeElement;"
                                  " return a.getAttribute('aria-label') || a.textContent.trim() })()"))
        if seen[-1].startswith("Edit watchlist in Settings"):
            break
    assert "LangChain" in seen and seen[-1].startswith("Edit watchlist in Settings"), seen
    outline = page.evaluate("(() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineWidth] })()")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def a04_9_dashboard(fx):
    from test_watchlist import chip_button  # here: test_watchlist imports this file
    page = fx("open_dash")(reduced=True)
    chip_button(page, "Langflow").click()  # a reload must not animate either (the product filter, A15b)
    expect(page.locator(".chart").first.locator(".bar-row")).to_have_count(1)
    still(page, "after a reload")
    transforms = tile(page, TILES[2][0]).evaluate("""async el => { const seen = new Set();
        for (let i = 0; i < 10; i++) { seen.add(getComputedStyle(el).transform); await new Promise(r => setTimeout(r, 50)) }
        return [...seen] }""")
    assert transforms == ["none"]  # the KEV tile doesn't wiggle

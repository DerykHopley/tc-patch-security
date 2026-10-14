"""Browser check (seam 3) for the CVEs page: the CVE table moved off the dashboard, its filters in the URL, the tiles'
links, the dashboard's "Top 5 open CVEs" card, phone cards and the pinned chat. Check ids: A04b.n, from ticket #26.
The table checks that moved here from the dashboard keep their A04.n ids (#6).

Runs in Firefox and Chromium (run.sh). Expected numbers come from the backend's API (tested on its own in
backend/tests/test_dashboard.py); expected looks from docs/design/DESIGN.md §4, §5.9, §7.1 and §10.
Every test that changes state puts it back (the `clean_state` fixture), since all tests share one backend.
"""
import re
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from test_dashboard import (  # noqa: F401 (fixtures)
    DESKTOP, PHONE, SHOTS, TILES, api, clean_state, expect_rows, open_dash, rows, tile, tile_value,
)

HEIGHT = 900
PIN = "Pin: dock the chat beside the page"
UNPIN = "Unpin: float the chat over the page"


@pytest.fixture
def open_cves(browser: Browser, ui_url: str, clean_state):
    """Opens the CVEs page (with an optional query string) in a fresh context and waits for the table."""
    contexts = []

    def _open(query="", width=DESKTOP, scheme="light", reduced=False, init_script=None) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": HEIGHT}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        if init_script:
            page.add_init_script(init_script)
        page.goto(f"{ui_url}/cves{query}")
        expect(page.locator("table.cves tbody tr").first).to_be_visible()
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def params(page: Page) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(urlparse(page.url).query).items()}


def window(page: Page) -> Locator:
    return page.get_by_role("complementary", name="Chat with Patch")


def head_button(page: Page, name: str) -> Locator:
    return window(page).locator(".chat-head").get_by_role("button", name=name, exact=True)


def pin(page: Page) -> None:
    page.keyboard.press("Control+k")
    expect(window(page)).to_be_visible()
    head_button(page, "Make larger").click()
    head_button(page, PIN).click()
    expect(head_button(page, UNPIN)).to_be_visible()
    page.wait_for_timeout(250)


def no_sideways_scroll(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def actions_in_view(page: Page) -> None:
    """Every row's actions sit inside the table's box and the window: nothing to scroll sideways to reach them."""
    scroll = page.locator(".table-scroll")
    assert scroll.evaluate("el => el.scrollWidth <= el.clientWidth + 1"), "the table scrolls sideways"
    box = scroll.bounding_box()
    width = page.viewport_size["width"] if page.viewport_size else DESKTOP
    for name in (re.compile(r"^Mark .* fixed$"), re.compile(r"^Ask about this: ")):
        for button in page.get_by_role("button", name=name).all()[:5]:
            b = button.bounding_box()
            assert b and box and b["x"] >= box["x"] - 0.5 and b["x"] + b["width"] <= box["x"] + box["width"] + 0.5
            assert b["x"] + b["width"] <= width


# --- A04b.1: navigation (DESIGN.md §4.1) --------------------------------------------------------------------------

def test_a04b_1_sidebar_lists_cves_and_shows_it_active(open_dash):
    page = open_dash()
    side = page.get_by_role("complementary", name="Main")
    names = side.locator(".side-links .side-link").evaluate_all(
        "els => els.map(el => el.getAttribute('aria-label') || el.querySelector('.side-label').textContent.trim())")
    assert names == ["Dashboard", "CVEs", "Settings", "Dev", "Ask Patch"]
    side.get_by_role("button", name="CVEs", exact=True).click()
    expect(page.get_by_role("heading", level=1)).to_have_text("CVEs")
    expect(page.locator(".crumb-path")).to_have_text("Pages / CVEs")
    expect(side.get_by_role("button", name="CVEs", exact=True)).to_have_attribute("aria-current", "page")
    expect(page.locator("[aria-current=page]")).to_have_count(1)
    assert urlparse(page.url).path == "/cves"
    page.go_back()  # each page is a history entry
    expect(page.get_by_role("heading", level=1)).to_have_text("Dashboard")
    page.reload()
    expect(page.get_by_role("heading", level=1)).to_have_text("Dashboard")


def test_a04b_1_phone_tab_bar_has_five_tabs_that_fit(open_cves):
    page = open_cves(width=PHONE)
    bar = page.locator(".sidenav")
    labels = bar.locator(".side-label").evaluate_all("els => els.map(el => el.firstChild.textContent.trim())")
    assert labels == ["Dashboard", "CVEs", "Settings", "Dev", "Ask"]
    for link in bar.locator(".side-link").all():
        b = link.bounding_box()
        assert b and b["x"] >= 0 and b["x"] + b["width"] <= PHONE
    expect(bar.get_by_role("button", name="CVEs", exact=True)).to_have_attribute("aria-current", "page")
    assert no_sideways_scroll(page)


# --- A04b.2: the CVEs page has the whole table, full width ----------------------------------------------------------

def test_a04b_2_cves_page_is_the_table_at_full_width_without_a_side_column(open_cves):
    page = open_cves()
    expect(page.locator(".dash-side")).to_have_count(0)
    expect(page.locator(".tile")).to_have_count(0)
    card = page.get_by_role("region", name="CVEs on your watchlist").bounding_box()
    content = page.locator("main .page").evaluate(
        "el => { const s = getComputedStyle(el); return el.clientWidth - parseFloat(s.paddingLeft) - parseFloat(s.paddingRight) }")
    assert card and abs(card["width"] - content) < 1
    expect(page.locator(".epss-credit")).to_contain_text("EPSS by FIRST")
    actions_in_view(page)


# Moved from the dashboard (A04.7): sorting, filters and paging, now on the CVEs page.
def test_a04_7_table_sorted_filtered_and_paged(open_cves, api_url):
    page = open_cves()
    first = api(api_url, "/cves?limit=25")
    expect_rows(page, [r["id"] for r in first["rows"]])
    expect(page.get_by_text(f"{first['total']} CVEs")).to_be_visible()
    page.get_by_role("button", name="Next page").click()
    expect(page.get_by_text(f"26–50 of {first['total']}")).to_be_visible()
    expect_rows(page, [r["id"] for r in api(api_url, "/cves?limit=25&offset=25")["rows"]])

    page.get_by_role("combobox", name="Product").select_option(label="Open WebUI")
    page.get_by_role("combobox", name="Severity").select_option(label="High or worse")
    filtered = api(api_url, "/cves?product=open-webui&severity_min=HIGH&limit=25")
    expect(page.get_by_text(f"{filtered['total']} CVEs")).to_be_visible()
    expect_rows(page, [r["id"] for r in filtered["rows"]])  # filters go back to page 1
    sev = page.locator("table.cves tbody tr td[data-label='Severity']").all_inner_texts()
    assert all(s.startswith(("High", "Critical")) for s in sev)


# Moved from the dashboard (A04.7): the row actions; the dashboard's tiles follow (one state).
def test_a04_7_row_actions_reload_the_table_and_the_tiles(open_cves, api_url):
    page = open_cves()
    open_before = api(api_url, "/dashboard")["kpis"]["open"]
    top = rows(page)[0]
    page.get_by_role("button", name=f"Mark {top} fixed").click()
    expect(page.get_by_role("link", name=top, exact=True)).to_have_count(0)
    second = rows(page)[0]
    page.get_by_role("button", name=f"Mark {second} not affected").click()
    expect(page.get_by_role("link", name=second, exact=True)).to_have_count(0)
    expect(page.get_by_text(f"{open_before - 2} CVEs")).to_be_visible()

    page.get_by_role("combobox", name="Status").select_option(label="Fixed")
    expect(page.get_by_role("link", name=top, exact=True)).to_be_visible()
    page.get_by_role("button", name=f"Reopen {top}").click()
    expect(page.get_by_text("No CVEs match these filters.")).to_be_visible()
    assert api(api_url, "/cves?status=not_affected")["rows"][0]["id"] == second
    page.get_by_role("button", name="Dashboard", exact=True).click()
    expect(tile(page, "Open CVEs").locator(".tile-value")).to_have_text(str(open_before - 1))


# --- A04b.3: filters in the URL ---------------------------------------------------------------------------------------

def test_a04b_3_a_link_opens_the_page_filtered_and_reload_keeps_the_filters(open_cves, api_url):
    page = open_cves("?product=langflow&severity=CRITICAL&status=open")
    expected = api(api_url, "/cves?product=langflow&severity_min=CRITICAL&status=open&limit=25")
    expect_rows(page, [r["id"] for r in expected["rows"]])
    expect(page.get_by_role("combobox", name="Product")).to_have_value("langflow")
    expect(page.get_by_role("combobox", name="Severity")).to_have_value("CRITICAL")
    expect(page.get_by_role("combobox", name="Status")).to_have_value("open")

    page.get_by_role("combobox", name="Status").select_option("all")
    page.get_by_role("combobox", name="Severity").select_option("HIGH")
    expect(page.get_by_role("combobox", name="Severity")).to_have_value("HIGH")
    assert params(page) == {"product": "langflow", "severity": "HIGH", "status": "all"}
    page.reload()
    expect(page.get_by_role("combobox", name="Severity")).to_have_value("HIGH")
    expect(page.get_by_role("combobox", name="Status")).to_have_value("all")
    expect_rows(page, [r["id"] for r in api(api_url, "/cves?product=langflow&severity_min=HIGH&status=all&limit=25")["rows"]])

    page.get_by_role("combobox", name="Product").select_option("")
    page.get_by_role("combobox", name="Severity").select_option("")
    page.get_by_role("combobox", name="Status").select_option("open")
    expect_rows(page, [r["id"] for r in api(api_url, "/cves?limit=25")["rows"]])
    assert urlparse(page.url).query == ""  # the defaults need no parameters


def test_a04b_3_unknown_filter_values_are_ignored(open_cves, api_url):
    page = open_cves("?severity=HUGE&status=closed&kev=maybe&since=yesterday")
    expect_rows(page, [r["id"] for r in api(api_url, "/cves?limit=25")["rows"]])
    expect(page.get_by_role("combobox", name="Severity")).to_have_value("")
    expect(page.get_by_role("combobox", name="Status")).to_have_value("open")


# --- A04b.4: the tiles link to the page with their filter -------------------------------------------------------------

@pytest.mark.parametrize("label", [t[0] for t in TILES])
def test_a04b_4_each_tile_opens_the_cves_page_with_its_filter(open_dash, api_url, label):
    page = open_dash()
    value = tile_value(page, label)
    link = page.get_by_role("link", name=re.compile(re.escape(label)))
    expect(link).to_have_count(1)
    link.click()
    expect(page.get_by_role("heading", level=1)).to_have_text("CVEs")
    expect(page.locator(".filters .meta")).to_have_text(re.compile(rf"^{value} CVEs "))
    p = params(page)
    if label == "Open and critical":
        assert p == {"severity": "CRITICAL"}
    elif label.startswith("Open and exploited"):
        assert p == {"kev": "1"}
        expect(page.get_by_role("checkbox", name="In CISA KEV only")).to_be_checked()
    elif label.startswith("New"):
        since = api(api_url, "/dashboard")["kpis"]["new_since"]
        assert p == {"status": "all", "since": since}
        expect(page.locator(".filters")).to_contain_text(f"Published since {since}")
    else:
        assert p == {}
    page.reload()  # the link's filter survives a reload
    expect(page.locator(".filters .meta")).to_have_text(re.compile(rf"^{value} CVEs "))


def test_a04b_4_extra_filters_can_be_cleared(open_cves, api_url):
    page = open_cves("?kev=1&status=all&since=2026-09-14")
    expect(page.locator(".filters")).to_contain_text("Published since 2026-09-14")
    page.get_by_role("button", name="Clear: published since 2026-09-14").click()
    expect(page.locator(".filters")).not_to_contain_text("Published since")
    page.get_by_role("checkbox", name="In CISA KEV only").uncheck()
    assert params(page) == {"status": "all"}
    total = api(api_url, "/cves?status=all&limit=1")["total"]
    expect(page.locator(".filters .meta")).to_have_text(re.compile(rf"^{total} CVEs "))


# --- A04b.5: the dashboard's "Top 5 open CVEs" card -------------------------------------------------------------------

def test_a04b_5_dashboard_has_the_top_5_card_instead_of_the_table(open_dash, api_url):
    page = open_dash()
    expect(page.locator("table.cves")).to_have_count(0)
    card = page.get_by_role("region", name="Top 5 open CVEs")
    top = api(api_url, "/cves?limit=5")["rows"]
    expect(card.locator("li .cve-id")).to_have_text([r["id"] for r in top])  # the table's order
    first = card.locator("li").first
    expect(first).to_contain_text(top[0]["product_name"])
    expect(first.locator(".sev")).to_be_visible()
    see_all = card.get_by_role("link", name="See all CVEs")
    expect(see_all).to_have_attribute("href", "/cves")
    see_all.click()
    expect(page.get_by_role("heading", level=1)).to_have_text("CVEs")
    expect_rows(page, [r["id"] for r in api(api_url, "/cves?limit=25")["rows"]])


def test_a04b_5_dashboard_keeps_its_other_parts(open_dash):
    page = open_dash()
    expect(page.locator(".hello")).to_be_visible()
    expect(page.locator(".tile")).to_have_count(4)
    titles = page.locator(".dash-main > .card h2").all_inner_texts()
    assert titles == ["Open CVEs by product and severity", "CVEs per month", "Open CVEs by OWASP category",
                      "Top 5 open CVEs"]
    side = page.locator(".dash-side > .card h2").all_inner_texts()
    assert side == ["Watchlist", "Latest AI incidents (MITRE ATLAS)", "Data freshness"]


# --- A04b.6: "Ask about this" over the CVEs page; the alert link still works ------------------------------------------

# "Ask about this" itself (opens the chat over the CVEs page, "on CVEs", the pinned chat) is A07.5 in
# test_chat_layout.py, which now runs on the CVEs page.

def test_a04b_6_alert_link_works_on_the_cves_page(open_cves):
    page = open_cves("#cve=CVE-2024-8309")
    banner = page.get_by_role("region", name="Alert")
    expect(banner).to_contain_text("You opened an alert for CVE-2024-8309.")
    banner.get_by_role("button", name="Explain it").click()
    expect(window(page).locator(".message.user")).to_have_text("Explain CVE-2024-8309 and how to defend against it.")
    assert urlparse(page.url).path == "/cves" and "cve=" not in page.url


# --- A04b.7: phone cards; A04b.8: the pinned chat -------------------------------------------------------------------

def test_a04b_7_phone_rows_are_stacked_cards(open_cves):
    page = open_cves(width=PHONE)
    assert no_sideways_scroll(page)
    expect(page.locator("table.cves thead")).to_be_hidden()
    first = page.locator("table.cves tbody tr").first
    assert first.evaluate("el => getComputedStyle(el).display") != "table-row"
    card = first.bounding_box()
    assert card and card["x"] >= 0 and card["x"] + card["width"] <= PHONE
    for label in ("Product", "Severity", "EPSS", "Status"):
        expect(first.locator(f"td[data-label='{label}']")).to_be_visible()
    cve = rows(page)[0]
    for name in (f"Mark {cve} fixed", f"Mark {cve} not affected", f"Ask about this: {cve}"):
        b = page.get_by_role("button", name=name).bounding_box()
        assert b and b["x"] >= 0 and b["x"] + b["width"] <= PHONE
    actions_in_view(page)


def test_a04b_8_pinned_chat_at_1400_keeps_the_row_actions_in_view(open_cves):
    page = open_cves()
    pin(page)
    actions_in_view(page)
    assert no_sideways_scroll(page)
    main = page.locator(".main-col").bounding_box()
    chat = window(page).bounding_box()
    assert main and chat and main["x"] + main["width"] <= chat["x"]


# --- A04b.9: motion and reduced motion (DESIGN.md §7.1) ------------------------------------------------------------

def test_a04b_9_cves_card_and_top_5_card_fade_up(open_cves, open_dash):
    page = open_cves()
    card = page.get_by_role("region", name="CVEs on your watchlist").evaluate(
        "el => [getComputedStyle(el).animationName, getComputedStyle(el).animationDuration, getComputedStyle(el).animationDelay]")
    assert card == ["fade-up", "0.45s", "0s"]
    dash = open_dash()
    top = dash.get_by_role("region", name="Top 5 open CVEs").evaluate(
        "el => [getComputedStyle(el).animationName, getComputedStyle(el).animationDelay]")
    assert top == ["fade-up", "0.24s"]


def test_a04b_9_reduced_motion_nothing_on_the_cves_page_moves(open_cves):
    page = open_cves(reduced=True)
    assert page.evaluate("document.getAnimations().length") == 0
    page.get_by_role("combobox", name="Severity").select_option("HIGH")
    page.get_by_role("button", name=f"Mark {rows(page)[0]} fixed").click()
    expect(page.locator("table.cves tbody tr").first).to_be_visible()
    assert page.evaluate("document.getAnimations().length") == 0
    phone = open_cves(width=PHONE, reduced=True)
    assert phone.evaluate("document.getAnimations().length") == 0


# --- A04b.10: light and dark, phone and desktop, pinned -------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a04b_10_light_dark_phone_and_desktop(open_cves, open_dash, browser_name, width, scheme):
    page = open_cves(width=width, scheme=scheme, reduced=True)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a04b-{browser_name}-{width}-{scheme}-cves.png")  # the first screen: rows readable at a glance
    assert no_sideways_scroll(page)
    surface = page.get_by_role("region", name="CVEs on your watchlist").evaluate("el => getComputedStyle(el).backgroundColor")
    assert surface == ("rgb(255, 255, 255)" if scheme == "light" else "rgb(26, 26, 46)")
    actions_in_view(page)
    if width == DESKTOP:
        pin(page)
        actions_in_view(page)
        assert no_sideways_scroll(page)
        page.screenshot(path=SHOTS / f"a04b-{browser_name}-{width}-{scheme}-cves-pinned.png")
    dash = open_dash(width=width, scheme=scheme, reduced=True)
    expect(dash.get_by_role("region", name="Top 5 open CVEs").locator("li")).to_have_count(5)
    dash.screenshot(path=SHOTS / f"a04b-{browser_name}-{width}-{scheme}-dashboard.png", full_page=True)
    assert no_sideways_scroll(dash)


# --- A04b.11: keyboard and names (DESIGN.md §10) ----------------------------------------------------------------------

def focused(page: Page) -> str:
    return page.evaluate("(() => { const a = document.activeElement;"
                         " return a.getAttribute('aria-label') || a.labels?.[0]?.textContent.trim() || a.textContent.trim() })()")


def visible_focus(page: Page) -> bool:
    s = page.evaluate("(() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineWidth] })()")
    return s[0] != "none" and float(s[1].rstrip("px")) >= 2


# Moved from the dashboard (A04.11): filters, row link, actions and paging by keyboard, now on the CVEs page.
def test_a04_11_keyboard_reaches_filters_actions_and_paging(open_cves):
    page = open_cves()
    top = rows(page)[0]
    page.get_by_role("combobox", name="Product").focus()
    seen = []
    for _ in range(200):
        page.keyboard.press("Tab")
        seen.append(focused(page))
        if seen[-1] == "Next page":
            break
    for name in ("Severity", "Status", "In CISA KEV only", top, f"Mark {top} fixed", f"Mark {top} not affected",
                 f"Ask about this: {top}", "FIRST", "Next page"):
        assert any(s.startswith(name) for s in seen), (name, seen)
    page.get_by_role("button", name=f"Mark {top} fixed").focus()
    assert visible_focus(page)
    page.keyboard.press("Enter")
    expect(page.get_by_role("link", name=top, exact=True)).to_have_count(0)


def test_a04b_11_keyboard_reaches_the_tile_links_and_the_top_5_card(open_dash):
    page = open_dash()
    page.get_by_role("button", name="Close Patch's welcome").focus()
    seen = []
    for _ in range(80):
        page.keyboard.press("Tab")
        seen.append(focused(page))
        if seen[-1].startswith("See all CVEs"):
            break
    for label, *_ in TILES:
        assert any(label in s for s in seen), (label, seen)
    assert seen[-1].startswith("See all CVEs"), seen
    assert visible_focus(page)
    page.get_by_role("link", name=re.compile(r"^\d+ Open CVEs$")).focus()
    assert visible_focus(page)
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", level=1)).to_have_text("CVEs")

"""Browser check (seam 3) for the snapshot additions: the EPSS column, the "possible match" badge (table and
lookup_cve card) and the sources' licences in the freshness panel. Check ids: A14.n, from ticket #16.
The table's checks run on the CVEs page since A04b (#26); the freshness panel stays on the dashboard.

Runs in Firefox and Chromium (run.sh). Expected values come from the backend's API (tested in
backend/tests/test_dashboard.py and test_tools.py); expected looks from docs/design/DESIGN.md.
"""
import re

import pytest
from playwright.sync_api import Page, Route, expect

from test_chat import Q2, ask, open_chat
from test_cves_page import open_cves  # noqa: F401 (fixture)
from test_dashboard import DESKTOP, PHONE, SHOTS, api, clean_state, contrast, open_dash, rgb_list  # noqa: F401 (fixtures)


def epss_text(e: dict) -> tuple[str, str]:
    score = "<0.1%" if e["score"] < 0.001 else f"{e['score'] * 100:.1f}%"
    n = int(e["percentile"] * 100)
    suffix = "th" if 11 <= n % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return score, f"{n}{suffix} percentile"


def table(page: Page):
    return page.locator("table.cves")


def row(page: Page, cve_id: str):
    return table(page).locator("tbody tr", has=page.get_by_role("link", name=cve_id, exact=True))


# --- EPSS column ---------------------------------------------------------------------------------------------------

def test_a14_9_epss_column_with_score_percentile_and_credit(open_cves, api_url):
    page = open_cves()
    expect(table(page).get_by_role("columnheader", name=re.compile("EPSS"))).to_be_visible()
    for r in api(api_url, "/cves?limit=25")["rows"][:5]:
        score, pct = epss_text(r["epss"])
        cell = row(page, r["id"]).locator("td.epss")
        expect(cell).to_contain_text(score)
        expect(cell).to_contain_text(pct)
    credit = page.locator(".epss-credit")
    expect(credit).to_contain_text("EPSS by FIRST")
    expect(credit.get_by_role("link", name="FIRST")).to_have_attribute("href", "https://www.first.org/epss")


# --- Possible match --------------------------------------------------------------------------------------------------

def test_a14_10_possible_match_badge_only_on_unconfirmed_guesses(open_cves, api_url):
    page = open_cves()
    page.get_by_role("combobox", name="Product").select_option(label="Langflow")
    rows = api(api_url, "/cves?product=langflow&limit=25")["rows"]
    expect(table(page).locator("tbody tr td:first-child a")).to_have_text([r["id"] for r in rows])
    flagged = [r["id"] for r in rows if r["possible_match"]]
    assert flagged, "page 1 of Langflow should have a possible match"
    badges = table(page).locator(".chip.possible")
    expect(badges).to_have_count(len(flagged))
    badge = row(page, flagged[0]).locator(".chip.possible")
    expect(badge).to_have_text("Possible match")
    assert "guessed from the description" in (badge.get_attribute("title") or "")


def test_a14_10_lookup_cve_card_shows_epss_and_possible_match(open_dash, api_url):
    page = open_dash()

    def as_possible_match(route: Route):
        resp = route.fetch()
        body = resp.json()
        body["tool_calls"][0]["result"] |= {"possible_match": True, "product_match": "unknown"}
        route.fulfill(response=resp, json=body)

    open_chat(page)
    answer = ask(page, Q2)  # looks up CVE-2024-8309: product from the CPE, so no badge
    answer.get_by_role("button", name=re.compile("Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    card = answer.locator(".cve-card")
    score, pct = epss_text({"score": 0.13738, "percentile": 0.96438})  # CVE-2024-8309 in the snapshot
    expect(card).to_contain_text(f"EPSS {score}")
    expect(card).to_contain_text(pct)
    expect(card.locator(".chip.possible")).to_have_count(0)

    page.route("**/chat", as_possible_match)
    answer = ask(page, Q2)
    answer.get_by_role("button", name=re.compile("Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    expect(answer.locator(".cve-card .chip.possible")).to_have_text("Possible match")


# --- Freshness panel ---------------------------------------------------------------------------------------------------

def test_a14_11_freshness_lists_every_licence_attribution_and_the_nvd_notice(open_dash, api_url):
    page = open_dash()
    panel = page.get_by_role("region", name="Data freshness")
    sources = api(api_url, "/dashboard")["freshness"]
    items = panel.locator(".side-list > li")
    expect(items).to_have_count(len(sources))
    for s, item in zip(sources, items.all()):
        expect(item).to_contain_text(s["licence"])
        expect(item).to_contain_text(s["attribution"])
    expect(panel).to_contain_text("This product uses the NVD API but is not endorsed or certified by the NVD.")
    expect(panel).to_contain_text("EPSS by FIRST")
    expect(panel).to_contain_text("CC0 1.0")


# --- Motion, themes, widths, keyboard ----------------------------------------------------------------------------------

def test_a14_12_reduced_motion_nothing_new_moves(open_cves, api_url):
    page = open_cves(reduced=True)
    page.get_by_role("combobox", name="Product").select_option(label="Langflow")
    expect(table(page).locator(".chip.possible").first).to_be_visible()
    expect(page.locator(".epss-credit")).to_be_visible()
    assert page.evaluate("document.getAnimations().length") == 0
    moving = page.locator(".chip.possible, td.epss, .epss-credit, .freshness-notice").evaluate_all(
        "els => els.filter(el => { const s = getComputedStyle(el);"
        " return s.animationName !== 'none' || (s.transitionDuration.split(',').some(d => parseFloat(d) > 0)"
        " && s.transitionProperty !== 'none') })")
    assert moving == []


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a14_13_light_dark_phone_and_desktop(open_cves, browser_name, width, scheme):
    page = open_cves(width=width, scheme=scheme, reduced=True)
    page.get_by_role("combobox", name="Product").select_option(label="Langflow")
    badge = table(page).locator(".chip.possible").first
    expect(badge).to_be_visible()
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a14-{browser_name}-{width}-{scheme}.png", full_page=True)
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    colours = badge.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
    fg, bg = rgb_list(colours[0])[0], rgb_list(colours[1])[0]
    assert contrast(fg, bg) >= 4.5, colours  # small text on a soft fill (DESIGN.md §5)
    for cell in (page.locator("td.epss").first, page.locator(".epss-credit")):
        c = cell.evaluate("el => getComputedStyle(el).color")
        card = page.get_by_role("region", name="CVEs on your watchlist").evaluate("el => getComputedStyle(el).backgroundColor")
        assert contrast(rgb_list(c)[0], rgb_list(card)[0]) >= 4.5
    # The new column doesn't push the row actions out of view: test_cves_page.py checks it (A04b.2, A04b.8).


def test_a14_14_keyboard_reaches_the_epss_credit_and_the_source_links(open_cves, open_dash):
    page = open_cves()
    page.get_by_role("combobox", name="Status").focus()
    seen = []
    for _ in range(200):
        page.keyboard.press("Tab")
        seen.append(page.evaluate("document.activeElement.textContent.trim()"))
        if seen[-1] == "FIRST":
            break
    assert seen[-1] == "FIRST", seen
    outline = page.evaluate("(() => { const s = getComputedStyle(document.activeElement);"
                            " return [s.outlineStyle, s.outlineWidth] })()")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2
    dash = open_dash()  # the freshness panel's EPSS source link, on the dashboard
    dash.get_by_role("region", name="Watchlist", exact=True).get_by_label("vLLM").focus()
    seen = []
    for _ in range(40):
        dash.keyboard.press("Tab")
        seen.append(dash.evaluate("document.activeElement.textContent.trim()"))
        if seen[-1].startswith("EPSS"):
            break
    assert seen[-1].startswith("EPSS"), seen

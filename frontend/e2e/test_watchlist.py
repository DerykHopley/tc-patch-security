"""Browser check (seam 3) for the watchlist's move (A15b, #30): editing in a Watchlist card on Settings, and on the
dashboard a product filter. Check ids: A15b.n, one per acceptance criterion of the ticket.

The dashboard editor's checks (A04.8, A15.6, A15.11) moved here, to the Settings card. Runs in Firefox and Chromium
(run.sh). Expected numbers come from the backend's API (tested on its own in backend/tests/test_dashboard.py);
expected looks from docs/design/DESIGN.md §5.7, §5.9 and §10. `clean_state` puts the watchlist, every product's
fields and every status back before and after each test.
"""
import json
import re

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from test_chat import ask
from test_cves_page import focused, no_sideways_scroll, params, visible_focus, window  # noqa: F401
from test_dashboard import (  # noqa: F401 (fixtures)
    DEFAULT_WATCHLIST, DESKTOP, PHONE, SHOTS, TILES, api, clean_state, contrast, open_dash, rgb_list, tile, tile_value,
)
from test_fix_first import chat_bodies, chip, open_chat

LANGFLOW_KEV = "CVE-2025-3248"  # Langflow, critical, in KEV; fixed in 1.3.0


@pytest.fixture
def open_watchlist(browser: Browser, ui_url: str, clean_state):
    """Opens Settings in a fresh context and waits for the Watchlist card's product fields."""
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(f"{ui_url}/settings")
        expect(card(page).get_by_role("group", name="Langflow")).to_be_visible()
        page.evaluate("document.fonts.ready.then(() => null)")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def card(page: Page) -> Locator:
    return page.get_by_role("region", name="Watchlist", exact=True)


def bar(page: Page) -> Locator:
    return page.locator(".save-bar output")


def save(page: Page) -> None:
    page.get_by_role("button", name="Save changes").click()
    expect(bar(page)).to_have_text("✓ Changes saved")


def chips(page: Page) -> Locator:
    return card(page).get_by_role("group", name="Show the tiles, charts and Top 5 for")


def chip_button(page: Page, name: str) -> Locator:
    return chips(page).get_by_role("button", name=re.compile(rf"^{re.escape(name)}\b"))


def top5(page: Page) -> Locator:
    return page.get_by_role("region", name="Top 5 open CVEs").locator("li .cve-id")


def kpis(api_url: str, query: str = "") -> list[int]:
    k = api(api_url, f"/dashboard{query}")["kpis"]
    return [k["open"], k["critical"], k["kev"], k["new_30d"]]


def tiles(page: Page, api_url: str, query: str = "") -> None:
    """Waits until the four tiles show the API's numbers for this filter."""
    for (label, *_), value in zip(TILES, kpis(api_url, query)):
        expect(tile(page, label).locator(".tile-value")).to_have_text(str(value))


# --- A15b.1: the Settings card has everything the dashboard editor had ------------------------------------------------

def test_a15b_1_add_and_remove_products_saved_with_the_save_bar(open_watchlist, api_url):
    page = open_watchlist()
    expect(bar(page)).to_have_text("All changes saved")
    card(page).get_by_label("vLLM", exact=True).check()
    card(page).get_by_label("LangChain", exact=True).uncheck()
    expect(bar(page)).to_have_text("Unsaved changes")
    assert "langchain" in api(api_url, "/watchlist")["watchlist"]  # nothing saved before the bar's button
    save(page)
    watchlist = api(api_url, "/watchlist")["watchlist"]
    assert "vllm" in watchlist and "langchain" not in watchlist
    page.reload()
    expect(card(page).get_by_label("vLLM", exact=True)).to_be_checked()
    expect(card(page).get_by_label("LangChain", exact=True)).not_to_be_checked()


def test_a15b_1_discard_brings_back_the_saved_watchlist(open_watchlist, api_url):
    page = open_watchlist()
    card(page).get_by_label("Dify", exact=True).check()
    card(page).get_by_role("group", name="Langflow").get_by_label("Version").fill("1.2.0")
    page.get_by_role("button", name="Discard").click()
    expect(card(page).get_by_label("Dify", exact=True)).not_to_be_checked()
    expect(card(page).get_by_role("group", name="Langflow").get_by_label("Version")).to_have_value("")
    expect(bar(page)).to_have_text("All changes saved")
    assert api(api_url, "/watchlist")["watchlist"] == DEFAULT_WATCHLIST


def test_a15b_1_usage_version_and_internet_facing_per_product(open_watchlist, api_url):
    page = open_watchlist()
    langflow = card(page).get_by_role("group", name="Langflow")
    expect(langflow.get_by_label("Usage")).to_have_value("self_hosted")
    expect(card(page).get_by_role("group", name="LangChain").get_by_label("Usage")).to_have_value("library")
    langflow.get_by_label("Usage").select_option(label="Comes in through another package")
    langflow.get_by_label("Version").fill("1.2.0")
    langflow.get_by_label("Internet-facing").check()
    save(page)
    saved = next(p for p in api(api_url, "/watchlist")["products"] if p["product"] == "langflow")
    assert (saved["usage"], saved["version"], saved["internet_facing"]) == ("transitive", "1.2.0", True)
    page.get_by_role("button", name="CVEs", exact=True).click()
    cell = page.locator("table.cves tbody tr", has=page.get_by_role("link", name=LANGFLOW_KEV, exact=True))
    expect(cell.locator("td[data-label='Verdict'] .verdict")).to_have_text("Affected")


def test_a15b_1_a_ticked_product_shows_its_fields_and_why_a_version_wont_help(open_watchlist):
    page = open_watchlist()
    expect(card(page).get_by_role("group", name="Dify")).to_have_count(0)
    card(page).get_by_label("Dify", exact=True).check()
    expect(card(page).get_by_role("group", name="Dify")).to_contain_text(
        "No version data for Dify, so its verdicts stay unknown.")
    card(page).get_by_label("llama.cpp", exact=True).check()
    expect(card(page).get_by_role("group", name="llama.cpp")).to_contain_text("only code commits")
    expect(card(page).get_by_role("group", name="Ollama").get_by_label("Version")).to_have_attribute(
        "placeholder", "e.g. v0.12.3")
    expect(card(page).get_by_role("group", name="Langflow").get_by_label("Version")).to_have_attribute(
        "placeholder", "e.g. 0.3.27")


def test_a15b_1_a_bad_version_is_rejected_in_the_card(open_watchlist, api_url):
    page = open_watchlist()
    card(page).get_by_role("group", name="Ollama").get_by_label("Version").fill("latest")
    page.get_by_role("button", name="Save changes").click()
    expect(card(page).get_by_role("alert")).to_contain_text("'latest' isn't a Go module version, which Ollama uses.")
    expect(bar(page)).to_have_text("Unsaved changes")  # still there to fix and save again
    assert next(p for p in api(api_url, "/watchlist")["products"] if p["product"] == "ollama")["version"] is None
    card(page).get_by_role("group", name="Ollama").get_by_label("Version").fill("v0.12.3")
    save(page)
    expect(card(page).get_by_role("alert")).to_have_count(0)


def test_a15b_1_an_unknown_product_gets_a_plain_message_in_the_card(open_watchlist):
    page = open_watchlist()
    page.route("**/watchlist", lambda route: route.continue_(post_data=json.dumps({"products": ["ollama", "notion"]}))
               if route.request.method == "PUT" else route.continue_())
    card(page).get_by_label("vLLM", exact=True).check()
    page.get_by_role("button", name="Save changes").click()
    expect(card(page).get_by_role("alert")).to_contain_text("'notion' isn't a product I track. Choose from:")


def test_a15b_1_the_card_saves_with_the_other_settings_in_one_click(open_watchlist, api_url):
    page = open_watchlist()
    page.get_by_label("Minimum severity").select_option("CRITICAL")
    card(page).get_by_label("vLLM", exact=True).check()
    save(page)
    assert "vllm" in api(api_url, "/watchlist")["watchlist"]
    assert api(api_url, "/settings")["settings"]["alerts"]["min_severity"] == "CRITICAL"
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})  # the settings aren't in clean_state


# --- A15b.2: the dashboard's product filter ---------------------------------------------------------------------------

def test_a15b_2_chips_filter_the_tiles_charts_and_top_5(open_dash, api_url):
    page = open_dash()
    all_chip = chips(page).get_by_role("button", name="All", exact=True)
    expect(all_chip).to_have_attribute("aria-pressed", "true")
    expect(chips(page).get_by_role("button")).to_have_count(1 + len(DEFAULT_WATCHLIST))
    chip_button(page, "Langflow").click()
    expect(page).to_have_url(re.compile(r"/\?product=langflow$"))
    expect(chip_button(page, "Langflow")).to_have_attribute("aria-pressed", "true")
    expect(all_chip).to_have_attribute("aria-pressed", "false")
    tiles(page, api_url, "?product=langflow")
    expect(page.locator(".chart").first.locator(".bar-row")).to_have_count(1)
    expect(top5(page)).to_have_text([r["id"] for r in api(api_url, "/cves?product=langflow&limit=5")["rows"]])
    chip_button(page, "Ollama").click()
    assert params(page) == {"product": "langflow,ollama"}
    tiles(page, api_url, "?product=langflow,ollama")
    expect(page.locator(".chart").first.locator(".bar-row")).to_have_count(2)
    expect(top5(page)).to_have_text([r["id"] for r in api(api_url, "/cves?product=langflow,ollama&limit=5")["rows"]])
    chip_button(page, "Langflow").click()  # a second click takes it out again
    assert params(page) == {"product": "ollama"}
    all_chip.click()
    expect(page).to_have_url(re.compile(r"/$"))  # the default adds nothing to the URL
    tiles(page, api_url)


def test_a15b_2_the_filter_lives_in_the_url_and_survives_a_reload(open_dash, api_url, ui_url):
    page = open_dash()
    page.goto(f"{ui_url}/?product=ollama,langflow")
    expect(chip_button(page, "Ollama")).to_have_attribute("aria-pressed", "true")
    expect(chip_button(page, "Langflow")).to_have_attribute("aria-pressed", "true")
    tiles(page, api_url, "?product=langflow,ollama")
    page.reload()
    tiles(page, api_url, "?product=langflow,ollama")
    page.goto(f"{ui_url}/?product=notion,vllm")  # unknown or unwatched: ignored, and dropped from the URL
    expect(chips(page).get_by_role("button", name="All", exact=True)).to_have_attribute("aria-pressed", "true")
    expect(page).to_have_url(re.compile(r"/$"))
    tiles(page, api_url)


@pytest.mark.parametrize("label", [t[0] for t in TILES])
def test_a15b_2_tile_links_carry_the_filter_to_the_cves_page(open_dash, api_url, label):
    page = open_dash()
    chip_button(page, "Langflow").click()
    chip_button(page, "Ollama").click()
    tiles(page, api_url, "?product=langflow,ollama")  # the tiles have caught up with the filter
    expect(page.locator(".top-cves .see-all")).to_have_attribute("href", "/cves?product=langflow,ollama")
    value = tile_value(page, label)
    tile(page, label).click()
    expect(page.get_by_role("heading", level=1)).to_have_text("CVEs")
    assert params(page)["product"] == "langflow,ollama"
    expect(page.locator(".filters .meta")).to_have_text(re.compile(rf"^{value} CVEs "))  # the tile's number
    expect(page.get_by_role("combobox", name="Product").locator("option:checked")).to_have_text("Langflow + Ollama")


def test_a15b_2_see_all_cves_carries_the_filter(open_dash, api_url):
    page = open_dash()
    chip_button(page, "Langflow").click()
    page.get_by_role("link", name="See all CVEs").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("CVEs")
    assert params(page) == {"product": "langflow"}
    expect(page.get_by_role("combobox", name="Product")).to_have_value("langflow")
    total = api(api_url, "/cves?product=langflow&limit=1")["total"]
    expect(page.locator(".filters .meta")).to_have_text(re.compile(rf"^{total} CVEs "))


def test_a15b_2_chips_flag_open_kev_and_link_to_settings(open_dash):
    page = open_dash()
    expect(chip_button(page, "Langflow")).to_have_accessible_name("Langflow: open CVEs in CISA KEV")
    expect(chip_button(page, "LangChain")).to_have_accessible_name("LangChain")
    edit = card(page).get_by_role("link", name="Edit watchlist in Settings")
    expect(edit).to_have_attribute("href", "/settings")
    edit.click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Settings")
    expect(card(page).get_by_role("group", name="Langflow")).to_be_visible()


# --- A15b.4: one truth: Settings, Patch and the dashboard ---------------------------------------------------------------

def test_a15b_4_a_product_patch_adds_shows_on_the_dashboard_at_once(open_dash, api_url, ui_url):
    api(api_url, "/watchlist", "PUT", {"products": [p for p in DEFAULT_WATCHLIST if p != "ollama"]})
    page = open_dash()
    page.goto(f"{ui_url}/?product=langflow")
    expect(chip_button(page, "Ollama")).to_have_count(0)
    open_chat(page)
    ask(page, "Add Ollama to my watchlist")
    expect(chip_button(page, "Ollama")).to_have_attribute("aria-pressed", "false")  # no reload needed
    expect(chip_button(page, "Langflow")).to_have_attribute("aria-pressed", "true")  # the filter stays


def test_a15b_4_a_product_patch_adds_shows_in_the_settings_card_at_once(open_watchlist, api_url):
    api(api_url, "/watchlist", "PUT", {"products": [p for p in DEFAULT_WATCHLIST if p != "ollama"]})
    page = open_watchlist()
    expect(card(page).get_by_label("Ollama", exact=True)).not_to_be_checked()
    open_chat(page)
    ask(page, "Add Ollama to my watchlist")
    expect(card(page).get_by_label("Ollama", exact=True)).to_be_checked()
    expect(bar(page)).to_have_text("All changes saved")  # the saved state moved, not a draft


def test_a15b_4_removing_the_filtered_product_in_settings_drops_it_from_the_filter(open_dash, api_url, ui_url):
    page = open_dash()
    page.goto(f"{ui_url}/?product=langflow,ollama")
    tiles(page, api_url, "?product=langflow,ollama")
    page.get_by_role("button", name="Settings", exact=True).click()
    card(page).get_by_label("Ollama", exact=True).uncheck()
    save(page)
    page.go_back()  # the dashboard's own URL still says langflow,ollama
    expect(page).to_have_url(re.compile(r"/\?product=langflow$"))
    expect(chip_button(page, "Ollama")).to_have_count(0)
    tiles(page, api_url, "?product=langflow")


# --- A15b.5: accessible chips --------------------------------------------------------------------------------------------

def test_a15b_5_chips_are_toggle_buttons_by_keyboard_with_visible_focus(open_dash):
    page = open_dash()
    chips(page).get_by_role("button", name="All", exact=True).focus()
    seen = []
    for _ in range(len(DEFAULT_WATCHLIST) + 1):
        seen.append(focused(page).removeprefix("✓"))  # the tick is hidden from screen readers
        assert visible_focus(page), seen[-1]
        page.keyboard.press("Tab")
    assert seen[0] == "All" and seen[1:] == [n for n in seen[1:] if n]  # every chip named
    assert focused(page) == "Edit watchlist in Settings →"
    chip_button(page, "Ollama").focus()
    page.keyboard.press("Enter")
    expect(chip_button(page, "Ollama")).to_have_attribute("aria-pressed", "true")
    page.keyboard.press("Space")
    expect(chip_button(page, "Ollama")).to_have_attribute("aria-pressed", "false")
    expect(page).to_have_url(re.compile(r"/$"))


def test_a15b_5_keyboard_reaches_each_products_fields_in_settings(open_watchlist):
    page = open_watchlist()
    card(page).get_by_label("LangChain", exact=True).focus()
    seen = []
    for _ in range(80):
        page.keyboard.press("Tab")
        if not card(page).evaluate("el => el.contains(document.activeElement)"):
            break
        seen.append(focused(page))

    def count(name):  # a select's label text includes its options
        return sum(s.startswith(name) for s in seen)

    n = len(DEFAULT_WATCHLIST)
    assert (count("Usage"), count("Version"), count("Internet-facing")) == (n, n, n), seen
    card(page).get_by_role("group", name="Langflow").get_by_label("Version").focus()
    assert visible_focus(page)


# --- A15b.6: the page context carries the dashboard's filter --------------------------------------------------------------

def test_a15b_6_patch_knows_the_dashboards_filter(open_dash, ui_url):
    page = open_dash()
    page.goto(f"{ui_url}/?product=langflow,ollama")
    expect(chip_button(page, "Ollama")).to_have_attribute("aria-pressed", "true")
    bodies = chat_bodies(page)
    open_chat(page)
    expect(chip(page)).to_have_text("on Dashboard · Langflow + Ollama")
    ask(page, "Explain CWE-918")
    assert bodies[-1]["page"] == {"page": "dashboard", "product": "langflow,ollama"}
    chips(page).get_by_role("button", name="All", exact=True).click()
    expect(chip(page)).to_have_text("on Dashboard")
    ask(page, "Explain CWE-918")
    assert bodies[-1]["page"] == {"page": "dashboard"}


# --- A15b.8: phone and desktop, light and dark ------------------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a15b_8_settings_card_and_dashboard_filter_at_both_widths_in_both_themes(open_watchlist, open_dash,
                                                                                  browser_name, width, scheme):
    SHOTS.mkdir(exist_ok=True)
    page = open_watchlist(width=width, scheme=scheme, reduced=True)
    assert no_sideways_scroll(page)
    box = card(page).bounding_box()
    for group in card(page).get_by_role("group").all():
        g = group.bounding_box()
        assert box and g and g["x"] >= box["x"] and g["x"] + g["width"] <= box["x"] + box["width"] + 0.5
    card(page).screenshot(path=SHOTS / f"a15b-{browser_name}-{width}-{scheme}-settings.png")
    dash = open_dash(width=width, scheme=scheme, reduced=True)
    chip_button(dash, "Langflow").click()
    expect(chip_button(dash, "Langflow")).to_have_attribute("aria-pressed", "true")
    assert no_sideways_scroll(dash)
    filter_card = card(dash).bounding_box()
    for b in chips(dash).get_by_role("button").all():
        c = b.bounding_box()
        assert filter_card and c and c["x"] >= filter_card["x"] and c["x"] + c["width"] <= filter_card["x"] + filter_card["width"]
        assert c["height"] >= 24  # a target big enough to tap (WCAG 2.5.8)
    picked = chip_button(dash, "Langflow").evaluate(
        "el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
    assert contrast(rgb_list(picked[0])[0], rgb_list(picked[1])[0]) >= 4.5, picked
    card(dash).screenshot(path=SHOTS / f"a15b-{browser_name}-{width}-{scheme}-filter.png")
    dash.screenshot(path=SHOTS / f"a15b-{browser_name}-{width}-{scheme}-dashboard.png", full_page=True)

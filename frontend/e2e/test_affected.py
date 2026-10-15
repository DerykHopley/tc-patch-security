"""Browser check (seam 3) for "Am I affected?": the verdict column, its filter and the "Mark not affected?" suggestion
on the CVEs page, the watchlist editor's usage, version and internet-facing fields, and the check_affected card in
the chat. Check ids: A15.n, from ticket #17.

Runs in Firefox and Chromium (run.sh). Expected verdicts come from the backend's API (the rules are table-tested in
backend/tests/test_verdict.py); expected looks from docs/design/DESIGN.md §5.3, §5.9, §7 and §10.
Every test puts the state back (`clean_state` resets the watchlist and each product's fields).
"""
import re

import pytest
from playwright.sync_api import Locator, Page, expect

from test_chat import ask
from test_cves_page import actions_in_view, focused, no_sideways_scroll, open_cves, params, pin, visible_focus, window  # noqa: F401
from test_dashboard import (  # noqa: F401 (fixtures)
    DEFAULT_WATCHLIST, DESKTOP, PHONE, SHOTS, api, clean_state, confirm, contrast, expect_rows, open_dash, rgb_list, rows,
)

LANGFLOW_KEV = "CVE-2025-3248"  # Langflow, critical, in KEV; fixed in 1.3.0


def set_stack(api_url: str, **fields: dict) -> None:
    """The default watchlist, with fields for some products (by id)."""
    api(api_url, "/watchlist", "PUT", {"products": [{"product": p, **fields.get(p, {})} for p in DEFAULT_WATCHLIST]})


def verdict_cell(page: Page, cve: str) -> Locator:
    return page.locator("table.cves tbody tr", has=page.get_by_role("link", name=cve, exact=True)).locator(
        "td[data-label='Verdict']")


def suggestion(page: Page, cve: str) -> Locator:
    return page.get_by_role("button", name=f"Mark {cve} not affected? Suggested by the version check")


def editor(page: Page) -> Locator:
    return page.get_by_role("region", name="Watchlist", exact=True)


# --- A15.5: the CVEs page: verdict column, filter, the one-click suggestion -------------------------------------------

def test_a15_5_verdict_column_with_reason_fixed_version_and_who_acts(open_cves, api_url):
    set_stack(api_url, langflow={"version": "1.2.0", "usage": "transitive"})
    page = open_cves("?product=langflow&kev=1")
    expect(page.locator("table.cves thead th", has_text="Verdict")).to_have_count(1)
    cell = verdict_cell(page, LANGFLOW_KEV)
    expect(cell.locator(".verdict")).to_have_text("Affected")
    expect(cell).to_contain_text("1.2.0 is before the fixed version 1.3.0 (langflow)")
    expect(cell).to_contain_text("Who acts: upstream")
    expect(suggestion(page, LANGFLOW_KEV)).to_have_count(0)  # only on "not affected" rows

    page = open_cves("?product=langchain")
    first = rows(page)[0]
    expect(verdict_cell(page, first).locator(".verdict")).to_have_text("Unknown")
    expect(verdict_cell(page, first)).to_contain_text(re.compile("no version given|no version data for this CVE"))


def test_a15_5_verdict_filter_lives_in_the_url(open_cves, api_url):
    set_stack(api_url, langflow={"version": "1.3.0"})
    page = open_cves()
    page.get_by_role("combobox", name="Verdict").select_option(label="Not affected")
    assert params(page) == {"verdict": "not_affected"}
    expected = api(api_url, "/cves?verdict=not_affected&limit=25")
    assert expected["total"] > 0
    expect_rows(page, [r["id"] for r in expected["rows"]])
    expect(page.locator(".filters .meta")).to_have_text(re.compile(rf"^{expected['total']} CVEs "))
    page.reload()
    expect(page.get_by_role("combobox", name="Verdict")).to_have_value("not_affected")
    expect_rows(page, [r["id"] for r in expected["rows"]])
    bad = open_cves("?verdict=maybe")
    expect(bad.get_by_role("combobox", name="Verdict")).to_have_value("")
    expect_rows(bad, [r["id"] for r in api(api_url, "/cves?limit=25")["rows"]])


def test_a15_5_mark_not_affected_is_a_suggestion_only_the_user_clicks(open_cves, api_url):
    set_stack(api_url, langflow={"version": "99.0.0"})
    page = open_cves("?product=langflow&verdict=not_affected")
    first = rows(page)[0]
    expect(verdict_cell(page, first).locator(".verdict")).to_have_text("Not affected")
    # Showing a not-affected verdict changes nothing: every CVE is still open.
    assert api(api_url, "/cves?status=not_affected&limit=1")["total"] == 0
    button = suggestion(page, first)
    expect(button).to_be_visible()
    expect(button).to_have_text("Mark not affected?")
    expect(page.get_by_role("button", name=f"Mark {first} not affected", exact=True)).to_have_count(0)  # one way
    button.click()  # A16b: the dialog opens with "vulnerable code not present" and the verdict's reason; the user confirms
    d = page.get_by_role("dialog")
    expect(d.get_by_role("radio", name="Vulnerable code not present")).to_be_checked()
    expect(d.get_by_role("textbox", name="Note (optional)")).to_have_value(re.compile(r"at or after the fixed version"))
    confirm(page)
    expect(page.get_by_role("link", name=first, exact=True)).to_have_count(0)
    assert [r["id"] for r in api(api_url, "/cves?status=not_affected&limit=200")["rows"]] == [first]
    unknown = open_cves("?verdict=unknown")
    expect(unknown.get_by_role("button", name=re.compile(r"Suggested by the version check$"))).to_have_count(0)


# --- A15.6: the watchlist editor's fields ----------------------------------------------------------------------------

def test_a15_6_usage_version_and_internet_facing_per_product(open_dash, api_url):
    page = open_dash()
    langflow = editor(page).get_by_role("group", name="Langflow")
    expect(langflow.get_by_label("Usage")).to_have_value("self_hosted")
    expect(editor(page).get_by_role("group", name="LangChain").get_by_label("Usage")).to_have_value("library")
    langflow.get_by_label("Usage").select_option(label="Comes in through another package")
    langflow.get_by_label("Version").fill("1.2.0")
    langflow.get_by_label("Internet-facing").check()
    editor(page).get_by_role("button", name="Save watchlist").click()
    expect(editor(page).get_by_text("Saved.")).to_be_visible()
    saved = next(p for p in api(api_url, "/watchlist")["products"] if p["product"] == "langflow")
    assert (saved["usage"], saved["version"], saved["internet_facing"]) == ("transitive", "1.2.0", True)
    expect(editor(page).get_by_role("group", name="Langflow").get_by_label("Version")).to_have_value("1.2.0")
    page.get_by_role("button", name="CVEs", exact=True).click()
    expect(verdict_cell(page, LANGFLOW_KEV).locator(".verdict")).to_have_text("Affected")


def test_a15_6_a_ticked_product_shows_its_fields_and_why_a_version_wont_help(open_dash):
    page = open_dash()
    expect(editor(page).get_by_role("group", name="Dify")).to_have_count(0)
    editor(page).get_by_label("Dify", exact=True).check()
    dify = editor(page).get_by_role("group", name="Dify")
    expect(dify).to_contain_text("No version data for Dify, so its verdicts stay unknown.")
    editor(page).get_by_label("llama.cpp", exact=True).check()
    expect(editor(page).get_by_role("group", name="llama.cpp")).to_contain_text("only code commits")
    expect(editor(page).get_by_role("group", name="Ollama").get_by_label("Version")).to_have_attribute(
        "placeholder", "e.g. v0.12.3")


def test_a15_6_a_bad_version_is_rejected_with_a_plain_message(open_dash, api_url):
    page = open_dash()
    editor(page).get_by_role("group", name="Ollama").get_by_label("Version").fill("latest")
    editor(page).get_by_role("button", name="Save watchlist").click()
    expect(editor(page).get_by_role("alert")).to_contain_text("'latest' isn't a Go module version, which Ollama uses.")
    assert next(p for p in api(api_url, "/watchlist")["products"] if p["product"] == "ollama")["version"] is None


# --- A15.7: the chat: check_affected and its card ------------------------------------------------------------------

def test_a15_7_am_i_affected_shows_the_verdict_card_and_changes_nothing(open_cves, api_url):
    set_stack(api_url, langflow={"version": "1.2.0"})
    page = open_cves()
    page.keyboard.press("Control+k")
    expect(window(page)).to_be_visible()
    answer = ask(page, f"Am I affected by {LANGFLOW_KEV}?")
    expect(answer).to_contain_text("affected by the version check")
    expect(answer).to_contain_text("Fixed in 1.3.0")
    answer.get_by_role("button", name=re.compile("Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    card = answer.locator(".tool-card .affected-card")
    expect(card.locator(".verdict")).to_have_text("Affected")
    expect(card).to_contain_text("1.2.0 is before the fixed version 1.3.0 (langflow)")
    expect(card).to_contain_text("Fixed in 1.3.0")
    expect(card).to_contain_text("Who acts: you")
    assert api(api_url, "/cves?status=all&product=langflow&limit=200")["rows"] and \
        api(api_url, "/cves?status=not_affected&limit=1")["total"] == 0


# --- A15.9: reduced motion -----------------------------------------------------------------------------------------

# Reduced motion: in the shared check, test_reduced_motion.py (scene a15_9).


# --- A15.10: light and dark, phone and desktop -------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a15_10_light_dark_phone_and_desktop(open_cves, open_dash, api_url, browser_name, width, scheme):
    set_stack(api_url, langflow={"version": "99.0.0"}, langchain={"version": "0.2.10"})
    page = open_cves(width=width, scheme=scheme, reduced=True)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a15-{browser_name}-{width}-{scheme}-cves.png")
    assert no_sideways_scroll(page)
    actions_in_view(page)
    for value, name in (("affected", "Affected"), ("not_affected", "Not affected"), ("unknown", "Unknown")):
        page.get_by_role("combobox", name="Verdict").select_option(value)
        chip = page.locator("table.cves .verdict").first
        expect(chip).to_have_text(name)
        text, bg = chip.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
        assert contrast(rgb_list(text)[0], rgb_list(bg)[0]) >= 4.5, (name, text, bg)
    page.get_by_role("combobox", name="Verdict").select_option("not_affected")
    # The filter reloads the table: wait on the filtered table's own first row, as in A15.9 (CI race, run #62).
    expect(page).to_have_url(re.compile(r"verdict=not_affected"))
    first_suggestion = page.locator("table.cves tbody tr").first.get_by_role(
        "button", name=re.compile(r"Suggested by the version check$"))
    expect(first_suggestion).to_be_visible()
    b = first_suggestion.bounding_box()
    assert b and b["x"] >= 0 and b["x"] + b["width"] <= width
    if width == DESKTOP:
        pin(page)
        actions_in_view(page)
        assert no_sideways_scroll(page)
        b = first_suggestion.bounding_box()
        chat = window(page).bounding_box()
        assert b and chat and b["x"] + b["width"] <= chat["x"]
    dash = open_dash(width=width, scheme=scheme, reduced=True)
    ed = editor(dash)
    ed.scroll_into_view_if_needed()
    dash.screenshot(path=SHOTS / f"a15-{browser_name}-{width}-{scheme}-watchlist.png", full_page=True)
    assert no_sideways_scroll(dash)
    card = ed.bounding_box()
    for group in ed.get_by_role("group").all():
        g = group.bounding_box()
        assert card and g and g["x"] >= card["x"] and g["x"] + g["width"] <= card["x"] + card["width"] + 0.5


# --- A15.11: keyboard and names ------------------------------------------------------------------------------------

def test_a15_11_keyboard_reaches_the_verdict_filter_and_the_suggestion(open_cves, api_url):
    set_stack(api_url, langflow={"version": "99.0.0"})
    page = open_cves("?product=langflow&verdict=not_affected")
    first = rows(page)[0]
    page.get_by_role("combobox", name="Product").focus()
    seen = []
    for _ in range(60):
        page.keyboard.press("Tab")
        seen.append(focused(page))
        if seen[-1].startswith(f"Mark {first} not affected?"):
            break
    assert any(s.startswith("Verdict") for s in seen), seen  # a label's text includes its options
    assert seen[-1].startswith(f"Mark {first} not affected?"), seen
    assert visible_focus(page)
    page.keyboard.press("Enter")  # opens the dialog on the pre-selected justification (A16b)
    expect(page.get_by_role("dialog")).to_be_visible()
    for _ in range(3):  # the radio group, the note, Cancel, then the submit button
        page.keyboard.press("Tab")
    assert focused(page) == "Mark not affected"
    page.keyboard.press("Enter")
    expect(page.get_by_role("link", name=first, exact=True)).to_have_count(0)


def test_a15_11_keyboard_reaches_each_products_fields(open_dash):
    page = open_dash()
    editor(page).get_by_label("LangChain", exact=True).focus()
    seen = []
    for _ in range(80):
        page.keyboard.press("Tab")
        # Stop where focus leaves the editor: Save watchlist is disabled (skipped) while nothing changed, and a
        # loop that wrapped round the page would count the fields twice now the charts are one stop each.
        if not editor(page).evaluate("el => el.contains(document.activeElement)"):
            break
        seen.append(focused(page))
        if seen[-1] == "Save watchlist":
            break
    def count(name):  # a select's label text includes its options
        return sum(s.startswith(name) for s in seen)

    n = len(DEFAULT_WATCHLIST)
    assert (count("Usage"), count("Version"), count("Internet-facing")) == (n, n, n), seen
    editor(page).get_by_role("group", name="Langflow").get_by_label("Version").focus()
    assert visible_focus(page)

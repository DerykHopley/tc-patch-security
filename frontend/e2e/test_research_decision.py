"""Browser check for web research that ends in a proposed decision (B22, #62). Check ids: B22.9.

run.sh turns web research on against the fake Tavily (backend/tests/fake_tavily.py). FakeLLM runs the workflow
script Q-research: lookup_cve, check_affected, research_web, propose_decision. The card is B21's (DESIGN.md §6.6)
with the sources it rests on; backend/tests/test_research_decision.py tests the rules. Every test starts from and
leaves the default state, since all tests share one backend.
"""
import pytest
from playwright.sync_api import Locator, expect

from test_chat import ask, open_chat, window
from test_dashboard import api
from test_shell import DESKTOP, PHONE, contrast, no_sideways_scroll, open_app  # noqa: F401 (fixture)

CVE = "CVE-2025-3248"
ASK = f"Is {CVE} a problem for my Langflow behind a VPN? Research it and propose a decision."


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


def langflow_row(api_url: str) -> dict:
    rows = api(api_url, "/cves?status=all&product=langflow&limit=200")["rows"]
    return next(r for r in rows if r["id"] == CVE)


def card_for(page) -> Locator:
    open_chat(page)
    return ask(page, ASK).locator(".proposal-card")


def test_b22_9_the_workflow_ends_in_a_card_with_its_sources_and_approve_records_them(open_app, api_url):
    page = open_app()
    card = card_for(page)
    expect(card.get_by_text(f"Accept the risk of {CVE}", exact=True)).to_be_visible()
    expect(card.locator(".before-after")).to_contain_text("Before: Open")
    expect(card.locator(".before-after .after")).to_contain_text("review 2026-11-12")
    items = card.locator(".proposal-sources li")
    expect(items).to_have_count(2)
    expect(items.nth(0).locator(".chip")).to_have_text("Knowledge base")
    expect(items.nth(1).locator(".chip")).to_have_text("Web result, unverified")
    expect(items.nth(1).get_by_role("link")).to_have_attribute(
        "href", "https://github.com/advisories/GHSA-rvqx-wpfh-mfx7")
    expect(card).not_to_contain_text("blog.example.net")  # the flagged page isn't evidence
    assert langflow_row(api_url)["status"] == "open"  # nothing changed yet

    card.get_by_role("button", name="Approve", exact=True).click()
    expect(card.locator("output.proposal-line")).to_contain_text(f"Done: Marked {CVE} as accepted.")
    row = langflow_row(api_url)
    assert row["status"] == "accepted" and [s["n"] for s in row["history"][-1]["sources"]] == [1, 3]

    # The decision's history on the CVEs page names its sources, the web one still unverified
    card.locator("output.proposal-line").get_by_role("link").click()
    history = page.locator("tr", has_text=CVE).locator("details.history")
    history.locator("summary").click()
    expect(history).to_contain_text("(web result, unverified)")


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b22_9_the_sources_in_light_and_dark_on_desktop_and_phone(open_app, scheme, width):
    page = open_app(width=width, scheme=scheme)
    card = card_for(page)
    for chip in card.locator(".proposal-sources .chip").all():
        fg, bg = chip.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
        assert contrast(fg, bg) >= 4.5, (scheme, fg, bg)
    assert no_sideways_scroll(page)
    box, win = card.bounding_box(), window(page).bounding_box()
    assert box and win and box["x"] + box["width"] <= win["x"] + win["width"] + 1


def test_b22_9_the_source_links_and_buttons_by_keyboard(open_app):
    page = open_app()
    card = card_for(page)
    link = card.locator(".proposal-sources a").first
    approve = card.get_by_role("button", name="Approve", exact=True)
    link.focus()
    expect(link).to_be_focused()
    for _ in range(4):
        page.keyboard.press("Tab")
        if approve.evaluate("el => el === document.activeElement"):
            break
    expect(approve).to_be_focused()  # the sources come before the buttons, in reading order

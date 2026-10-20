"""Browser check (seam 3) for the buttons on tool cards. Check ids: B24.n, from #63.

A refine button narrows the answer at once, as a new message with chips saying what was applied; a change button
makes a proposal card, and nothing changes until Approve. The API side of each action is in
backend/tests/test_card_actions.py; the looks are from DESIGN.md §6.7. Every test starts from and leaves the default
state, since all tests share one backend.
"""
import json
import re

import pytest
from playwright.sync_api import Locator, Page, expect

from test_chat import Q2, ask, open_chat, window
from test_dashboard import api, cve_row
from test_fix_first import FIX_FIRST
from test_shell import DESKTOP, PHONE, SHOTS, contrast, no_sideways_scroll, open_app  # noqa: F401 (fixture)
from reduced_motion import scene, still

CVE = "CVE-2024-8309"  # LangChain: watched and open in the default state
VLLM_CVE = "CVE-2026-109311"  # vLLM: not on the default watchlist


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


def tool_cards(answer: Locator) -> Locator:
    answer.get_by_role("button", name=re.compile("^Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    return answer.locator(".tool-card")


def status(api_url: str, cve: str = CVE, product: str = "langchain") -> str:
    return cve_row(api_url, cve, product)["status"]


def action_bodies(page: Page) -> list[dict]:
    seen: list[dict] = []
    page.on("request", lambda r: seen.append(json.loads(r.post_data or "{}"))
            if r.url.endswith("/chat/action") else None)
    return seen


# --- B24.7: a refine button narrows the answer, and says what it applied ------------------------------------------

def test_b24_7_show_only_cves_then_only_critical_narrow_the_search(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, Q2)
    search = tool_cards(answer).filter(has=page.locator(".search-card")).locator(".search-card")
    first = search.locator(".search-list li")
    expect(first.first).to_be_visible()
    assert any("CVE" not in t for t in first.locator(".meta").all_inner_texts())  # a mix to narrow
    bodies = action_bodies(page)

    search.get_by_role("button", name="Show only CVEs").click()
    refined = window(page).locator(".message.assistant").last
    expect(refined.locator(".refined-head .chip.applied")).to_have_text(["Only CVEs"])
    expect(refined.locator(".refined-head")).to_be_focused()
    assert bodies[-1] == {"action": "refine", "tool": "search_security", "query": bodies[-1]["query"],
                          "filters": ["only_cves"], "page": {"page": "dashboard"}}
    rows = refined.locator(".search-card .search-list li")
    expect(rows.first).to_be_visible()
    assert set(rows.locator(".meta").all_inner_texts()) == {"CVE"}
    expect(refined).to_contain_text("Patch didn't write a new answer")
    expect(refined.get_by_role("button", name="Show only CVEs")).to_have_count(0)  # applied already

    refined.get_by_role("button", name="Only critical").click()
    narrower = window(page).locator(".message.assistant").last
    expect(narrower.locator(".refined-head .chip.applied")).to_have_text(["Only CVEs", "Only critical"])
    for li in narrower.locator(".search-card .search-list li").all():
        expect(li).to_contain_text("Critical")
    expect(narrower.locator(".search-card .card-actions")).to_have_count(0)  # nothing left to narrow
    expect(answer.locator(".answer-text")).to_be_visible()  # the answer above stays as it was


# --- B24.8: a change button makes a proposal; nothing changes until Approve ---------------------------------------

def test_b24_8_mark_not_affected_proposes_and_approve_records_it(open_app, api_url):
    page = open_app()
    open_chat(page)
    card = tool_cards(ask(page, Q2)).filter(has=page.locator(".cve-card"))
    card.get_by_role("button", name=f"Mark not affected… {CVE}").click()
    form = card.get_by_role("form", name="Mark not affected")
    expect(form.get_by_role("radio").first).to_be_focused()
    form.get_by_role("radio", name="Vulnerable code not in execute path").check()
    form.get_by_role("button", name="Propose").click()
    proposal = card.locator(".proposal-card")
    expect(proposal.locator(".result-title")).to_have_text(f"Mark {CVE} not affected")
    expect(proposal.get_by_role("button", name="Approve", exact=True)).to_be_focused()
    assert status(api_url) == "open"  # nothing changed yet
    page.keyboard.press("Enter")
    expect(proposal.locator("output.proposal-line")).to_contain_text("Done:")
    assert status(api_url) == "not_affected"


def test_b24_8_watch_this_product_proposes_at_once(open_app, api_url):
    page = open_app()
    open_chat(page)
    card = tool_cards(ask(page, f"Tell me about {VLLM_CVE}")).filter(has=page.locator(".cve-card"))
    expect(card.get_by_role("button", name=re.compile("^Mark not affected"))).to_have_count(0)  # not watched yet
    card.get_by_role("button", name=re.compile("^Watch this product")).click()
    proposal = card.locator(".proposal-card")
    expect(proposal.locator(".before-after")).to_have_text("Before: Not watched→After: Watched")
    assert "vllm" not in api(api_url, "/watchlist")["watchlist"]
    proposal.get_by_role("button", name="Cancel", exact=True).click()
    expect(proposal.locator("output.proposal-line")).to_have_text("Cancelled: nothing was changed.")
    assert "vllm" not in api(api_url, "/watchlist")["watchlist"]


def test_b24_8_mark_accepted_on_a_fix_first_row_and_set_my_version(open_app, api_url):
    page = open_app()
    open_chat(page)
    card = tool_cards(ask(page, FIX_FIRST)).filter(has=page.locator(".fix-first-card"))
    row = card.locator(".fix-list > li").first
    cve = row.locator("strong").first.inner_text()
    product = api(api_url, "/cves?limit=200")["rows"]
    pid = next(r["product"] for r in product if r["id"] == cve)
    row.get_by_role("button", name=f"Mark accepted… {cve}").click()
    form = row.get_by_role("form", name="Mark accepted")
    expect(form.get_by_role("textbox", name="Reason (required)")).to_be_focused()
    form.get_by_role("button", name="Back").click()  # Back returns focus to the button
    expect(row.get_by_role("button", name=f"Mark accepted… {cve}")).to_be_focused()
    page.keyboard.press("Enter")
    form.get_by_role("textbox", name="Reason (required)").fill("Behind the VPN")
    form.get_by_role("button", name="Propose").click()
    proposal = row.locator(".proposal-card")
    expect(proposal.locator(".result-title")).to_have_text(f"Accept the risk of {cve}")
    assert status(api_url, cve, pid) == "open"
    proposal.get_by_role("button", name="Approve", exact=True).click()
    expect(proposal.locator("output.proposal-line")).to_contain_text("Done:")
    assert status(api_url, cve, pid) == "accepted"

    lookup = tool_cards(ask(page, f"Tell me about {CVE}")).filter(has=page.locator(".cve-card"))
    lookup.get_by_role("button", name="Set my version… LangChain").click()
    form = lookup.get_by_role("form", name="Set my version")
    form.get_by_role("textbox", name="Your version of LangChain").fill("0.2.9")
    form.get_by_role("button", name="Propose").click()
    expect(lookup.locator(".proposal-card .before-after .after")).to_contain_text("version 0.2.9")
    langchain = next(p for p in api(api_url, "/watchlist")["products"] if p["product"] == "langchain")
    assert langchain["version"] in (None, "")  # nothing changed yet


# --- B24.9: Open in CVEs page and Ask about this --------------------------------------------------------------------

def test_b24_9_open_in_cves_page_and_ask_about_this(open_app):
    page = open_app()
    open_chat(page)
    card = tool_cards(ask(page, FIX_FIRST)).filter(has=page.locator(".fix-first-card"))
    cve = card.locator(".fix-list > li strong").first.inner_text()
    bodies: list[dict] = []
    page.on("request", lambda r: bodies.append(json.loads(r.post_data or "{}")) if r.url.endswith("/chat") else None)
    card.get_by_role("button", name=f"Ask about this: {cve}").first.click()
    expect(window(page).locator(".message.user").last).to_have_text(f"Explain {cve} and how to defend against it.")
    expect(window(page).locator(".message.assistant")).to_have_count(2, timeout=10_000)
    assert bodies[-1]["page"] == {"page": "dashboard", "cve": cve}

    card.get_by_role("link", name="Open in CVEs page").click()
    expect(page).to_have_url(re.compile(r"/cves$"))
    expect(window(page)).to_be_visible()  # in the app: the chat stays open


# --- B24.10: light and dark, phone and desktop, keyboard ------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b24_10_the_buttons_read_well_in_light_and_dark_and_on_a_phone(open_app, browser_name, width, scheme):
    page = open_app(width=width, scheme=scheme, reduced=True)
    open_chat(page)
    cards = tool_cards(ask(page, Q2))
    button = cards.get_by_role("button", name="Show only CVEs")
    colour = lambda el, p="color": el.evaluate(f"el => getComputedStyle(el).{p}")  # noqa: E731
    assert contrast(colour(button), colour(button, "backgroundColor")) >= 4.5
    button.focus()
    page.keyboard.press("Enter")  # by keyboard
    chip = window(page).locator(".refined-head .chip.applied")
    expect(chip).to_have_text("Only CVEs")
    assert contrast(colour(chip), colour(chip, "backgroundColor")) >= 4.5
    cards.get_by_role("button", name=f"Mark not affected… {CVE}").click()
    assert no_sideways_scroll(page)
    win = window(page).bounding_box()
    for el in (cards.locator(".card-actions").first, chip):
        box = el.bounding_box()
        assert box["x"] >= win["x"] and box["x"] + box["width"] <= win["x"] + win["width"] + 0.5
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b24-{browser_name}-{width}-{scheme}-card-actions.png")


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def b24_11_card_actions(fx):
    page = fx("open_app")(reduced=True)
    open_chat(page)
    cards = tool_cards(ask(page, "Explain CVE-2024-8309 and how to prevent that kind of bug"))
    cards.get_by_role("button", name=f"Mark not affected… {CVE}").click()
    still(page, "a change button's form")
    cards.get_by_role("button", name="Show only CVEs").click()
    expect(window(page).locator(".refined-head .chip.applied")).to_have_text("Only CVEs")
    still(page, "a refined result")

"""Browser check for web research that ends in a proposed decision (B22, #62). Check ids: B22.9, B62.8, B66.4, F133.6.

run.sh turns web research on against the fake Tavily (backend/tests/fake_tavily.py). With Langflow's version recorded
(1.3.0: not affected), FakeLLM runs its workflow script research-fixed-version: lookup_cve, check_affected,
research_web, propose_decision (not affected). The CVE is in KEV, so with no version Q-research stops before proposing
and asks for it (B62.8); with 1.2.0 (affected) Q-research-affected recommends the fix instead (#133).
The card is B21's (DESIGN.md §6.6) with the sources it rests on; backend/tests/test_research_decision.py tests the
rules. Every test leaves the default state, since all tests share one backend.
"""
import pytest
from playwright.sync_api import Locator, expect

from test_affected import set_stack
from test_chat import ask, open_chat, window
from test_dashboard import api, cve_row
from test_shell import DESKTOP, PHONE, contrast, no_sideways_scroll, open_app  # noqa: F401 (fixture)
from reduced_motion import scene, still

CVE = "CVE-2025-3248"
ASK = f"Is {CVE} a problem for my Langflow behind a VPN? Research it and propose a decision."  # Q-research
ASK_KNOWN = f"I run Langflow 1.3.0 behind a VPN. Is {CVE} a problem? Research it and propose a decision."
ASK_AFFECTED = f"I run Langflow 1.2.0 behind a VPN. Is {CVE} a problem? Research it and propose a decision."


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    """The default state with Langflow 1.3.0 recorded: not affected, so the workflow ends in a proposal. With the
    version unknown (B62) or affected (#133), Patch proposes nothing for this KEV CVE."""
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})
    set_stack(api_url, langflow={"version": "1.3.0"})
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


def langflow_row(api_url: str) -> dict:
    return cve_row(api_url, CVE, "langflow")


def card_for(page) -> Locator:
    open_chat(page)
    return ask(page, ASK_KNOWN).locator(".proposal-card")


def test_b22_9_the_workflow_ends_in_a_card_with_its_sources_and_approve_records_them(open_app, api_url):
    page = open_app()
    card = card_for(page)
    expect(card.get_by_text(f"Mark {CVE} not affected", exact=True)).to_be_visible()
    expect(card.locator(".before-after")).to_contain_text("Before: Open")
    expect(card.locator(".before-after .after")).to_contain_text("Not affected")
    items = card.locator(".proposal-sources li")
    expect(items).to_have_count(2)
    expect(items.nth(0).locator(".chip")).to_have_text("Knowledge base")
    expect(items.nth(1).locator(".chip")).to_have_text("Web result, unverified")
    expect(items.nth(1).get_by_role("link")).to_have_attribute(
        "href", "https://github.com/advisories/GHSA-rvqx-wpfh-mfx7")
    expect(card).not_to_contain_text("blog.example.net")  # the flagged page isn't evidence
    assert langflow_row(api_url)["status"] == "open"  # nothing changed yet

    card.get_by_role("button", name="Approve", exact=True).click()
    expect(card.locator("output.proposal-line")).to_contain_text(f"Done: Marked {CVE} as not affected.")
    row = langflow_row(api_url)
    assert row["status"] == "not_affected" and [s["n"] for s in row["history"][-1]["sources"]] == [2, 3]

    # The decision's history on the CVEs page names its sources, the web one still unverified
    card.locator("output.proposal-line").get_by_role("link").click()
    history = page.locator("tr", has_text=CVE).locator("details.history")
    # By keyboard: the chat stays open and, with this view's one row (B33 links to the new status), covers it
    history.locator("summary").focus()
    page.keyboard.press("Enter")
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


def test_b62_8_with_no_version_patch_asks_for_it_instead_of_proposing(open_app, api_url):
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})  # no Langflow version: the verdict is unknown
    page = open_app()
    open_chat(page)
    answer = ask(page, ASK)
    expect(answer).to_contain_text("Which Langflow version do you run?")
    expect(answer.locator(".proposal-card")).to_have_count(0)
    assert langflow_row(api_url)["status"] == "open"


def test_f133_6_with_the_version_affected_patch_recommends_the_fix_instead_of_proposing(open_app, api_url):
    set_stack(api_url, langflow={"version": "1.2.0"})  # affected; fresh_state resets it after
    page = open_app()
    open_chat(page)
    answer = ask(page, ASK_AFFECTED)
    expect(answer).to_contain_text("upgrade Langflow to 1.3.0")
    expect(answer.locator(".proposal-card")).to_have_count(0)
    assert langflow_row(api_url)["status"] == "open"


def test_b66_4_a_version_typed_in_the_chat_is_proposed_saved_then_the_decision_follows(open_app, api_url):
    """#113: the user answers Patch's question in the chat. Patch proposes saving it; only after Approve does the
    next turn check it again. 1.2.0 is affected, so it recommends the fix and proposes nothing (#133). The chat sends
    the earlier turns as history, as for any follow-up."""
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})  # no Langflow version: the verdict is unknown
    page = open_app()
    open_chat(page)
    expect(ask(page, ASK)).to_contain_text("Tell me and I'll propose saving it")

    save = ask(page, "1.2.0").locator(".proposal-card")
    expect(save.get_by_text("Change how you run Langflow", exact=True)).to_be_visible()
    expect(save.locator(".before-after .after")).to_contain_text("1.2.0")
    save.get_by_role("button", name="Approve", exact=True).click()
    expect(save.locator("output.proposal-line")).to_contain_text("Done:")

    answer = ask(page, "Approved. Carry on.")
    expect(answer).to_contain_text("affected by the version check")
    expect(answer).to_contain_text("keep it open and upgrade Langflow")
    expect(answer.locator(".proposal-card")).to_have_count(0)
    assert langflow_row(api_url)["status"] == "open"


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def b22_9_proposed_decision(fx):
    set_stack(fx("api_url"), langflow={"version": "1.3.0"})  # not affected; reduced_motion_defaults resets it
    page = fx("open_app")(reduced=True)
    open_chat(page)
    card = ask(page, ASK_KNOWN).locator(".proposal-card")
    expect(card.locator(".proposal-sources li")).to_have_count(2)
    still(page, "the proposed decision with its sources")
    card.get_by_role("button", name="Cancel", exact=True).click()  # leaves the shared state as it was
    expect(card.locator("output.proposal-line")).to_contain_text("Cancelled")

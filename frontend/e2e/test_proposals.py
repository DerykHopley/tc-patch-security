"""Browser check (seam 3) for the card of a change Patch proposes. Check ids: B21.9, from #58.

FakeLLM proposes Q10 ("Mark CVE-2024-8309 as fixed") and Q9 ("Add vLLM to my watchlist"). The expected words come
from the backend (backend/tests/test_proposals.py tests the lifecycle itself) and the looks from DESIGN.md §6.6.
Every test starts from and leaves the default state (`fresh_state`), since all tests share one backend.
"""
import re

import pytest
from playwright.sync_api import Locator, Page, expect

from test_chat import ask, open_chat, window
from test_dashboard import api
from test_shell import DESKTOP, PHONE, SHOTS, contrast, no_sideways_scroll, open_app  # noqa: F401 (fixture)

CVE = "CVE-2024-8309"
Q10 = f"Mark {CVE} as fixed"
Q9 = "Add vLLM to my watchlist"


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


def proposal(answer: Locator) -> Locator:
    return answer.locator(".proposal-card")


def status(api_url: str) -> str:
    rows = api(api_url, "/cves?status=all&product=langchain&limit=200")["rows"]
    return next(r for r in rows if r["id"] == CVE)["status"]


def history(api_url: str) -> list[dict]:
    rows = api(api_url, "/cves?status=all&product=langchain&limit=200")["rows"]
    return next(r for r in rows if r["id"] == CVE)["history"]


def test_b21_9_the_card_previews_the_change_and_nothing_changes_until_approve(open_app, api_url):
    page = open_app()
    open_chat(page)
    card = proposal(ask(page, Q10))
    expect(card.get_by_text(f"Mark {CVE} fixed", exact=True)).to_be_visible()
    expect(card.locator(".before-after")).to_have_text("Before: Open→After: Fixed")
    expect(card).to_contain_text("Nothing has changed yet.")
    for name in ("Approve", "Edit", "Cancel"):
        expect(card.get_by_role("button", name=name, exact=True)).to_be_enabled()
    assert status(api_url) == "open"

    card.get_by_role("button", name="Approve", exact=True).dblclick()  # a double click approves once
    line = card.locator("output.proposal-line")
    expect(line).to_contain_text(f"Done: Marked {CVE} as fixed.")
    expect(card.get_by_role("button", name="Approve", exact=True)).to_have_count(0)
    assert status(api_url) == "fixed" and len(history(api_url)) == 1

    link = line.get_by_role("link", name=f"See {CVE} on the CVEs page")
    link.click()
    expect(page).to_have_url(re.compile(r"/cves\?product=langchain&status=all$"))
    expect(page.get_by_role("row", name=re.compile(CVE))).to_be_visible()
    expect(window(page)).to_be_visible()  # the chat stays open: no page load


def test_b21_9_edit_uses_the_decision_fields_and_approve_records_them(open_app, api_url):
    page = open_app()
    open_chat(page)
    card = proposal(ask(page, Q10))
    card.get_by_role("button", name="Edit", exact=True).click()
    form = card.get_by_role("form", name=f"Edit: Mark {CVE} fixed")
    expect(form.get_by_role("combobox", name="Status")).to_be_focused()
    form.get_by_role("combobox", name="Status").select_option("not_affected")
    form.get_by_role("radio", name="Vulnerable code not in execute path").check()
    form.get_by_role("textbox", name="Note (optional)").fill("We never call the SQL agent.")
    form.get_by_role("button", name="Save changes").click()
    expect(card.locator(".result-title")).to_have_text(f"Mark {CVE} not affected")
    expect(card.locator(".before-after .after")).to_have_text("After: Not affected (vulnerable code not in execute path)")
    expect(card.get_by_role("button", name="Approve", exact=True)).to_be_focused()
    assert status(api_url) == "open"
    page.keyboard.press("Enter")  # Approve, by keyboard
    expect(card.locator("output.proposal-line")).to_contain_text("Done:")
    d = history(api_url)[-1]
    assert (d["status"], d["justification"], d["note"], d["via"]) == (
        "not_affected", "vulnerable_code_not_in_execute_path", "We never call the SQL agent.", "chat")


def test_b21_9_cancel_changes_nothing(open_app, api_url):
    page = open_app()
    open_chat(page)
    card = proposal(ask(page, Q9))
    expect(card.locator(".before-after")).to_have_text("Before: Not watched→After: Watched")
    expect(card.get_by_role("button", name="Edit", exact=True)).to_have_count(0)  # nothing to correct
    card.get_by_role("button", name="Cancel", exact=True).click()
    expect(card.locator("output.proposal-line")).to_have_text("Cancelled: nothing was changed.")
    expect(card.locator(".proposal-state")).to_have_text("Cancelled")
    assert "vllm" not in api(api_url, "/watchlist")["watchlist"]


def test_b21_9_an_approve_the_backend_refuses_shows_why(open_app, api_url):
    page = open_app()
    open_chat(page)
    card = proposal(ask(page, Q10))
    api(api_url, f"/cves/{CVE}", "PATCH", {"status": "fixed", "note": "done on the CVEs page"})
    card.get_by_role("button", name="Approve", exact=True).click()
    expect(card.get_by_role("alert")).to_have_text(
        "This CVE's status changed since Patch proposed this. Propose it again.")
    assert len(history(api_url)) == 1


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b21_9_the_card_reads_well_in_light_and_dark_and_on_a_phone(open_app, browser_name, width, scheme):
    page = open_app(width=width, scheme=scheme, reduced=True)
    open_chat(page)
    card = proposal(ask(page, Q10))
    expect(card).to_be_visible()
    chip = card.locator(".proposal-state")
    colour = lambda el, p="color": el.evaluate(f"el => getComputedStyle(el).{p}")  # noqa: E731
    assert contrast(colour(chip), colour(chip, "backgroundColor")) >= 4.5
    box, win = card.bounding_box(), window(page).bounding_box()
    assert box["x"] >= win["x"] and box["x"] + box["width"] <= win["x"] + win["width"] + 0.5
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b21-{browser_name}-{width}-{scheme}-proposal.png")
    card.get_by_role("button", name="Approve", exact=True).click()
    line = card.locator("output.proposal-line")
    expect(line).to_contain_text("Done:")
    assert contrast(colour(line), colour(line, "backgroundColor")) >= 4.5

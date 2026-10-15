"""Browser check (seam 3) for accepted status, decision records and "no fix yet". Check ids: A16b.n, from #27.

The rules (open, accepted, review due; no fix; overdue) and the validation are tested in the backend
(test_status.py, test_decisions_api.py). These check the CVEs page shows them: the decision dialog (named fields,
focus trapped, Esc closes), the justification picker, the history, the "No fix yet" mark, the Top 5 and Patch's card,
in light and dark, at 400px and 1400px, pinned, with reduced motion and by keyboard. Expected looks: DESIGN.md §5.9.
"""
import datetime as dt
import re

import pytest
from playwright.sync_api import Page, Route, expect

from test_cves_page import actions_in_view, focused, no_sideways_scroll, open_cves, pin, visible_focus, window  # noqa: F401
from test_dashboard import (  # noqa: F401 (fixtures)
    DESKTOP, PHONE, SHOTS, api, clean_state, confirm, open_dash, rows,
)

NO_FIX = "CVE-2026-0770"  # Langflow, critical, in KEV, no fixed version in OSV; published 2026-01-23
FIXABLE = "CVE-2025-3248"  # Langflow, critical, in KEV, fixed in 1.3.0; overdue


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    """A full reset before and after: the only way to clear the append-only history, so counts start from none."""
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


def row(page: Page, cve: str):
    return page.locator("table.cves tbody tr", has=page.get_by_role("link", name=cve, exact=True))


def cell(page: Page, cve: str, label: str):
    return row(page, cve).locator(f"td[data-label='{label}']")


def api_row(api_url: str, cve: str) -> dict:
    return next(r for r in api(api_url, "/cves?status=all&product=langflow&limit=200")["rows"] if r["id"] == cve)


def as_of(api_url: str) -> str:
    return api(api_url, "/dashboard")["as_of"]


def plus_days(iso: str, days: int) -> str:
    return (dt.date.fromisoformat(iso) + dt.timedelta(days=days)).isoformat()


def accept(page: Page, cve: str, reason="Behind our VPN; vendor has no fix", control="WAF rule") -> None:
    page.get_by_role("button", name=f"Accept the risk of {cve}", exact=True).click()
    d = page.get_by_role("dialog", name=f"Accept the risk of {cve}")
    d.get_by_role("textbox", name="Reason (required)").fill(reason)
    d.get_by_role("textbox", name="Compensating control (optional)").fill(control)
    d.get_by_role("button", name="Accept the risk").click()
    expect(d).to_have_count(0)


# --- A16b.9: the accept dialog: named fields, defaults, required ones, Esc, focus trapped -------------------------

def test_a16b_9_accepting_moves_it_out_of_open_with_reason_review_date_and_history(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1")
    page.get_by_role("button", name=f"Accept the risk of {NO_FIX}", exact=True).click()
    d = page.get_by_role("dialog", name=f"Accept the risk of {NO_FIX}")
    expect(d).to_be_visible()
    expect(d.get_by_label("Review date (required)")).to_have_value(plus_days(as_of(api_url), 90))
    expect(d.get_by_role("textbox", name="Reason (required)")).to_be_focused()
    d.get_by_role("button", name="Accept the risk").click()  # no reason yet: the browser refuses, the dialog stays
    expect(d).to_be_visible()
    assert api(api_url, "/cves?status=accepted")["total"] == 0
    d.get_by_role("button", name="Cancel").click()
    expect(d).to_have_count(0)

    accept(page, NO_FIX)
    expect(page.get_by_role("link", name=NO_FIX, exact=True)).to_have_count(0)
    page.get_by_role("combobox", name="Status").select_option(label="Accepted")
    assert "status=accepted" in page.url
    status = cell(page, NO_FIX, "Status")
    expect(status.locator(".status")).to_have_text("Accepted")
    expect(status).to_contain_text(f"Review on {plus_days(as_of(api_url), 90)}")
    expect(status).to_contain_text("Behind our VPN; vendor has no fix")
    expect(status).to_contain_text("Control: WAF rule")
    history = status.get_by_text("History (1)")
    history.click()
    expect(status.locator(".history li")).to_have_count(1)
    expect(status.locator(".history li")).to_contain_text("Accepted")
    expect(status.locator(".history li")).to_contain_text("by owner, on the CVEs page")
    expect(status.locator(".history li .history-when")).to_have_text(re.compile(r"^\d{4}-\d\d-\d\d \d\d:\d\d UTC$"))
    # Reopen: the history grows, never shrinks
    status.get_by_role("button", name=f"Reopen {NO_FIX}").click()
    page.get_by_role("dialog").get_by_role("textbox", name="Note (optional)").fill("Vendor shipped a fix")
    confirm(page)
    assert [h["status"] for h in api_row(api_url, NO_FIX)["history"]] == ["accepted", "open"]


def test_a16b_9_esc_closes_the_dialog_and_changes_nothing_focus_goes_back(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1")
    opener = page.get_by_role("button", name=f"Accept the risk of {FIXABLE}", exact=True)
    opener.click()
    d = page.get_by_role("dialog")
    d.get_by_role("textbox", name="Reason (required)").fill("typed, then cancelled")
    page.keyboard.press("Escape")
    expect(d).to_have_count(0)
    expect(opener).to_be_focused()
    assert api(api_url, "/cves?status=accepted")["total"] == 0


def test_a16b_9_the_dialog_traps_focus(open_cves):
    page = open_cves("?product=langflow&kev=1")
    page.get_by_role("button", name=f"Accept the risk of {FIXABLE}", exact=True).click()
    expect(page.get_by_role("dialog")).to_be_visible()
    seen = []
    for _ in range(8):
        page.keyboard.press("Tab")
        seen.append(focused(page))
        assert page.evaluate("document.querySelector('dialog').contains(document.activeElement)"), seen
        assert visible_focus(page), seen[-1]
    for name in ("Review date (required)", "Compensating control (optional)", "Cancel", "Accept the risk",
                 "Reason (required)"):
        assert any(s.startswith(name) for s in seen), (name, seen)
    page.get_by_role("textbox", name="Reason (required)").focus()
    page.keyboard.press("Shift+Tab")  # from the first field back to the last button
    assert focused(page) == "Accept the risk"


def test_a16b_9_a_server_error_shows_in_the_dialog(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1")
    page.get_by_role("button", name=f"Accept the risk of {FIXABLE}", exact=True).click()
    d = page.get_by_role("dialog")
    d.get_by_role("textbox", name="Reason (required)").fill("ok")
    d.get_by_label("Review date (required)").evaluate("el => { el.removeAttribute('min') }")
    d.get_by_label("Review date (required)").fill(as_of(api_url))  # the as-of date itself: the backend refuses
    d.get_by_role("button", name="Accept the risk").click()
    expect(d.get_by_role("alert")).to_contain_text("The review date must be after the as-of date")
    expect(d).to_be_visible()


# --- A16b.10: not affected needs a justification; fixed and reopen take a note ------------------------------------

def test_a16b_10_the_justification_picker(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1")
    page.get_by_role("button", name=f"Mark {FIXABLE} not affected", exact=True).click()
    d = page.get_by_role("dialog", name=f"Mark {FIXABLE} not affected")
    group = d.get_by_role("group", name="Why isn't it affected? (required)")
    for name in ("Component not present", "Vulnerable code not present", "Vulnerable code not in execute path",
                 "Vulnerable code cannot be controlled by adversary", "Inline mitigations already exist"):
        expect(group.get_by_role("radio", name=name)).to_be_visible()
    d.get_by_role("button", name="Mark not affected").click()  # none picked: refused, still open
    expect(d).to_be_visible()
    group.get_by_role("radio", name="Vulnerable code not in execute path").check()
    d.get_by_role("textbox", name="Note (optional)").fill("We never call /api/v1/validate")
    d.get_by_role("button", name="Mark not affected").click()
    expect(d).to_have_count(0)
    h = next(r for r in api(api_url, "/cves?status=not_affected")["rows"] if r["id"] == FIXABLE)["decision"]
    assert (h["justification"], h["note"]) == ("vulnerable_code_not_in_execute_path", "We never call /api/v1/validate")
    page.get_by_role("combobox", name="Status").select_option(label="Not affected")
    expect(cell(page, FIXABLE, "Status")).to_contain_text("Vulnerable code not in execute path")


def test_a16b_10_mark_fixed_takes_an_optional_note(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1")
    page.get_by_role("button", name=f"Mark {FIXABLE} fixed").click()
    d = page.get_by_role("dialog", name=f"Mark {FIXABLE} fixed")
    expect(d.get_by_role("textbox", name="Note (optional)")).to_be_focused()
    d.get_by_role("textbox", name="Note (optional)").fill("Upgraded to 1.3.0")
    confirm(page)
    h = api(api_url, "/cves?status=fixed")["rows"][0]["decision"]
    assert (h["status"], h["note"]) == ("fixed", "Upgraded to 1.3.0")


# --- A16b.11: "No fix yet · open N days" instead of overdue; the Top 5 and Patch's card ----------------------------

def test_a16b_11_no_fix_yet_replaces_overdue_and_the_due_date_says_decide_by(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1")
    due = cell(page, NO_FIX, "Due")
    expect(due.locator(".chip.no-fix")).to_have_text("No fix yet · open 263 days")
    expect(due.locator(".due-label")).to_have_text("Decide by")
    expect(due.locator(".overdue")).to_have_count(0)
    expect(due.locator(".due-from")).to_contain_text("accept, mitigate or replace")
    fixable = cell(page, FIXABLE, "Due")
    expect(fixable.locator(".overdue")).to_have_text("Overdue")
    expect(fixable.locator(".chip.no-fix")).to_have_count(0)


def test_a16b_11_top_5_shows_no_fix_yet(open_dash, api_url):
    api(api_url, "/watchlist", "PUT", {"products": ["langflow"]})  # its two KEV CVEs lead: one fixable, one not
    page = open_dash()
    top = api(api_url, "/cves?status=open&limit=5")["rows"]
    assert NO_FIX in [r["id"] for r in top]
    card = page.get_by_role("region", name="Top 5 open CVEs")
    for i, r in enumerate(top):
        li = card.locator("li").nth(i)
        if r["no_fix"]:
            expect(li.locator(".chip.no-fix")).to_have_text(f"No fix yet · open {r['open_days']} days")
            expect(li).to_contain_text("Decide by")
            expect(li.locator(".overdue")).to_have_count(0)
        else:
            expect(li.locator(".chip.no-fix")).to_have_count(0)
    expect(page.locator(".tile-kev .tile-note")).to_contain_text("Overdue since")  # the fixable one comes first


def test_a16b_11_patchs_card_shows_the_acceptance_and_never_changes_it(open_cves, api_url):
    from test_chat import ask

    page = open_cves("?product=langflow&kev=1")
    accept(page, NO_FIX)
    page.keyboard.press("Control+k")
    expect(window(page)).to_be_visible()
    answer = ask(page, f"Accept the risk of {NO_FIX} and tell me about it")
    expect(answer).to_contain_text("accepted")
    answer.get_by_role("button", name=re.compile("Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    card = answer.locator(".tool-card .cve-card")
    expect(card).to_contain_text("Accepted: Behind our VPN; vendor has no fix")
    assert [r["id"] for r in api(api_url, "/cves?status=accepted")["rows"]] == [NO_FIX]
    assert len(api(api_url, "/cves?status=accepted")["rows"][0]["history"]) == 1  # Patch added nothing


# --- A16b.12: review due (drawn from a mocked reply: the API refuses a review date that's already due) -------------

def test_a16b_12_review_due_shows_in_open_with_its_acceptance(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1")
    when = as_of(api_url)

    def due(route: Route):
        body = route.fetch().json()
        for r in body["rows"]:
            if r["id"] == FIXABLE:
                d = {"status": "accepted", "justification": None, "reason": "Vendor has no fix", "note": None,
                     "review_date": when, "compensating_control": None, "decided_at": "2026-07-15T09:00:00+00:00",
                     "decided_by": "owner", "via": "page"}
                r |= {"status": "accepted", "review_due": True, "review_date": when, "decision": d, "history": [d]}
        route.fulfill(json=body)

    page.route(f"{api_url}/cves?*", due)  # the API, not the page (also /cves?…)
    page.reload()
    status = cell(page, FIXABLE, "Status")
    expect(status.locator(".chip.review-due")).to_have_text("Review due")
    expect(status).to_contain_text(f"Review was due {when}")
    expect(status).to_contain_text("Vendor has no fix")
    for name in (f"Accept the risk of {FIXABLE} again", f"Mark {FIXABLE} fixed", f"Mark {FIXABLE} not affected",
                 f"Reopen {FIXABLE}"):
        expect(status.get_by_role("button", name=name, exact=True)).to_be_visible()
    status.get_by_role("button", name=f"Accept the risk of {FIXABLE} again", exact=True).click()
    expect(page.get_by_role("dialog", name=f"Accept the risk of {FIXABLE} again")).to_be_visible()
    page.keyboard.press("Escape")


# --- A16b.13: phones, pinned, reduced motion, light and dark ---------------------------------------------------------

def test_a16b_13_phone_and_pinned_show_the_decision_and_history_without_sideways_scroll(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1", width=PHONE)
    accept(page, NO_FIX)
    page.get_by_role("combobox", name="Status").select_option(label="Accepted")
    status = cell(page, NO_FIX, "Status")
    status.get_by_text("History (1)").click()
    expect(status.locator(".history li")).to_be_visible()
    assert no_sideways_scroll(page)
    b = status.locator(".history").bounding_box()
    assert b and b["x"] >= 0 and b["x"] + b["width"] <= PHONE
    page.get_by_role("button", name=f"Reopen {NO_FIX}").click()
    d = page.get_by_role("dialog").bounding_box()
    assert d and d["x"] >= 0 and d["x"] + d["width"] <= PHONE
    page.keyboard.press("Escape")
    wide = open_cves("?product=langflow&kev=1")
    pin(wide)
    actions_in_view(wide)
    for name in (f"Accept the risk of {FIXABLE}", f"Mark {FIXABLE} not affected"):
        bb = wide.get_by_role("button", name=name, exact=True).bounding_box()
        box = wide.locator(".table-scroll").bounding_box()
        assert bb and box and bb["x"] + bb["width"] <= box["x"] + box["width"] + 0.5
    assert no_sideways_scroll(wide)


# Reduced motion: in the shared check, test_reduced_motion.py (scene a16b_13).


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a16b_13_light_dark_phone_and_desktop(open_cves, api_url, browser_name, width, scheme):
    page = open_cves("?product=langflow&kev=1", width=width, scheme=scheme, reduced=True)
    accept(page, NO_FIX)
    page.get_by_role("combobox", name="Status").select_option(label="All")
    cell(page, NO_FIX, "Status").get_by_text("History (1)").click()
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a16b-{browser_name}-{width}-{scheme}-cves.png")
    assert no_sideways_scroll(page)
    page.get_by_role("button", name=f"Mark {FIXABLE} not affected", exact=True).click()
    d = page.get_by_role("dialog")
    bg = d.evaluate("el => getComputedStyle(el).backgroundColor")
    assert bg == ("rgb(255, 255, 255)" if scheme == "light" else "rgb(26, 26, 46)")
    color = d.evaluate("el => getComputedStyle(el).color")
    assert color == ("rgb(42, 37, 89)" if scheme == "light" else "rgb(236, 235, 255)")
    page.screenshot(path=SHOTS / f"a16b-{browser_name}-{width}-{scheme}-dialog.png")


# --- A16b.14: keyboard: every action and the history are reachable, with names ------------------------------------

def test_a16b_14_keyboard_reaches_accept_and_the_history(open_cves, api_url):
    page = open_cves("?product=langflow&kev=1")
    accept(page, NO_FIX)
    page.get_by_role("combobox", name="Status").select_option(label="All")
    page.get_by_role("combobox", name="Product").focus()
    seen = []
    for _ in range(120):
        page.keyboard.press("Tab")
        seen.append(focused(page))
        if seen[-1].startswith(f"History of {NO_FIX}"):
            break
    assert seen[-1] == f"History of {NO_FIX}: 1 decisions", seen
    assert visible_focus(page)
    page.keyboard.press("Enter")
    expect(cell(page, NO_FIX, "Status").locator(".history li")).to_be_visible()
    assert f"Accept the risk of {FIXABLE}" in seen, seen

"""Browser check (seam 3) for priority by rules, policy and due dates: the Priority and Due columns on the CVEs page,
the dashboard's Top 5 and KEV tile, and the policy on the Settings page. Check ids: A16.n, from ticket #18.

Runs in Firefox and Chromium (run.sh). Expected levels, reasons and dates come from the backend's API (the rules are
table-tested in backend/tests/test_priority.py); expected looks from docs/design/DESIGN.md §5.9, §7 and §10.
Every test puts the state back: `clean_state` (watchlist, fields, statuses) and `default_policy` (the settings).
"""
import re

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from test_affected import set_stack
from test_cves_page import actions_in_view, focused, no_sideways_scroll, open_cves, pin, visible_focus, window  # noqa: F401
from test_dashboard import (  # noqa: F401 (fixtures)
    DESKTOP, PHONE, SHOTS, api, clean_state, confirm, contrast, expect_rows, open_dash, rgb_list, rows, tile,
)
from reduced_motion import scene, still

LANGFLOW_KEV = "CVE-2025-3248"  # Langflow, critical, in KEV since 2025-05-05; KEV deadline 2025-05-26
EPSS_HIGH = "CVE-2026-21445"  # Langflow, high severity, EPSS 98th percentile, fixed in 1.7.1; not in KEV
LITELLM_EPSS = "CVE-2026-35029"  # LiteLLM, high severity, EPSS 90th percentile, fixed in 1.83.0; not in KEV
DEFAULT_POLICY = {"urgent_days": 7, "high_days": 30, "normal_days": 90, "low_days": 180, "adopt_kev_deadline": True}


@pytest.fixture(autouse=True)
def default_policy(api_url: str):
    """The default policy and threshold before and after each test (the other settings are left alone)."""
    def reset():
        s = api(api_url, "/settings")["settings"]
        api(api_url, "/settings", "PUT", {**s, "policy": DEFAULT_POLICY, "priority": {"epss_percentile": 90}})

    reset()
    yield
    reset()


@pytest.fixture
def open_settings(browser: Browser, ui_url: str, clean_state):
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(f"{ui_url}/settings")
        expect(page.get_by_role("heading", name="Priority and due dates", exact=True)).to_be_visible()
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def row(page: Page, cve: str) -> Locator:
    return page.locator("table.cves tbody tr", has=page.get_by_role("link", name=cve, exact=True))


def cell(page: Page, cve: str, label: str) -> Locator:
    return row(page, cve).locator(f"td[data-label='{label}']")


def api_row(api_url: str, cve: str, product: str = "langflow") -> dict:
    return next(r for r in api(api_url, f"/cves?status=all&product={product}&limit=200")["rows"] if r["id"] == cve)


# --- A16.9: the CVEs page: priority with reasons, due date, overdue, KEV deadline; sorted by priority -------------

def test_a16_9_cves_page_shows_priority_reasons_due_date_and_overdue(open_cves, api_url):
    page = open_cves()
    for name in ("Priority", "Due"):
        expect(page.locator("table.cves thead th", has_text=name)).to_have_count(1)
    expected = api(api_url, "/cves?limit=25")
    expect_rows(page, [r["id"] for r in expected["rows"]])  # the API's order: by priority, then due date
    expect(page.locator(".filters .meta")).to_have_text(f"{expected['total']} CVEs · by priority, then due date")
    top = expected["rows"][0]
    assert top["priority"] == "urgent"
    expect(cell(page, top["id"], "Priority").locator(".chip.priority")).to_have_text("Urgent")
    expect(cell(page, top["id"], "Priority")).to_contain_text(" · ".join(top["priority_reasons"]))

    kev = open_cves(f"?product=langflow&kev=1")
    due = cell(kev, LANGFLOW_KEV, "Due")
    expect(due.locator(".due-date")).to_have_text("2025-05-26")
    expect(due.locator(".overdue")).to_have_text("Overdue")
    expect(due.locator(".overdue svg")).to_have_attribute("aria-hidden", "true")
    expect(due.locator(".due-from")).to_have_text("by your policy: KEV deadline")
    expect(due.locator(".kev-deadline")).to_have_text("CISA KEV deadline 2025-05-26")  # CISA's date, its own fact
    levels = [r["priority"] for r in api(api_url, "/cves?limit=200")["rows"]]
    assert levels == sorted(levels, key=["urgent", "high", "normal", "low"].index)


def test_a16_9_internet_facing_raises_a_cve_and_not_affected_lowers_it(open_cves, api_url):
    page = open_cves("?product=litellm&severity=HIGH")  # 17 rows: all on the first page
    chip = cell(page, LITELLM_EPSS, "Priority").locator(".chip.priority")
    expect(chip).to_have_text("Normal")
    set_stack(api_url, litellm={"internet_facing": True})
    page.reload()
    expect(chip).to_have_text("High")
    expect(cell(page, LITELLM_EPSS, "Priority")).to_contain_text("EPSS 90th percentile · internet-facing")
    expect_rows(page, [r["id"] for r in api(api_url, "/cves?product=litellm&severity_min=HIGH&limit=25")["rows"]])
    set_stack(api_url, litellm={"internet_facing": True, "version": "1.83.0"})
    page.reload()
    expect(chip).to_have_text("Normal")
    expect(cell(page, LITELLM_EPSS, "Priority")).to_contain_text("not affected: one level lower")


def test_a16_9_top_5_and_the_kev_tile_follow_the_priority(open_dash, api_url):
    page = open_dash()
    top = api(api_url, "/cves?limit=5")["rows"]
    card = page.get_by_role("region", name="Top 5 open CVEs")
    expect(card.locator("li .cve-id")).to_have_text([r["id"] for r in top])
    expect(card.locator("li .chip.priority")).to_have_text([r["priority"].capitalize() for r in top])
    first = card.locator("li").first
    expect(first.locator(".top-due")).to_contain_text(f"Due {top[0]['due_date']}")
    if top[0]["overdue"]:
        expect(first.locator(".overdue")).to_have_text("Overdue")
    expect(first.locator(".priority-reasons")).to_have_text(" · ".join(top[0]["priority_reasons"]))
    k = api(api_url, "/dashboard")["kpis"]["kev_next_due"]
    note = tile(page, "Open and exploited in the wild (CISA KEV)").locator(".tile-note")
    expect(note).to_have_text(f"Overdue since {k['due']} ({k['cve']})")


# --- A16.10: the policy and threshold on the Settings page -------------------------------------------------------

def test_a16_10_policy_saves_and_changes_due_dates(open_settings, open_cves, api_url):
    page = open_settings()
    for label, value in (("Urgent", "7"), ("High", "30"), ("Normal", "90"), ("Low", "180")):
        expect(page.get_by_label(label, exact=True)).to_have_value(value)
    adopt = page.get_by_label(re.compile("^Use CISA's KEV deadline"))
    expect(adopt).to_be_checked()
    expect(page.get_by_label("EPSS percentile for high priority")).to_have_value("90")
    page.get_by_label("Normal", exact=True).fill("120")
    page.get_by_label("Low", exact=True).fill("200")
    adopt.uncheck()
    page.get_by_role("button", name="Save changes").click()
    expect(page.locator(".save-bar").get_by_role("status")).to_have_text("✓ Changes saved")
    assert api(api_url, "/settings")["settings"]["policy"] == {
        "urgent_days": 7, "high_days": 30, "normal_days": 120, "low_days": 200, "adopt_kev_deadline": False}

    cves = open_cves("?product=langflow&kev=1")
    due = cell(cves, LANGFLOW_KEV, "Due")
    expect(due.locator(".due-date")).to_have_text("2025-05-12")  # added to KEV 2025-05-05 + 7 days
    expect(due.locator(".due-from")).to_have_text("by your policy: added to KEV + 7 days")
    expect(due.locator(".kev-deadline")).to_have_text("CISA KEV deadline 2025-05-26")  # still shown, as a fact
    assert api_row(api_url, EPSS_HIGH)["due_from"] == "published + 120 days"


def test_a16_10_days_out_of_order_are_explained_and_refused(open_settings, api_url):
    page = open_settings()
    page.get_by_label("Urgent", exact=True).fill("60")
    expect(page.get_by_role("alert").filter(has_text="urgent ≤ high ≤ normal ≤ low")).to_be_visible()
    page.get_by_role("button", name="Save changes").click()
    expect(page.locator(".save-bar")).to_contain_text("urgent ≤ high ≤ normal ≤ low")
    assert api(api_url, "/settings")["settings"]["policy"]["urgent_days"] == 7


def test_a16_10_the_threshold_is_a_setting(open_settings, api_url):
    set_stack(api_url, langflow={"internet_facing": True})
    assert api_row(api_url, EPSS_HIGH)["priority"] == "high"
    page = open_settings()
    page.get_by_label("EPSS percentile for high priority").fill("99")
    page.get_by_role("button", name="Save changes").click()
    expect(page.locator(".save-bar").get_by_role("status")).to_have_text("✓ Changes saved")
    assert api_row(api_url, EPSS_HIGH)["priority"] == "normal"


# --- A16.11: the chat's lookup_cve card shows the priority -------------------------------------------------------

def test_a16_11_lookup_cve_card_shows_priority_and_due_date(open_cves):
    from test_chat import ask

    page = open_cves()
    page.keyboard.press("Control+k")
    expect(window(page)).to_be_visible()
    answer = ask(page, f"Explain {LANGFLOW_KEV} and how to defend against it.")
    answer.get_by_role("button", name=re.compile("Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    card = answer.locator(".tool-card .cve-card")
    expect(card.locator(".chip.priority")).to_have_text("Urgent")
    expect(card).to_contain_text("KEV deadline 2025-05-26")
    expect(card).to_contain_text("due 2025-05-26 (KEV deadline)")
    expect(card.locator(".overdue")).to_have_text("Overdue")


# --- B33: a closed CVE shows no priority or due date; reopened, it gets them back -----------------------------------

CLOSED = {
    "fixed": {"status": "fixed"},
    "not_affected": {"status": "not_affected", "justification": "component_not_present"},
    "accepted": {"status": "accepted", "reason": "behind our VPN", "review_date": "2027-01-11"},
}


@pytest.mark.parametrize("status", CLOSED)
def test_b33_5_a_closed_cve_shows_no_priority_or_due_date(open_cves, api_url, status):
    api(api_url, f"/cves/{LANGFLOW_KEV}", "PATCH", CLOSED[status])  # urgent and overdue while open
    page = open_cves(f"?status={status}&product=langflow")
    priority, due = cell(page, LANGFLOW_KEV, "Priority"), cell(page, LANGFLOW_KEV, "Due")
    expect(priority).to_contain_text("—")
    expect(priority.locator(".chip.priority")).to_have_count(0)
    expect(due).to_contain_text("—")
    expect(due).not_to_contain_text("Overdue")
    expect(due).not_to_contain_text("by your policy")
    expect(due.locator(".kev-deadline")).to_have_text("CISA KEV deadline 2025-05-26")  # CISA's fact stays
    expect(priority.get_by_text("No priority: closed")).to_be_attached()  # a screen reader hears why
    row(page, LANGFLOW_KEV).get_by_role("button", name=f"Reopen {LANGFLOW_KEV}").click()
    confirm(page)
    expect(page.get_by_role("dialog")).to_have_count(0)  # saved: the dialog closes
    page = open_cves("?product=langflow&kev=1")
    expect(cell(page, LANGFLOW_KEV, "Priority").locator(".chip.priority")).to_have_text("Urgent")
    expect(cell(page, LANGFLOW_KEV, "Due")).to_contain_text("2025-05-26")
    expect(cell(page, LANGFLOW_KEV, "Due").locator(".overdue")).to_have_text("Overdue")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b33_6_the_dash_reads_in_light_and_dark_at_phone_width(open_cves, api_url, scheme):
    api(api_url, f"/cves/{LANGFLOW_KEV}", "PATCH", CLOSED["fixed"])
    page = open_cves("?status=fixed&product=langflow", width=PHONE, scheme=scheme, reduced=True)
    assert no_sideways_scroll(page)
    dash = cell(page, LANGFLOW_KEV, "Priority").locator(".no-priority")
    expect(dash).to_be_visible()
    text, bg = dash.evaluate("""el => {
        let p = el  // the first ancestor with a background of its own
        while (p.parentElement && getComputedStyle(p).backgroundColor === 'rgba(0, 0, 0, 0)') p = p.parentElement
        return [getComputedStyle(el).color, getComputedStyle(p).backgroundColor]
    }""")
    assert contrast(rgb_list(text)[0], rgb_list(bg)[0]) >= 4.5


# --- A16.12: reduced motion ---------------------------------------------------------------------------------------

# Reduced motion: scene a16_12 at the end of this file, in the shared check (reduced_motion.py).


# --- A16.13: light and dark, phone and desktop --------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a16_13_light_dark_phone_and_desktop(open_cves, open_dash, open_settings, api_url, browser_name, width,
                                             scheme):
    # Langflow not affected (every level steps down: normal and low) and Ollama internet-facing (high): all four.
    set_stack(api_url, langflow={"version": "99.0.0"}, ollama={"internet_facing": True})
    seen = {}
    for query in ("", "?product=ollama", "?product=langflow&verdict=not_affected", "?product=langflow&kev=1"):
        page = open_cves(query, width=width, scheme=scheme, reduced=True)
        assert no_sideways_scroll(page)
        actions_in_view(page)
        for chip in page.locator("table.cves .chip.priority").all()[:25]:
            name = chip.inner_text()
            if name in seen:
                continue
            text, bg = chip.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
            seen[name] = contrast(rgb_list(text)[0], rgb_list(bg)[0])
        mark = page.locator("table.cves .overdue").first
        expect(mark).to_be_visible()
        b = mark.bounding_box()
        assert b and b["x"] >= 0 and b["x"] + b["width"] <= width
    assert set(seen) == {"Urgent", "High", "Normal", "Low"}, seen
    assert all(c >= 4.5 for c in seen.values()), seen
    SHOTS.mkdir(exist_ok=True)
    page = open_cves(width=width, scheme=scheme, reduced=True)
    page.screenshot(path=SHOTS / f"a16-{browser_name}-{width}-{scheme}-cves.png")
    if width == DESKTOP:
        pin(page)
        actions_in_view(page)
        assert no_sideways_scroll(page)
        due = page.locator("table.cves td[data-label='Due']").first.bounding_box()
        chat = window(page).bounding_box()
        assert due and chat and due["x"] + due["width"] <= chat["x"]
    dash = open_dash(width=width, scheme=scheme, reduced=True)
    card = dash.get_by_role("region", name="Top 5 open CVEs")
    card.scroll_into_view_if_needed()
    assert no_sideways_scroll(dash)
    box = card.bounding_box()
    for item in card.locator("li").all():
        b = item.bounding_box()
        assert box and b and b["x"] + b["width"] <= box["x"] + box["width"] + 0.5
    dash.screenshot(path=SHOTS / f"a16-{browser_name}-{width}-{scheme}-top5.png", full_page=True)
    settings = open_settings(width=width, scheme=scheme, reduced=True)
    assert no_sideways_scroll(settings)
    policy = settings.locator("section.card", has=settings.get_by_role("heading", name="Priority and due dates"))
    policy.scroll_into_view_if_needed()
    policy.screenshot(path=SHOTS / f"a16-{browser_name}-{width}-{scheme}-policy.png")


# --- A16.14: keyboard and names -----------------------------------------------------------------------------------

def test_a16_14_keyboard_reaches_every_policy_field_with_visible_focus(open_settings):
    page = open_settings()
    page.get_by_label("Urgent", exact=True).focus()
    page.keyboard.press("Shift+Tab")
    seen = []
    for _ in range(12):
        page.keyboard.press("Tab")
        seen.append(focused(page))
        assert visible_focus(page), seen[-1]
        if seen[-1].startswith("EPSS percentile"):
            break
    for name in ("Urgent", "High", "Normal", "Low", "Use CISA's KEV deadline", "EPSS percentile for high priority"):
        assert any(s.startswith(name) for s in seen), (name, seen)
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Space")  # the KEV-deadline checkbox, by keyboard
    expect(page.get_by_label(re.compile("^Use CISA's KEV deadline"))).not_to_be_checked()
    expect(page.locator(".save-bar").get_by_role("status")).to_contain_text("Unsaved changes")


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def a16_12_priority(fx):
    open_page, open_board, open_policy = fx("open_cves"), fx("open_dash"), fx("open_settings")  # before set_stack
    set_stack(fx("api_url"), langflow={"internet_facing": True, "version": "99.0.0"})
    page = open_page(reduced=True)
    expect(page.locator("table.cves .chip.priority").first).to_be_visible()
    expect(page.locator("table.cves .overdue").first).to_be_visible()
    still(page, "priority chips, overdue")
    dash = open_board(reduced=True)
    expect(dash.locator(".top-cves .chip.priority").first).to_be_visible()
    still(dash, "the Top 5")
    settings = open_policy(reduced=True)
    settings.get_by_label("Urgent", exact=True).fill("60")
    expect(settings.get_by_role("alert").filter(has_text="urgent ≤ high")).to_be_visible()
    still(settings, "the policy card's error")

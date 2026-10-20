"""Browser check for "New" until you've seen it: opening a CVE's page, and "Mark all as seen". Check ids: B40.n (#92).

Against the live pair, as test_new_since_check.py (its fixture: one check, which finds both NEW CVEs, and a reset
around each test). Expected looks: docs/design/DESIGN.md §5.9.
"""
import pathlib
import re

import pytest
from playwright.sync_api import Page, expect

from test_live import NEW
from test_new_since_check import count, live_cves, new_box, rows  # noqa: F401 (live_cves is a fixture)
from test_cves_page import open_filters
from test_shell import contrast, no_sideways_scroll

SHOTS = pathlib.Path(__file__).parent / "screenshots"
PHONE, DESKTOP = 390, 1440


def mark_all(page: Page):
    return page.get_by_role("button", name="Mark all as seen")


def test_b40_7_opening_a_cve_page_takes_only_that_cve_out_of_new(live_cves):
    page = live_cves("?new=1")
    expect(rows(page)).to_have_count(len(NEW))
    opened, other = NEW
    with page.expect_response(re.compile(rf"/cves/{opened}/seen$")) as seen:
        page.get_by_role("link", name=opened, exact=True).click()
        expect(page.locator("#cve-title")).to_have_text(opened)
        expect(page.locator(".cve-title-row .chip.new-chip")).to_have_text("New")  # new when you opened it
    assert seen.value.ok
    page.go_back()
    expect(rows(page)).to_have_count(1)
    expect(rows(page).get_by_role("link", name=other, exact=True)).to_be_visible()
    page.reload()  # kept by the backend, not only this page
    expect(rows(page)).to_have_count(1)


def test_b40_8_mark_all_as_seen_by_keyboard_empties_new_and_keeps_the_focus(live_cves):
    page = live_cves("?new=1")
    expect(rows(page)).to_have_count(len(NEW))
    mark_all(page).focus()
    page.keyboard.press("Enter")
    expect(count(page)).to_have_text("0 CVEs · by priority, then due date")
    expect(mark_all(page)).to_have_count(0)  # nothing new: the button goes
    expect(new_box(page)).to_be_focused()  # the focus moves to the New box next to it, not to the page
    new_box(page).uncheck()
    expect(page.locator(".chip.new-chip")).to_have_count(0)  # no row says New any more


def test_b40_9_no_button_while_nothing_is_new(live_cves):
    page = live_cves(checked=False)  # live, before any check
    expect(new_box(page)).to_be_visible()
    expect(mark_all(page)).to_have_count(0)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b40_10_the_new_list_and_its_button_in_both_themes_and_on_a_phone(live_cves, scheme, width):
    page = live_cves("?new=1", width=width, scheme=scheme)
    open_filters(page)  # folded on a phone (B44)
    button = mark_all(page)
    expect(button).to_be_in_viewport()
    expect(rows(page)).to_have_count(len(NEW))
    colours = button.evaluate("el => { const s = getComputedStyle(el); return [s.color, s.backgroundColor] }")
    assert contrast(*colours) >= 4.5, colours
    box = button.bounding_box()
    assert box and box["height"] >= 24, box  # a target big enough to tap (WCAG 2.2 target size)
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    page.locator(".cves-card .filters").screenshot(path=SHOTS / f"b40-mark-all-{scheme}-{width}.png")
    page.screenshot(path=SHOTS / f"b40-new-list-{scheme}-{width}.png")

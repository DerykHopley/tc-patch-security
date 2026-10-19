"""Browser check for "New" on the CVEs page. Check ids: B05.n (#38). Until seen: B40, test_new_until_seen.py.

Runs against the live pair (live mode, the fake feeds on day 2), as test_live.py: a check changes the CVE data, so
each test starts and ends with the live data back at the snapshot (the fake feeds' reset route, which also forgets
what was new). Expected looks: docs/design/DESIGN.md §5.9.
"""
import pathlib
import re

import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from test_dashboard import api
from test_live import NEW
from test_shell import contrast, no_sideways_scroll

SHOTS = pathlib.Path(__file__).parent / "screenshots"
PHONE, DESKTOP = 400, 1400


@pytest.fixture
def live_cves(browser: Browser, live_ui_url: str, live_api_url: str):
    """Open the live pair's CVEs page (after a check, by default) in a fresh context."""
    contexts = []

    def reset():
        api(live_api_url, "/refresh/reset", "POST", {"confirm": "reset"})

    def _open(query="", width=DESKTOP, scheme="light", checked=True) -> Page:
        if checked:
            assert api(live_api_url, "/refresh", "POST")["ran"]
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(f"{live_ui_url}/cves{query}")
        expect(count(page)).to_contain_text("CVEs ·")
        return page

    reset()
    yield _open
    for ctx in contexts:
        ctx.close()
    reset()


def new_box(page: Page) -> Locator:
    return page.get_by_role("checkbox", name="New, not seen yet")


def count(page: Page) -> Locator:
    return page.locator(".cves-card .filters .meta")


def rows(page: Page) -> Locator:
    return page.locator("table.cves tbody tr")


def test_b05_6_new_chip_filter_and_url(live_cves):
    page = live_cves()
    expect(new_box(page)).not_to_be_checked()
    new_box(page).check()
    expect(page).to_have_url(re.compile(r"/cves\?new=1$"))
    expect(count(page)).to_have_text(f"{len(NEW)} CVEs · by priority, then due date")
    for cve in NEW:  # the chip on each row the check found new
        row = rows(page).filter(has=page.get_by_role("link", name=cve, exact=True))
        expect(row.locator(".chip.new-chip")).to_have_text("New")

    page.reload()  # the filter is in the URL: a reload keeps it
    expect(new_box(page)).to_be_checked()
    expect(rows(page)).to_have_count(len(NEW))

    new_box(page).uncheck()
    expect(page).to_have_url(re.compile(r"/cves$"))
    expect(count(page)).not_to_have_text(f"{len(NEW)} CVEs · by priority, then due date")


def test_b05_7_before_any_check_nothing_is_new(live_cves):
    page = live_cves("?new=1", checked=False)
    expect(new_box(page)).to_be_checked()
    expect(count(page)).to_have_text("0 CVEs · by priority, then due date")
    expect(page.locator(".chip.new-chip")).to_have_count(0)


def test_b05_8_keyboard_toggles_the_filter(live_cves):
    page = live_cves()
    new_box(page).focus()
    page.keyboard.press("Space")
    expect(page).to_have_url(re.compile(r"new=1"))
    expect(rows(page)).to_have_count(len(NEW))


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [DESKTOP, PHONE])
def test_b05_9_the_chip_in_both_themes_and_on_a_phone(live_cves, scheme, width):
    page = live_cves("?new=1", width=width, scheme=scheme)
    chip = rows(page).first.locator(".chip.new-chip")
    expect(chip).to_be_visible()
    colours = chip.evaluate("el => { const s = getComputedStyle(el); return [s.color, s.backgroundColor] }")
    assert contrast(*colours) >= 4.5, colours
    expect(new_box(page)).to_be_in_viewport()
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    rows(page).first.screenshot(path=SHOTS / f"b05-new-chip-{scheme}-{width}.png")


def test_b05_10_snapshot_mode_hides_the_filter_unless_a_link_set_it(browser: Browser, ui_url: str):
    ctx = browser.new_context(viewport={"width": DESKTOP, "height": 900})
    page = ctx.new_page()
    page.goto(f"{ui_url}/cves")
    expect(count(page)).to_contain_text("CVEs ·")
    expect(page.get_by_role("checkbox", name="In CISA KEV only")).to_be_visible()
    expect(new_box(page)).to_have_count(0)  # the snapshot never changes: nothing is ever new
    page.goto(f"{ui_url}/cves?new=1")
    expect(new_box(page)).to_be_checked()  # shown, so the filter a link set can be cleared
    new_box(page).click()  # click, not uncheck: the box goes away with the filter
    expect(new_box(page)).to_have_count(0)
    expect(page).to_have_url(re.compile(r"/cves$"))
    ctx.close()

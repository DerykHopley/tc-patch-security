"""Browser check (seam 3) for shorter CVE rows (B36, #86): one main action per row, the rest under "More"; the Due cell
says each date once. Check ids: B36.n (B36.1 to B36.4 are the unit tests in src/cveActions.test.ts and src/due.test.ts).

Before B36 a row was about 147px tall at 1440×900 (6.1 rows per 900px; 4 rows in view on load), measured 2026-10-18
in Chromium and Firefox on spec-b. The ticket asks for at least twice as many. Runs in Firefox and Chromium (run.sh).
Expected looks from docs/design/DESIGN.md §5.9.
"""
import pytest
from playwright.sync_api import Browser, Locator, Page, expect

from test_dashboard import SHOTS, api, clean_state  # noqa: F401 (fixture)
from test_cves_page import open_filters
from test_shell import contrast, no_sideways_scroll
from reduced_motion import scene, still

CVE = "CVE-2025-3248"  # Langflow: open, in KEV, your due date is the KEV deadline (the default policy adopts it)
BEFORE_PER_SCREEN = 6.1  # rows per 900px before B36 (mean row 146.8px over the first 25, both browsers)
BEFORE_IN_VIEW = 4  # whole rows in view at 1440×900 on load, before B36
DESKTOP_VP = {"width": 1440, "height": 900}
PHONE_VP = {"width": 390, "height": 844}


@pytest.fixture
def open_list(browser: Browser, ui_url: str, clean_state):
    contexts = []

    def _open(viewport=DESKTOP_VP, scheme="light", reduced=False) -> Page:
        ctx = browser.new_context(viewport=viewport, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(f"{ui_url}/cves")
        expect(page.locator("table.cves tbody tr").nth(24)).to_be_attached()
        page.evaluate("document.fonts.ready.then(() => null)")  # late web fonts move the layout (CI race)
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def row(page: Page, cve: str) -> Locator:
    return page.locator("table.cves tbody tr").filter(has=page.get_by_role("link", name=cve, exact=True))


def more(page: Page, cve: str) -> Locator:
    return page.get_by_text("More", exact=True).and_(page.get_by_label(f"More actions for {cve}"))


# The fill behind an element: its own, or the nearest ancestor's that isn't transparent
OWN_FILL = ("el => { let n = el;"
            " while (getComputedStyle(n).backgroundColor === 'rgba(0, 0, 0, 0)') n = n.parentElement;"
            " return getComputedStyle(n).backgroundColor }")
ROW_HEIGHTS = "[...document.querySelectorAll('table.cves tbody tr')].map(r => r.getBoundingClientRect().height)"
IN_VIEW = ("[...document.querySelectorAll('table.cves tbody tr')]"
           ".filter(r => r.getBoundingClientRect().bottom <= innerHeight).length")


def test_b36_5_twice_as_many_rows_per_desktop_screen(open_list):
    page = open_list()
    heights = page.evaluate(ROW_HEIGHTS)
    per_screen = 900 / (sum(heights) / len(heights))
    in_view = page.evaluate(IN_VIEW)
    print(f"B36.5: mean row {sum(heights) / len(heights):.1f}px, tallest {max(heights):.1f}px, "
          f"{per_screen:.1f} rows per 900px, {in_view} in view on load")
    assert per_screen >= 2 * BEFORE_PER_SCREEN, per_screen
    assert in_view >= 2 * BEFORE_IN_VIEW, in_view


def test_b36_6_one_phone_card_fits_the_screen(open_list, api_url):
    # An accepted CVE (its decision under the status, History (1)) is the tallest kind of card: it must fit too.
    api(api_url, f"/cves/{CVE}", "PATCH",
        {"status": "accepted", "reason": "Behind the VPN until the upgrade", "review_date": "2026-12-01",
         "compensating_control": "Only reachable over the VPN"})
    page = open_list(PHONE_VP)
    open_filters(page)  # folded on a phone (B44)
    page.get_by_label("Status").select_option("accepted")  # closed rows sort last (B33): show the accepted ones
    expect(row(page, CVE)).to_be_visible()
    tab_bar = page.locator(".sidenav").evaluate("el => el.getBoundingClientRect().height")
    room = PHONE_VP["height"] - tab_bar
    heights = page.evaluate(ROW_HEIGHTS)
    accepted = row(page, CVE).evaluate("el => el.getBoundingClientRect().height")
    print(f"B36.6: tallest card {max(heights):.0f}px, accepted card {accepted:.0f}px, room {room:.0f}px")
    assert max(heights) <= room, (max(heights), room)
    assert no_sideways_scroll(page)


def test_b36_7_one_main_action_the_rest_under_more(open_list):
    page = open_list()
    r = row(page, CVE)
    # In view: the one main action and More; nothing else of the status actions until More opens
    expect(r.get_by_role("button", name=f"Mark {CVE} fixed")).to_be_visible()
    for name in (f"Mark {CVE} not affected", f"Accept the risk of {CVE}", f"Ask about this: {CVE}"):
        expect(r.get_by_role("button", name=name, exact=True)).to_be_hidden()
    toggle = more(page, CVE)
    toggle.focus()
    page.keyboard.press("Enter")
    for name in (f"Mark {CVE} not affected", f"Accept the risk of {CVE}", f"Ask about this: {CVE}"):
        # Enabled, not only visible: the status actions stay disabled (out of the Tab order) until /dashboard brings
        # the as-of date, a separate request from the rows. A slow CI runner tabbed past them (B72, 2026-10-20).
        expect(r.get_by_role("button", name=name, exact=True)).to_be_enabled()
    # Tab goes on into the opened actions, in order
    page.keyboard.press("Tab")
    assert page.evaluate("document.activeElement.getAttribute('aria-label')") == f"Mark {CVE} not affected"
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Enter")  # closes again
    expect(r.get_by_role("button", name=f"Accept the risk of {CVE}", exact=True)).to_be_hidden()
    # Every row: exactly one status action in view
    for tr in page.locator("table.cves tbody tr").all()[:25]:
        visible = [b for b in tr.locator(".status-cell button").all() if b.is_visible()]
        assert len(visible) == 1, [b.get_attribute("aria-label") for b in visible]


def test_b36_8_the_due_cell_says_each_date_once(open_list):
    page = open_list()
    due = row(page, CVE).locator(".due-cell")
    date = due.locator(".due-date").inner_text()
    assert date and due.inner_text().count(date) == 1, due.inner_text()
    expect(due.locator(".due-from")).to_have_text("by your policy: KEV deadline")
    expect(due.locator(".kev-deadline")).to_have_count(0)


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b36_9_light_and_dark_desktop_and_phone(open_list, browser_name, scheme):
    for name, vp in (("desktop", DESKTOP_VP), ("phone", PHONE_VP)):
        page = open_list(vp, scheme)
        toggle = more(page, CVE)
        toggle.click()
        expect(row(page, CVE).get_by_role("button", name=f"Ask about this: {CVE}")).to_be_visible()
        colour = toggle.evaluate("el => getComputedStyle(el).color")
        fill = toggle.evaluate(OWN_FILL)
        assert contrast(colour, fill) >= 4.5, (colour, fill)
        assert no_sideways_scroll(page)
        page.screenshot(path=str(SHOTS / f"b36-rows-{name}-{scheme}-{browser_name}.png"))


@scene
def b36_10_more_opens_without_motion(fx):
    page = fx("open_list")(reduced=True)
    more(page, CVE).click()
    expect(row(page, CVE).get_by_role("button", name=f"Ask about this: {CVE}")).to_be_visible()
    still(page, "More opened")

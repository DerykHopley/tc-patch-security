"""Browser check (seam 3): anyone but the owner sees the Dev page's choices read-only (B29, #76). Check ids: B29.n.

The throwaway backend has sign-in off, so the browser is the owner. As test_pause_history does with `yours: false`,
the browser fakes another signed-in user by changing one answer: GET /dev/settings says `yours: false` (the backend
test B29.1 checks the server side). Expected looks come from DESIGN.md §5.5 and §5.3, not from the CSS.
"""
import pytest
from playwright.sync_api import Page, expect

from test_dev import SHOTS, dev_page  # noqa: F401 (fixture)
from test_shell import DESKTOP, PHONE, contrast, no_sideways_scroll

NOTE = "These are the owner's choices: the chat and search use them for everyone. Only the owner can change them."


def as_another_user(context) -> None:
    def not_yours(route):
        if route.request.method != "GET":
            route.continue_()
            return
        response = route.fetch()
        route.fulfill(response=response, json=response.json() | {"yours": False})

    context.route("**/dev/settings", not_yours)


def text_and_fill(page: Page, selector: str) -> tuple[str, str]:
    """The element's text colour and the first opaque background behind it."""
    return page.locator(selector).first.evaluate("""el => {
        let e = el, bg = 'rgba(0, 0, 0, 0)'
        while (e && (bg === 'rgba(0, 0, 0, 0)' || bg === 'transparent')) {
            bg = getComputedStyle(e).backgroundColor; e = e.parentElement }
        return [getComputedStyle(el).color, bg] }""")


# --- B29.5: the owner's choices, read-only: no control changes them, no Save, no run that needs the owner ----------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b29_5_another_user_sees_the_owners_choices_read_only(dev_page, browser_name, width, scheme):  # noqa: F811
    page = dev_page(width=width, scheme=scheme, reduced=True, setup=as_another_user)
    main = page.get_by_role("main")
    expect(main.get_by_test_id("owners-choices")).to_have_text(NOTE)

    model = main.locator("section.card", has=page.get_by_role("heading", name="Model", exact=True))
    expect(model.locator("dt")).to_have_text(["Who answers"])
    expect(model.locator("dd")).to_have_text(["FakeLLM (scripted)"])
    search = main.locator("section.card", has=page.get_by_role("heading", name="Agent and search", exact=True))
    expect(search.locator("dt").first).to_have_text("Max agent steps")
    expect(search.locator("dd")).to_have_count(8)

    # Nothing to change: no radio, slider, switch, text box or select, and no Save, Find models or runs. (The saved
    # checks' "compare" boxes stay: they only pick runs for the report.)
    expect(main.locator(".settings-grid, .playground").locator("input, select")).to_have_count(0)
    for name in ("Save changes", "Discard", "Reset to the defaults", "Run search", "Run model check",
                 "Run retrieval check", "Find models"):
        expect(main.get_by_role("button", name=name)).to_have_count(0)
    expect(main.get_by_test_id("owner-runs")).to_have_count(3)  # the playground and the two checks say why

    # What stays: the index facts, the map, the saved runs and the report
    expect(main.get_by_role("heading", name="Index", exact=True)).to_be_visible()
    expect(main.get_by_role("heading", name="Embedding map", exact=True)).to_be_visible()
    expect(main.get_by_role("link", name="Open the report")).to_be_visible()

    color, fill = text_and_fill(page, "[data-testid=owners-choices]")
    assert contrast(color, fill) >= 4.5
    color, fill = text_and_fill(page, ".owners-choices dd")
    assert contrast(color, fill) >= 4.5
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b29-{browser_name}-{width}-{scheme}-dev-read-only.png", full_page=True)


def test_b29_6_the_owner_still_sees_every_control(dev_page):  # noqa: F811
    page = dev_page()
    main = page.get_by_role("main")
    expect(main.get_by_test_id("owners-choices")).to_have_count(0)
    expect(main.get_by_role("radio", name="FakeLLM")).to_be_checked()
    for name in ("Reset to the defaults", "Run search", "Run model check", "Run retrieval check"):
        expect(main.get_by_role("button", name=name)).to_have_count(1)

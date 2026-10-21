"""Browser check for the warning on a proposal's control (B73, #134). Check ids: B73.4.

The watchlist marks LangChain internet-facing. FakeLLM proposes Q10 ("Mark CVE-2024-8309 as fixed"): no control,
so no warning. Editing it to Accepted with a compensating control shows the warning by the control, with the words
the backend gives (backend/tests/test_proposal_warnings.py tests when). The looks are DESIGN.md §6.6's warning line.
Every test leaves the default state, since all tests share one backend.
"""
import pytest
from playwright.sync_api import Locator, Page, expect

from test_affected import set_stack
from test_chat import ask, open_chat, window
from test_dashboard import api
from test_shell import DESKTOP, SHOTS, contrast, no_sideways_scroll, open_app  # noqa: F401 (fixture)
from reduced_motion import scene, still

CVE = "CVE-2024-8309"
WARNING = "Your watchlist marks LangChain internet-facing. Check this control matches."
PHONE = 390  # a small phone, narrower than test_shell's 400


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})
    set_stack(api_url, langchain={"internet_facing": True})
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


def accept_with_a_control(page: Page) -> Locator:
    """Q10's card, edited to Accepted with a VPN-only control."""
    open_chat(page)
    card = ask(page, f"Mark {CVE} as fixed").locator(".proposal-card")
    expect(card.locator(".proposal-warning")).to_have_count(0)  # no control, no warning
    card.get_by_role("button", name="Edit", exact=True).click()
    form = card.get_by_role("form", name=f"Edit: Mark {CVE} fixed")
    form.get_by_role("combobox", name="Status").select_option("accepted")
    form.get_by_role("textbox", name="Reason (required)").fill("Only staff use it")
    form.get_by_role("textbox", name="Compensating control (optional)").fill("Only reachable over the VPN")
    form.get_by_role("button", name="Save changes").click()
    expect(card.locator(".result-title")).to_have_text(f"Accept the risk of {CVE}")
    return card


def test_b73_4_a_control_on_an_internet_facing_product_shows_the_warning_by_it(open_app):
    page = open_app()
    card = accept_with_a_control(page)
    warning = card.locator(".proposal-warning")
    expect(warning).to_have_text(f"Warning: {WARNING}")  # "Warning: " for screen readers; the edge shows it
    # Right under the control's line, before the buttons
    control = card.locator(".after-line", has_text="Control: Only reachable over the VPN")
    assert control.evaluate("(el, w) => el.nextElementSibling === w", warning.element_handle())

    card.get_by_role("button", name="Edit", exact=True).click()  # take the control out again: the warning goes
    form = card.get_by_role("form", name=f"Edit: Accept the risk of {CVE}")
    form.get_by_role("textbox", name="Compensating control (optional)").fill("")
    form.get_by_role("button", name="Save changes").click()
    expect(card.locator(".after-line", has_text="Control:")).to_have_count(0)
    expect(warning).to_have_count(0)


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b73_4_the_warning_reads_well_in_light_and_dark_and_on_a_phone(open_app, browser_name, width, scheme):
    page = open_app(width=width, scheme=scheme, reduced=True)
    card = accept_with_a_control(page)
    warning = card.locator(".proposal-warning")
    expect(warning).to_be_visible()
    fg, bg = warning.evaluate("el => [getComputedStyle(el).color, getComputedStyle(el).backgroundColor]")
    assert contrast(fg, bg) >= 4.5, (scheme, fg, bg)
    box, win = card.bounding_box(), window(page).bounding_box()
    assert box and win and box["x"] + box["width"] <= win["x"] + win["width"] + 0.5
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    card.scroll_into_view_if_needed()
    page.screenshot(path=SHOTS / f"b73-{browser_name}-{width}-{scheme}-proposal-warning.png")


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) ---------------------------------------

@scene
def b73_4_proposal_warning(fx):
    set_stack(fx("api_url"), langchain={"internet_facing": True})  # reduced_motion_defaults resets it after
    page = fx("open_app")(reduced=True)
    card = accept_with_a_control(page)
    expect(card.locator(".proposal-warning")).to_be_visible()
    still(page, "the warning by the control")
    card.get_by_role("button", name="Cancel", exact=True).click()  # leaves the shared state as it was
    expect(card.locator("output.proposal-line")).to_contain_text("Cancelled")

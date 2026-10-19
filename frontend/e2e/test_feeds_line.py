"""Browser check (seam 3) for where live data comes from (B28, #74): the Data card's line and the freshness card's
warning. Check ids: B28.n.

Every pair run.sh starts sets FEEDS=fake, so the browser sees the warning: "Live: the made-up test data, not
the real feeds" (no setting's name since B50), `--text` on `--warn-soft` with a 3px `--warn` edge (DESIGN.md §5.7's edge rule). The real feeds' words
("Live: NVD, CISA KEV, EPSS and OSV.dev") are checked by `npm test` (src/feeds.test.ts) and the API by the backend's
tests: no browser check may reach the real services. Sign-in is off, so the one local user is the owner.
"""
import pytest
from playwright.sync_api import Locator, Page, expect

from test_live import card, open_live, live_reset  # noqa: F401  (fixtures)
from test_settings import panel
from test_settings_over_env import open_settings, server_defaults  # noqa: F401  (fixtures)
from test_shell import DESKTOP, PHONE, contrast, no_sideways_scroll
from reduced_motion import scene, still

FAKE = "Live: the made-up test data, not the real feeds"


def looks_like_a_warning(page: Page, line: Locator, box: Locator) -> None:
    """The edge rule: `--text` on `--warn-soft` (at least 4.5:1), a 3px `--warn` edge, inside its card, no sideways
    scroll."""
    expect(line).to_have_text(FAKE)
    style = line.evaluate("""el => { const s = getComputedStyle(el); return {
        colour: s.color, fill: s.backgroundColor, edge: s.borderLeftColor, width: s.borderLeftWidth } }""")
    tokens = page.evaluate("""() => { const p = document.createElement('p');
        document.body.append(p); const out = {};
        for (const [k, v] of [['warn', '--warn'], ['soft', '--warn-soft'], ['text', '--text']]) {
          p.style.color = `var(${v})`; out[k] = getComputedStyle(p).color }
        p.remove(); return out }""")
    assert (style["colour"], style["edge"], style["width"]) == (tokens["text"], tokens["warn"], "3px")
    assert style["fill"] == tokens["soft"]
    assert contrast(style["colour"], style["fill"]) >= 4.5
    inner, outer = line.bounding_box(), box.bounding_box()
    assert inner and outer and inner["x"] >= outer["x"] and inner["x"] + inner["width"] <= outer["x"] + outer["width"]
    assert no_sideways_scroll(page)


# --- B28.7: the Data card says where live data comes from (the owner's) -------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b28_7_the_data_card_warns_that_live_mode_reads_made_up_data(open_settings, scheme, width):
    page = open_settings(width=width, scheme=scheme)
    data = panel(page, "Data")
    line = data.get_by_test_id("feeds-line")
    looks_like_a_warning(page, line, data)
    # under the Live choice it describes, before the NVD key
    live = data.get_by_label("Live").bounding_box()
    key = data.get_by_label("NVD API key (optional)").bounding_box()
    box = line.bounding_box()
    assert live and key and box and live["y"] < box["y"] < key["y"]


# --- B28.8: the dashboard's freshness card says the same, in live mode only ---------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b28_8_the_freshness_card_warns_in_live_mode_on_the_fake_feeds(open_live, scheme, width):
    page = open_live(width=width, scheme=scheme)
    looks_like_a_warning(page, card(page).get_by_test_id("feeds-warning"), card(page))
    # right under the last-checked line, above Check now
    checked = card(page).locator(".checked-line").bounding_box()
    warning = card(page).get_by_test_id("feeds-warning").bounding_box()
    check = card(page).get_by_role("button", name="Check now").bounding_box()
    assert checked and warning and check and checked["y"] < warning["y"] < check["y"]


def test_b28_8_the_snapshot_needs_no_warning(page: Page, ui_url: str):
    page.goto(ui_url + "/")
    freshness = card(page)
    expect(freshness.locator(".checked-line")).to_contain_text("A frozen snapshot")
    expect(freshness.get_by_test_id("feeds-warning")).to_have_count(0)


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) ------------------------------------

@scene
def b28_9_feeds_warning(fx):
    page = fx("open_live")(reduced=True)
    expect(card(page).get_by_test_id("feeds-warning")).to_have_text(FAKE)
    still(page, "the freshness card's feeds warning")

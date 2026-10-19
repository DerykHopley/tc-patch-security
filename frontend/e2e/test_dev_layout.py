"""Browser check (seam 3) for the Dev page's card layout: Model and Index stacked on the left, Agent and search on
the right, so a short Model card never leaves a hole above Index (B39, the owner's report of 2026-10-19).
Check ids: B39.n. Expected values come from docs/design/DESIGN.md §5.6.3, not from the CSS.
"""
import pytest
from playwright.sync_api import Page

from test_dev import SHOTS, dev_page  # noqa: F401 (fixture)
from test_dev_owner import as_another_user
from test_shell import DESKTOP, PHONE, no_sideways_scroll

ORDER = ["Model", "Agent and search", "Index"]  # DOM order = Tab order = the one-column order
GAP = 1.2 * 16  # the gap between cards (DESIGN.md §4.1)


def cards(page: Page) -> dict[str, dict]:
    """Each card in the Dev grid: its title and box, in DOM order (dicts keep it)."""
    return dict(page.evaluate("""[...document.querySelectorAll('.settings-grid > section.card')].map(c => {
        const r = c.getBoundingClientRect();
        return [c.querySelector('h2').textContent, {x: r.left, y: r.top + scrollY, width: r.width, height: r.height}] })"""))


def shot(page: Page, name: str) -> None:
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"{name}.png", full_page=True)


def assert_index_under_model(box: dict[str, dict]) -> None:
    model, search, index = box["Model"], box["Agent and search"], box["Index"]
    assert abs(model["x"] - index["x"]) <= 1  # the left column
    assert search["x"] > model["x"] + model["width"]  # the right column
    assert abs(search["y"] - model["y"]) <= 1  # both start at the top
    assert abs(index["y"] - (model["y"] + model["height"] + GAP)) <= 2  # one gap under Model, not under Agent and search


# --- B39.1: at 1400px Index sits one gap under Model, whatever the Model card holds ----------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b39_1_index_sits_under_model_at_desktop_width(dev_page, browser_name, scheme):  # noqa: F811
    page = dev_page(width=DESKTOP, scheme=scheme, reduced=True)
    shot(page, f"b39-{browser_name}-{DESKTOP}-{scheme}-dev-layout")
    box = cards(page)
    assert list(box) == ORDER
    assert_index_under_model(box)
    assert no_sideways_scroll(page)


def test_b39_1_a_tall_model_card_still_packs(dev_page, browser_name):  # noqa: F811
    page = dev_page(width=DESKTOP, reduced=True)
    page.get_by_role("radio", name="Local model").check()  # the tallest Model card: URL, presets, model, temperature
    shot(page, f"b39-{browser_name}-{DESKTOP}-light-dev-layout-local")
    assert_index_under_model(cards(page))


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b39_1_the_read_only_page_packs_too(dev_page, browser_name, scheme):  # noqa: F811
    page = dev_page(width=DESKTOP, scheme=scheme, reduced=True, setup=as_another_user)
    shot(page, f"b39-{browser_name}-{DESKTOP}-{scheme}-dev-layout-read-only")
    assert_index_under_model(cards(page))


# --- B39.2: at 400px one column in DOM order, one gap between cards, no sideways scroll ------------------------------

@pytest.mark.parametrize("yours", [True, False])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_b39_2_one_column_in_order_on_a_phone(dev_page, scheme, yours):  # noqa: F811
    page = dev_page(width=PHONE, scheme=scheme, reduced=True, setup=None if yours else as_another_user)
    box = cards(page)
    assert list(box) == ORDER
    assert len({round(b["x"]) for b in box.values()}) == 1
    tops = [box[t] for t in ORDER]
    for above, below in zip(tops, tops[1:]):  # no empty row, no extra gap from the span
        assert abs(below["y"] - (above["y"] + above["height"] + GAP)) <= 2
    assert no_sideways_scroll(page)

"""Browser check for the model-check report's script (A20). Check id: A20.1.

The report is a static file, so this needs no server: it builds the fake report (FakeLLM and fake embedders, no
network), as CI does, and opens it from disk. The backend tests read the report's HTML; only a browser runs its script.
"""
import pathlib
import subprocess

import pytest
from playwright.sync_api import Page, expect

BACKEND = pathlib.Path(__file__).resolve().parents[2] / "backend"


@pytest.fixture(scope="module")
def report(tmp_path_factory) -> pathlib.Path:
    out = tmp_path_factory.mktemp("report") / "report.html"
    subprocess.run(["uv", "run", "python", "-m", "app.evals", "fake-report", "--out", str(out)], cwd=BACKEND,
                   check=True, capture_output=True)
    return out


def test_a20_1_at_a_glance_switch_swaps_the_chart(page: Page, report: pathlib.Path):
    """Found by Deryk on the published report: "Seconds per question" pressed, the cost chart stayed. The script set
    .hidden on the <svg>s, which only HTML elements have."""
    page.goto(report.as_uri())
    glance = page.locator("#glance")
    cost, time = glance.locator("#glance-cost"), glance.locator("#glance-time")
    expect(cost).to_be_visible()
    expect(time).to_be_hidden()

    glance.get_by_role("button", name="Seconds per question").click()
    expect(time).to_be_visible()
    expect(cost).to_be_hidden()
    expect(glance.get_by_role("button", name="Seconds per question")).to_have_attribute("aria-pressed", "true")

    glance.get_by_role("button", name="Cost per question").click()
    expect(cost).to_be_visible()
    expect(time).to_be_hidden()

"""Browser check (seam 3) for the model check, the retrieval check and the report on the Dev page. Check ids: A12.n,
from ticket #14.

Runs in Firefox and Chromium against run.sh's throwaway servers (FakeLLM, hash embedder). Runs pile up in the
throwaway state folder: tests look for their own run, never count all of them. Expected looks come from DESIGN.md
§5.2–5.3, §10, not from the CSS.
"""
import json
import re
import urllib.request
from urllib.parse import parse_qs, urlparse

import pytest
from playwright.sync_api import Browser, Page, expect

from test_dev import DESKTOP, PHONE, SHOTS, api, css_var, resolved, style


@pytest.fixture(autouse=True)
def default_dev_settings(api_url: str):
    yield
    api(api_url, "/dev/settings", "PUT", api(api_url, "/dev/settings")["defaults"])


@pytest.fixture
def dev_page(browser: Browser, ui_url: str):
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(ui_url)
        page.get_by_role("button", name="Dev", exact=True).click()
        expect(page.get_by_role("heading", name="Model check", exact=True)).to_be_visible()
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def run_model_check(page: Page):
    page.get_by_role("button", name="Run model check").click()
    result = page.get_by_role("region", name="Model check result")
    expect(result.get_by_text("questions passed")).to_be_visible()
    return result


def run_retrieval_check(page: Page):
    """Click and wait for this run to finish: the button reads "Running…" until then (older runs are listed already)."""
    page.get_by_role("button", name="Run retrieval check").click()
    expect(page.get_by_role("button", name="Run retrieval check")).to_be_enabled()


def no_sideways_scroll(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


# --- A12.6: the model check in the dev panel -----------------------------------------------------------------------

def test_a12_6_fakellm_passes_every_question_in_the_dev_panel(dev_page, api_url):
    page = dev_page()
    expect(page.get_by_text("Asks the scripted questions of FakeLLM (scripted)")).to_be_visible()
    result = run_model_check(page)
    n = len(json.load(urllib.request.urlopen(api_url + "/examples")))
    expect(result.locator(".eval-numbers")).to_contain_text(f"{n} / {n}questions passed")
    expect(result.locator(".verdict.pass")).to_have_count(n)
    expect(result.get_by_text("$0").first).to_be_visible()  # FakeLLM is free
    # A question opens to its answer
    q1 = result.get_by_role("button", name="Q1: show the answer")
    q1.click()
    expect(q1).to_have_attribute("aria-expanded", "true")
    expect(result.locator(".eval-answer-text")).to_contain_text("Langflow")


def test_a12_6_past_runs_listed_and_two_side_by_side(dev_page):
    page = dev_page()
    run_model_check(page)
    page.reload()
    page.get_by_role("button", name="Dev", exact=True).click()
    run_model_check(page)
    boxes = page.get_by_role("checkbox", name=re.compile(r"^Compare FakeLLM"))
    expect(boxes.nth(1)).to_be_visible()
    boxes.nth(0).check()
    boxes.nth(1).check()
    side = page.get_by_role("region", name="Runs side by side")
    expect(side).to_be_visible()
    expect(side.locator("thead th")).to_have_count(3)  # the measure, then one column per run
    for label in ("Questions passed", "Right tools", "Real citations", "Cost per question", "Time per question"):
        expect(side.get_by_role("rowheader", name=label)).to_be_visible()
    # The report link carries the ticked runs
    href = page.get_by_role("link", name=re.compile("Open the report")).get_attribute("href")
    query = parse_qs(urlparse(href).query)
    assert urlparse(href).path == "/dev/report" and len(query["models"][0].split(",")) == 2


def test_a12_6_save_first_before_a_model_check(dev_page):
    page = dev_page()
    run = page.get_by_role("button", name="Run model check")
    # The saved settings load after the heading: a field filled before that is reset by the load (CI race).
    expect(run).to_be_enabled()
    expect(page.get_by_label("Sources per search")).not_to_have_value("")
    page.get_by_label("Sources per search").fill("7")
    expect(run).to_be_disabled()
    expect(page.get_by_text("Save your settings first")).to_be_visible()


# --- A12.6: the retrieval check ------------------------------------------------------------------------------------

def test_a12_6_retrieval_check_for_the_loaded_embedder(dev_page):
    page = dev_page()
    run_retrieval_check(page)
    show = page.get_by_role("button", name=re.compile(r"^hash-4096, .*: show the misses")).first
    expect(show).to_have_attribute("aria-expanded", "true")  # the new run opens to its misses
    row = page.locator("table.runs tr", has=show)
    cells = [c for c in row.locator("td.num").all_inner_texts()]
    assert all(re.fullmatch(r"[01]\.\d\d", c) for c in cells[:4]), cells  # hit rate and MRR, vector and hybrid
    expect(page.get_by_role("heading", name=re.compile(r"^Vector: \d+ of \d+ not in the top 5"))).to_be_visible()
    show.click()
    expect(show).to_have_attribute("aria-expanded", "false")


# --- A12.6: the report -----------------------------------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_a12_6_the_report_opens_in_both_themes_at_both_widths(dev_page, browser_name, width):
    page = dev_page(width=width)
    run_model_check(page)
    run_retrieval_check(page)
    link = page.get_by_role("link", name=re.compile("Open the report"))
    expect(link).to_have_attribute("target", "_blank")
    with page.context.expect_page() as new:
        link.click()
    report = new.value
    report.wait_for_load_state()
    expect(report.get_by_role("heading", name="Models side by side")).to_be_visible()
    expect(report.locator("#models")).to_contain_text("FakeLLM (scripted)")
    expect(report.locator("#embedders")).to_contain_text("hash-4096")
    for sid in ("explain-levels", "fix-first", "findings"):
        expect(report.locator(f"#{sid}")).to_be_visible()
    toggle = report.get_by_role("button", name="Switch to dark mode")
    for scheme in ("light", "dark"):
        assert report.evaluate("document.documentElement.dataset.theme") == scheme
        card = report.locator("section.card").first
        assert style(card, "backgroundColor") == resolved(report, css_var(report, "--surface"))
        assert no_sideways_scroll(report)
        SHOTS.mkdir(exist_ok=True)
        report.screenshot(path=SHOTS / f"a12-{browser_name}-{width}-{scheme}-report.png", full_page=True)
        if scheme == "light":
            toggle.click()
            expect(report.get_by_role("button", name="Switch to light mode")).to_be_visible()


# --- A12.6: light and dark, phone and desktop; A12.7: keyboard and names -------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a12_6_works_in_both_themes_at_both_widths(dev_page, browser_name, width, scheme):
    page = dev_page(width=width, scheme=scheme, reduced=True)
    result = run_model_check(page)
    result.get_by_role("button", name="Q2: show the answer").click()
    run_retrieval_check(page)
    expect(page.get_by_role("heading", name=re.compile(r"^Hybrid: "))).to_be_visible()
    assert no_sideways_scroll(page)
    # Pass marks: --text on a soft fill with a coloured edge, never a colour alone
    mark = result.locator(".verdict.pass").first
    assert style(mark, "color") == resolved(page, css_var(page, "--text"), "color")
    assert mark.inner_text().startswith("✓")
    for card in page.locator("section.card").all():
        assert style(card, "borderTopLeftRadius") == "26px"
    run = page.get_by_role("button", name="Run model check")
    assert "gradient" in style(run, "backgroundImage") and style(run, "borderTopLeftRadius") == "999px"
    SHOTS.mkdir(exist_ok=True)
    page.locator("section.model-check").screenshot(path=SHOTS / f"a12-{browser_name}-{width}-{scheme}-check.png")


def test_a12_7_keyboard_reaches_the_checks_with_visible_focus(dev_page):
    page = dev_page()
    run_model_check(page)
    run_retrieval_check(page)
    page.get_by_role("button", name="Run model check").focus()
    seen = []
    for _ in range(300):  # runs pile up in the shared backend: up to 50 listed per kind, two controls each
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement === document.body"):
            break
        seen.append(page.evaluate("""(() => { const a = document.activeElement;
            return (a.getAttribute('aria-label') || a.textContent || '').trim() })()"""))
        outline = page.evaluate("""(() => { const s = getComputedStyle(document.activeElement);
            return [s.outlineStyle, s.outlineWidth] })()""")
        assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2, seen[-1]
    text = " | ".join(seen)
    for name in ("Q1: show the answer", "Compare FakeLLM", "Show the run of FakeLLM", "Run retrieval check",
                 "show the misses", "Put hash-4096", "Open the report"):
        assert name in text, (name, seen)


def test_a12_7_buttons_and_boxes_have_accessible_names(dev_page):
    page = dev_page()
    run_model_check(page)
    run_retrieval_check(page)
    sel = ".model-check button, .model-check input, .retrieval-check button, .retrieval-check input"
    unnamed = page.evaluate(f"""[...document.querySelectorAll('{sel}')].filter(b => !(b.getAttribute('aria-label')
        || (b.labels && b.labels.length && b.labels[0].textContent) || b.textContent || '').trim()).length""")
    assert unnamed == 0
    expect(page.get_by_role("progressbar")).to_have_count(0)  # only while running, then named "Model check progress"

"""Browser check (seam 3) for the design tokens and the app shell. Check ids: A02.n, from ticket #4.

Runs in Firefox and Chromium (run.sh). Expected values come from docs/design/DESIGN.md, not from the CSS.
"""
import pathlib
import re

import pytest
from playwright.sync_api import Browser, Page, expect

SHOTS = pathlib.Path(__file__).parent / "screenshots"
PHONE, DESKTOP = 400, 1400


@pytest.fixture
def open_app(browser: Browser, ui_url: str):
    """Opens the app in a fresh context: width, system colour scheme, motion preference, URL query."""
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False, query="", init_script=None) -> Page:
        ctx = browser.new_context(
            viewport={"width": width, "height": 900},
            color_scheme=scheme,
            reduced_motion="reduce" if reduced else "no-preference",
        )
        contexts.append(ctx)
        page = ctx.new_page()
        if init_script:
            page.add_init_script(init_script)
        page.goto(ui_url + query)
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def css_var(page: Page, name: str) -> str:
    return page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('{name}').trim()")


def sidebar_width(page: Page) -> float:
    return page.locator(".sidenav").evaluate("el => el.getBoundingClientRect().width")


def no_sideways_scroll(page: Page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def contrast(a: str, b: str) -> float:
    """WCAG 2 contrast ratio of two colours given as #rrggbb or rgb()/rgba() strings."""
    def rgb(c: str) -> list[float]:
        if c.startswith("#"):
            return [int(c[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        return [float(v) / 255 for v in re.findall(r"[\d.]+", c)[:3]]

    def lum(c: str) -> float:
        r, g, b_ = (x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in rgb(c))
        return 0.2126 * r + 0.7152 * g + 0.0722 * b_

    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


# --- Tokens (DESIGN.md §3) ---------------------------------------------------------------------------------------

LIGHT = {
    "--bg": "#dfe5fd", "--surface": "#ffffff", "--text": "#2a2559", "--muted": "#605d8c", "--border": "#e4e5f8",
    "--accent": "#6c4cf5", "--accent-soft": "#efeaff", "--user": "#efeaff", "--ok": "#12a46b", "--error": "#e5385a",
    "--error-soft": "#ffe8ed", "--warn": "#b8640a", "--warn-soft": "#fff1de", "--series-1": "#7b5cff", "--grid": "#eceefb",
    "--sev-low": "#a48bff", "--sev-medium": "#7b5cff", "--sev-high": "#5235d6", "--sev-critical": "#2e1a80",
    "--cat-1": "#6c4cf5", "--cat-2": "#e2780f", "--cat-3": "#e0306a",
}
DARK = {
    "--bg": "#0f0f1c", "--surface": "#1a1a2e", "--text": "#ecebff", "--muted": "#a9a8cc", "--border": "#2c2b48",
    "--accent": "#a28dff", "--accent-soft": "#2a2550", "--user": "#2a2550", "--ok": "#4fd39a", "--error": "#ff7a95",
    "--error-soft": "#3a1c2a", "--warn": "#ffb547", "--warn-soft": "#33281a", "--series-1": "#a28dff", "--grid": "#25243d",
    "--sev-low": "#5641c4", "--sev-medium": "#7860f2", "--sev-high": "#a796ff", "--sev-critical": "#d9d0ff",
    "--cat-1": "#8a70ff", "--cat-2": "#d4761a", "--cat-3": "#e33e6e",
}
SHAPE = {
    "--radius-sidebar": "28px", "--radius-card": "26px", "--radius-tile": "24px", "--radius-banner": "28px",
    "--radius-save-bar": "20px", "--radius-message": "20px", "--radius-nested": "18px", "--radius-input": "14px",
    "--radius-item": "16px", "--radius-pill": "999px",
    "--shadow-sidebar": "0 16px 40px rgba(108, 76, 245, 0.12)", "--shadow-card": "0 12px 30px rgba(108, 76, 245, 0.09)",
    "--shadow-primary": "0 6px 14px rgba(108, 76, 245, 0.3)",
}


@pytest.mark.parametrize(("scheme", "expected"), [("light", LIGHT), ("dark", DARK)])
def test_a02_2_colour_tokens_light_and_dark(open_app, scheme, expected):
    page = open_app(scheme=scheme)
    assert page.evaluate("document.documentElement.dataset.design") == "playful"
    assert page.evaluate("document.documentElement.dataset.theme") == scheme
    assert {name: css_var(page, name).lower() for name in expected} == expected


def test_a02_2_shape_type_and_background_tokens(open_app):
    page = open_app()
    assert {name: re.sub(r"\s+", " ", css_var(page, name)) for name in SHAPE} == SHAPE
    assert page.evaluate("getComputedStyle(document.body).fontSize") == "15px"
    assert page.evaluate("getComputedStyle(document.body).fontFamily").startswith("Nunito")
    assert page.evaluate("getComputedStyle(document.querySelector('h1')).fontFamily").startswith("Fredoka")
    light_bg = page.evaluate("getComputedStyle(document.body).backgroundImage")
    assert light_bg.count("radial-gradient") == 3
    assert page.evaluate("getComputedStyle(document.body).backgroundAttachment").startswith("fixed")
    page.get_by_role("button", name="Switch to dark mode").click()
    assert page.evaluate("getComputedStyle(document.body).backgroundImage").count("radial-gradient") == 1


def test_a02_13_fonts_load_from_the_html_head(open_app):
    page = open_app()
    hrefs = page.evaluate("[...document.head.querySelectorAll('link')].map(l => l.rel + ' ' + l.href)")
    assert any(h.startswith("preconnect") for h in hrefs)
    font_css = [h for h in hrefs if h.startswith("stylesheet") and "fonts.googleapis.com" in h]
    assert font_css and "Fredoka" in font_css[0] and "Nunito" in font_css[0]


# --- Design faults fixed (DESIGN.md §12.1) ------------------------------------------------------------------------

def test_a02_3_muted_text_passes_on_the_page_background_and_soft_fills(open_app):
    page = open_app()
    muted = page.locator(".crumb-path").evaluate("el => getComputedStyle(el).color")
    assert contrast(muted, css_var(page, "--bg")) >= 4.5
    assert contrast(muted, css_var(page, "--accent-soft")) >= 4.5


def test_a02_3_primary_gradient_passes_with_white_text_at_both_ends(open_app):
    page = open_app()
    stops = re.findall(r"#[0-9a-f]{6}", css_var(page, "--gradient-primary").lower())
    assert len(stops) == 2
    for stop in stops:
        assert contrast("#ffffff", stop) >= 4.5, stop
    active = page.get_by_role("button", name="Dashboard")
    assert active.evaluate("el => getComputedStyle(el).color") == "rgb(255, 255, 255)"
    assert "linear-gradient" in active.evaluate("el => getComputedStyle(el).backgroundImage")


# --- Shell (DESIGN.md §4.1) ---------------------------------------------------------------------------------------

def test_a02_4_sidebar_has_brand_sections_snapshot_card_and_collapse(open_app):
    page = open_app()
    side = page.get_by_role("complementary", name="Main")
    expect(side.get_by_text("LLM Security", exact=True)).to_be_visible()
    expect(side.get_by_text("assistant", exact=True)).to_be_visible()
    expect(side.get_by_text("Monitor", exact=True)).to_be_visible()
    expect(side.get_by_text("Assistant", exact=True)).to_be_visible()
    for name in ("Dashboard", "Settings", "Dev", "Ask Patch"):
        expect(side.get_by_role("button", name=name, exact=True)).to_be_visible()
    card = side.locator(".side-card")
    expect(card.get_by_text("Snapshot")).to_be_visible()
    expect(card.get_by_text("Data as of 2026-10-13")).to_be_visible()
    expect(card.get_by_text("FakeLLM (scripted)")).to_be_visible()
    expect(card.locator("svg.robot")).to_have_attribute("aria-hidden", "true")
    assert sidebar_width(page) == 250


def test_a02_4_collapsed_rail_keeps_names_and_is_remembered(open_app):
    page = open_app()
    page.get_by_role("button", name="Collapse the sidebar").click()
    expect(page.get_by_role("button", name="Expand the sidebar")).to_be_visible()
    page.wait_for_function("document.querySelector('.sidenav').getBoundingClientRect().width === 78")
    expect(page.locator(".side-card")).to_be_hidden()
    expect(page.get_by_text("LLM Security", exact=True)).to_be_hidden()
    for name in ("Dashboard", "Settings", "Dev", "Ask Patch"):
        expect(page.get_by_role("button", name=name, exact=True)).to_be_visible()
    page.reload()
    expect(page.get_by_role("button", name="Expand the sidebar")).to_be_visible()
    assert sidebar_width(page) == 78
    page.get_by_role("button", name="Expand the sidebar").click()
    page.wait_for_function("document.querySelector('.sidenav').getBoundingClientRect().width === 250")


def test_a02_5_pages_reachable_and_active_page_shown_everywhere(open_app):
    page = open_app()
    for name, title in (("Settings", "Settings"), ("Dev", "Dev panel"), ("Dashboard", "Dashboard")):
        page.get_by_role("button", name=name, exact=True).click()
        expect(page.get_by_role("heading", level=1)).to_have_text(title)
        expect(page.locator(".crumb-path")).to_have_text(f"Pages / {title}")
        expect(page.get_by_role("button", name=name, exact=True)).to_have_attribute("aria-current", "page")
        expect(page.locator("[aria-current=page]")).to_have_count(1)
        expect(page.get_by_role("main")).to_be_visible()


def test_a02_5_dev_page_hidden_when_the_backend_disallows_it(open_app):
    def no_dev(page: Page):
        def handle(route):
            resp = route.fetch()
            route.fulfill(response=resp, json={**resp.json(), "dev_panel": False})
        page.route("**/health", handle)

    page = open_app()
    no_dev(page)
    page.reload()
    expect(page.get_by_role("button", name="Settings", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Dev", exact=True)).to_have_count(0)


def test_a02_5_ask_patch_is_named_and_reachable_but_a_placeholder(open_app):
    page = open_app()
    ask = page.get_by_role("button", name="Ask Patch")
    expect(ask).to_have_attribute("aria-disabled", "true")
    ask.focus()
    expect(ask).to_be_focused()


def test_a02_4_snapshot_card_says_offline_without_backend(open_app):
    page = open_app(init_script="window.fetch = () => Promise.reject(new TypeError('offline'))")
    expect(page.locator(".side-card").get_by_text("Backend offline")).to_be_visible()
    expect(page.get_by_role("button", name="Dev", exact=True)).to_have_count(0)


# --- Light and dark (DESIGN.md §9), remembered state (§11) --------------------------------------------------------

def test_a02_6_toggle_switches_instantly_is_remembered_and_overrides_the_system(open_app):
    page = open_app(scheme="dark")
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.get_by_role("button", name="Switch to light mode").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "light"
    assert css_var(page, "--surface") == "#ffffff"
    page.reload()
    expect(page.get_by_role("button", name="Switch to dark mode")).to_be_visible()
    assert page.evaluate("document.documentElement.dataset.theme") == "light"  # saved choice beats the system


def test_a02_6_url_theme_wins_over_the_saved_choice(open_app):
    page = open_app()
    page.get_by_role("button", name="Switch to dark mode").click()
    page.goto(page.url.split("?")[0] + "?theme=light")
    assert page.evaluate("document.documentElement.dataset.theme") == "light"


def test_a02_6_theme_is_set_before_the_app_runs(browser: Browser, ui_url: str):
    # Set by an inline script in <head>, so the first frame is already dark: no flash of the light theme.
    ctx = browser.new_context(color_scheme="dark")
    page = ctx.new_page()
    page.route("**/src/main.tsx", lambda route: route.abort())  # the app never starts
    page.goto(ui_url)
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    ctx.close()


BLOCKED_STORAGE = """
Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('blocked', 'SecurityError') } });
"""


def test_a02_7_blocked_storage_never_breaks_the_app(open_app):
    page = open_app(init_script=BLOCKED_STORAGE)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.get_by_role("button", name="Switch to dark mode").click()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    page.get_by_role("button", name="Collapse the sidebar").click()
    expect(page.get_by_role("button", name="Expand the sidebar")).to_be_visible()
    assert errors == []


# --- Phone width and no sideways scroll (DESIGN.md §4.2) ----------------------------------------------------------

def test_a02_8_bottom_tab_bar_on_phones(open_app):
    page = open_app(width=PHONE)
    bar = page.locator(".sidenav").bounding_box()
    assert bar is not None
    assert bar["x"] == 0 and bar["width"] == PHONE and bar["y"] + bar["height"] == 900
    expect(page.get_by_role("button", name="Ask Patch")).to_be_visible()
    assert page.get_by_role("button", name="Ask Patch").locator(".side-label").inner_text().strip() == "Ask"
    for hidden in (".brand", ".side-section", ".side-card", ".collapse-btn"):
        expect(page.locator(hidden).first).to_be_hidden()
    icon = page.get_by_role("button", name="Settings").locator(".side-icon").bounding_box()
    label = page.get_by_role("button", name="Settings").locator(".side-label").bounding_box()
    assert icon and label and icon["y"] + icon["height"] <= label["y"] + 1  # icon over label


def test_a02_8_nothing_hidden_behind_the_tab_bar(open_app):
    page = open_app(width=PHONE)
    page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
    last = page.locator("main > :last-child").bounding_box()
    bar = page.locator(".sidenav").bounding_box()
    assert last and bar and last["y"] + last["height"] <= bar["y"]


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a02_8_no_sideways_scroll(open_app, width, scheme):
    page = open_app(width=width, scheme=scheme)
    for name in ("Dashboard", "Settings", "Dev"):
        page.get_by_role("button", name=name, exact=True).click()
        assert no_sideways_scroll(page), name


# --- Motion (DESIGN.md §7) ----------------------------------------------------------------------------------------

CURSOR_OPACITIES = """async () => {
  const h1 = document.querySelector('h1');
  const seen = new Set();
  for (let i = 0; i < 26; i++) {
    seen.add(getComputedStyle(h1, '::after').opacity);
    await new Promise(r => setTimeout(r, 50));
  }
  return { seen: [...seen], content: getComputedStyle(h1, '::after').content };
}"""

WIDTHS_DURING_COLLAPSE = """async () => {
  const nav = document.querySelector('.sidenav');
  const widths = [];
  document.querySelector('.collapse-btn').click();
  const end = performance.now() + 400;
  while (performance.now() < end) {
    await new Promise(r => requestAnimationFrame(r));
    widths.push(Math.round(nav.getBoundingClientRect().width));
  }
  return widths;
}"""


def test_a02_9_normal_motion_cursor_blinks_and_sidebar_width_animates(open_app):
    page = open_app()
    cursor = page.evaluate(CURSOR_OPACITIES)
    assert cursor["content"] == '"_"'
    assert set(cursor["seen"]) == {"0", "1"}  # it blinks
    widths = page.evaluate(WIDTHS_DURING_COLLAPSE)
    assert widths[-1] == 78
    assert any(78 < w < 250 for w in widths), widths  # in between: it animates
    chevron = page.locator(".collapse-btn svg").evaluate("el => getComputedStyle(el).transitionDuration")
    assert chevron == "0.2s"


def test_a02_10_reduced_motion_nothing_moves(open_app):
    page = open_app(reduced=True)
    cursor = page.evaluate(CURSOR_OPACITIES)
    assert cursor["seen"] == ["1"]  # the cursor stays put
    widths = page.evaluate(WIDTHS_DURING_COLLAPSE)
    assert all(w == 78 for w in widths), widths  # jumps straight to the rail
    running = page.evaluate("document.getAnimations().length")
    assert running == 0  # no CSS animation or transition anywhere, Patch included


# --- Keyboard and names (DESIGN.md §10) ---------------------------------------------------------------------------

def tab_order(page: Page, steps: int = 14) -> list[str]:
    names = []
    for _ in range(steps):
        page.keyboard.press("Tab")
        names.append(page.evaluate(
            "(() => { const a = document.activeElement; return a.getAttribute('aria-label') || a.textContent.trim() })()"))
    return names


@pytest.mark.parametrize("collapsed", [False, True])
def test_a02_11_every_control_reachable_by_keyboard_with_visible_focus(open_app, collapsed):
    page = open_app()
    if collapsed:
        page.get_by_role("button", name="Collapse the sidebar").click()
    page.locator("body").click(position={"x": 700, "y": 600})
    order = tab_order(page)
    expected = ["Dashboard", "Settings", "Dev", "Ask Patch",
                "Expand the sidebar" if collapsed else "Collapse the sidebar", "Switch to dark mode"]
    found = [n for n in expected if any(o.startswith(n) for o in order)]
    assert found == expected, order
    page.get_by_role("button", name="Settings", exact=True).focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")
    outline = page.evaluate("(() => { const s = getComputedStyle(document.activeElement); return [s.outlineStyle, s.outlineWidth] })()")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2


# --- Screenshots for gate A (#5) ----------------------------------------------------------------------------------

@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a02_12_screenshots(open_app, browser_name, scheme):
    SHOTS.mkdir(exist_ok=True)
    page = open_app(scheme=scheme, reduced=True)  # reduced motion: no frame caught mid-blink
    page.screenshot(path=SHOTS / f"a02-{browser_name}-1400-{scheme}-expanded.png", full_page=True)
    page.get_by_role("button", name="Collapse the sidebar").click()
    page.screenshot(path=SHOTS / f"a02-{browser_name}-1400-{scheme}-collapsed.png", full_page=True)
    phone = open_app(width=PHONE, scheme=scheme, reduced=True)
    phone.screenshot(path=SHOTS / f"a02-{browser_name}-400-{scheme}-tabbar.png", full_page=False)
    assert len(list(SHOTS.glob(f"a02-{browser_name}-*-{scheme}-*.png"))) == 3

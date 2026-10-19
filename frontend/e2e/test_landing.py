"""Browser check for the landing page (B42, #80). Check ids: B42.n.

Signed out (sign-in on, Clerk unreachable, test_sign_in.py's `open_signed_out`): the landing page at any address but
the sign-in form's, with no API call but /health; Sign in and Request access open the sign-in screen's two views;
Back returns. The screenshots follow the theme. A browser that was signed in waits for Clerk instead.
Sign-in off (the pairs run.sh starts): the app opens on the dashboard as before; the landing page is About.
"""
import pathlib
import re

from playwright.sync_api import Browser, Page, expect

from reduced_motion import scene, still
from test_dashboard import contrast, rgb_list
from test_shell import no_sideways_scroll, open_app, settled  # noqa: F401 (fixture)
from test_sign_in import CLERK_GIVES_UP_MS, LOCAL, _signed_in_health, open_signed_out  # noqa: F401 (fixture)

TITLE = "Security flaws in your LLM stack, tracked for you"
SHOTS = pathlib.Path(__file__).resolve().parents[1] / "src" / "landing" / "shots"
PHONE, DESKTOP = 390, 1440


def landing(open_signed_out, path="/", **kw) -> tuple[Page, list[str]]:
    return open_signed_out(path=path, heading=TITLE, **kw)


def shot_sources(page: Page) -> list[str]:
    return page.locator(".landing-shot img").evaluate_all("imgs => imgs.map(i => i.getAttribute('src'))")


def colour(page: Page, selector: str, prop: str = "color") -> tuple[int, ...]:
    return rgb_list(page.locator(selector).first.evaluate(f"el => getComputedStyle(el).{prop}"))[0]


def token(page: Page, name: str) -> tuple[int, ...]:
    """A colour token as the browser resolves it (a throwaway element painted with it)."""
    css = page.evaluate("""name => { const d = document.createElement('div'); d.style.color = `var(${name})`
        document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c }""", name)
    return rgb_list(css)[0]


# --- B42.6: signed out, the landing page at any address; nothing but /health asked ---------------------------------

def test_b42_6_a_signed_out_visitor_lands_on_the_landing_page_at_any_address(open_signed_out):
    for path in ("/", "/nope", "/cves/CVE-2025-3248", "/about"):
        page, asked = landing(open_signed_out, path)
        expect(page.get_by_text("Patch", exact=True).first).to_be_visible()
        expect(page.get_by_role("link", name="Sign in", exact=True).first).to_be_visible()
        expect(page.get_by_role("link", name="Request access").first).to_be_visible()
        expect(page.get_by_role("navigation")).to_have_count(0)  # nothing of the app
        expect(page.locator(".landing-shot img")).to_have_count(3)
        assert [p for p in asked if p != "/health"] == [], path
        assert page.url.endswith(path), path  # the address stays as typed


# --- B42.7: Sign in and Request access open the sign-in screen; Back returns ------------------------------------------

def test_b42_7_sign_in_and_request_access_lead_to_the_form_and_back(open_signed_out, ui_url):
    page, asked = landing(open_signed_out)
    page.get_by_role("link", name="Sign in", exact=True).first.click()
    expect(page.get_by_role("heading", level=1, name="Sign in to Patch")).to_be_visible()
    assert page.url == ui_url + "/sign-in"
    page.go_back()
    expect(page.get_by_role("heading", level=1, name=TITLE)).to_be_visible()

    page.get_by_role("link", name="Request access").first.click()
    expect(page.get_by_role("heading", level=1, name="Request access to Patch")).to_be_visible()
    assert page.url == ui_url + "/sign-in#/create"
    assert [p for p in asked if p != "/health"] == []


def test_b42_7_the_next_step_works_by_keyboard(open_signed_out):
    page, _ = landing(open_signed_out)
    names = []
    for _ in range(6):
        page.keyboard.press("Tab")
        names.append(page.evaluate("document.activeElement.textContent || document.activeElement.ariaLabel"))
        if names[-1] == "Sign in":
            break
    assert names[-1] == "Sign in", names
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", level=1, name="Sign in to Patch")).to_be_visible()


# --- B42.8: the screenshots match the theme, the system's and the switch's ------------------------------------------

def test_b42_8_the_screenshots_follow_the_theme(open_signed_out):
    page, _ = landing(open_signed_out, scheme="dark")
    assert all("-dark" in s for s in shot_sources(page)), shot_sources(page)
    page.get_by_role("button", name="Switch to light mode").click()
    expect(page.locator("html")).to_have_attribute("data-theme", "light")
    expect(page.locator(".landing-shot img").first).to_have_attribute("src", re.compile(r"dashboard-light"))
    assert all("-light" in s for s in shot_sources(page)), shot_sources(page)


def test_b42_8_the_screenshots_are_small_and_load(open_signed_out):
    sizes = {p.name: p.stat().st_size for p in SHOTS.glob("*.webp")}
    assert sorted(sizes) == sorted(f"{n}-{t}.webp" for n in ("dashboard", "cves", "chat") for t in ("light", "dark"))
    assert all(size < 150_000 for size in sizes.values()), sizes  # compressed: about 50 to 90 KB each
    page, _ = landing(open_signed_out)
    for img in page.locator(".landing-shot img").all():
        img.scroll_into_view_if_needed()
        expect(img).to_have_js_property("complete", True)
        assert img.evaluate("i => i.naturalWidth") == 1280
        assert img.get_attribute("alt")


# --- B42.9: light and dark, phone and desktop: fits, Patch over the edge, readable ----------------------------------

def test_b42_9_fits_a_phone_and_a_desktop_in_light_and_dark(open_signed_out):
    for width, scheme in ((PHONE, "light"), (PHONE, "dark"), (DESKTOP, "light"), (DESKTOP, "dark")):
        page, _ = landing(open_signed_out, width=width, scheme=scheme)
        settled(page.locator(".landing"))
        assert no_sideways_scroll(page), (width, scheme)
        hero = page.locator(".landing-hero").bounding_box()
        robot = page.locator(".landing-art svg.robot").bounding_box()
        assert robot["y"] < hero["y"] < robot["y"] + robot["height"], (width, scheme)  # his head over the top edge
        surface, soft = token(page, "--surface"), token(page, "--accent-soft")
        for sel in (".landing-problem", ".landing-what", ".landing-note"):
            for bg in (surface, soft):  # the hero's gradient runs from the surface to --accent-soft
                assert contrast(colour(page, sel), bg) >= 4.5, (sel, width, scheme)
        assert contrast(colour(page, ".landing-kicker"), colour(page, ".landing-kicker", "backgroundColor")) >= 4.5
        assert contrast(colour(page, ".landing-foot p"), token(page, "--bg")) >= 4.5, (width, scheme)
        for tile in page.locator(".landing-tile").all():
            assert tile.bounding_box()["x"] + tile.bounding_box()["width"] <= width


# --- B42.10: a browser that was signed in waits for Clerk, then the landing page if Clerk can't load ---------------

def test_b42_10_a_browser_signed_in_before_waits_for_clerk(browser: Browser, ui_url, api_url):
    ctx = browser.new_context()
    try:
        ctx.route(lambda url: not LOCAL.match(url), lambda route: route.abort())  # no network: Clerk can't load
        ctx.route(f"{api_url}/health", _signed_in_health)
        ctx.add_init_script("try { localStorage.setItem('signedInHere', '1') } catch {}")
        page = ctx.new_page()
        page.goto(ui_url + "/")
        expect(page.get_by_role("heading", level=1, name="Opening Patch")).to_be_visible()
        expect(page.get_by_role("heading", level=1, name=TITLE)).to_be_visible(timeout=CLERK_GIVES_UP_MS)
    finally:
        ctx.close()


# --- B51.3: after the sign-in form, the next load of "/" waits for Clerk; the landing page never flashes -----------

# Every level-1 heading the page ever shows, from its first paint: catches a landing page shown for a moment.
SEEN_HEADINGS = """window.__h1s = []
new MutationObserver(() => document.querySelectorAll('h1').forEach(h => {
  if (!window.__h1s.includes(h.textContent)) window.__h1s.push(h.textContent) })
).observe(document, { childList: true, subtree: true, characterData: true })"""


def test_b51_3_after_the_sign_in_form_a_load_of_home_waits_for_clerk(open_signed_out):
    # Clerk's redirect after signing in is a fresh load of "/" before Clerk answers; Clerk can't load here, so the
    # wait lasts until Clerk gives up, then the landing page (B42.10)
    page, _ = open_signed_out(path="/sign-in")  # the form was shown (its loading line: Clerk is unreachable)
    page.context.add_init_script(SEEN_HEADINGS)
    page.goto(page.url.removesuffix("/sign-in") + "/")
    expect(page.get_by_role("heading", level=1, name="Opening Patch")).to_be_visible()
    assert TITLE not in page.evaluate("window.__h1s"), page.evaluate("window.__h1s")
    expect(page.get_by_role("heading", level=1, name=TITLE)).to_be_visible(timeout=CLERK_GIVES_UP_MS)
    assert page.evaluate("window.__h1s")[0] == "Opening Patch"


# --- B42.11: sign-in off: the dashboard as before, the landing page as About ----------------------------------------

def test_b42_11_with_sign_in_off_the_app_opens_on_the_dashboard_and_about_is_in_the_nav(open_app):  # noqa: F811
    page = open_app()
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()
    page.get_by_role("navigation", name="Pages").get_by_role("button", name="About").click()
    expect(page.get_by_role("heading", level=1, name="About")).to_be_visible()
    assert page.url.endswith("/about")
    expect(page.get_by_role("button", name="About")).to_have_attribute("aria-current", "page")
    expect(page.get_by_role("heading", level=2, name=TITLE)).to_be_visible()
    expect(page.get_by_role("link", name="Sign in", exact=True)).to_have_count(0)  # already in
    page.get_by_role("link", name="Open the dashboard").first.click()
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()


def test_b42_11_about_fits_a_phone_in_the_app_with_the_tab_bar(open_app):  # noqa: F811
    for width, scheme in ((PHONE, "dark"), (DESKTOP, "light")):
        page = open_app(width=width, scheme=scheme, query="/about")
        expect(page.get_by_role("heading", level=1, name="About")).to_be_visible()
        settled(page.locator(".landing"))
        assert no_sideways_scroll(page), width
        bar = page.locator(".sidenav").bounding_box()
        about = page.locator(".sidenav").get_by_role("button", name="About").bounding_box()
        assert about["x"] >= bar["x"] and about["x"] + about["width"] <= bar["x"] + bar["width"] + 0.5, width
        assert all("-" + scheme in s for s in shot_sources(page)), width


# --- Reduced motion: this file's scene in the shared check (reduced_motion.py) -------------------------------------

@scene
def b42_12_landing_page(fx):
    page, _ = fx("open_signed_out")(reduced=True, path="/", heading=TITLE)
    page.locator(".shot-frame").first.hover()
    still(page, "the landing page")

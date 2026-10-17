"""Browser check (seam 3) for the Dev panel: model switch, local-model discovery, search tuning, the playground and
the embedding map. Check ids: A11.n, from ticket #13.

Runs in Firefox and Chromium against run.sh's throwaway servers (FakeLLM, hash embedder). The "local model server"
is a tiny fake started by this file on 127.0.0.1: it lists two models and is never asked to answer. Every test puts
the dev choices back to the defaults, since all tests share one backend. Expected looks come from DESIGN.md §5.3,
§5.5–5.7, not from the CSS.
"""
import json
import pathlib
import threading
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from playwright.sync_api import Browser, Page, expect
from reduced_motion import scene, still

SHOTS = pathlib.Path(__file__).parent / "screenshots"
PHONE, DESKTOP = 400, 1400
Q5 = "How do I protect a RAG app from indirect prompt injection?"


def api(api_url: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


@pytest.fixture(autouse=True)
def default_dev_settings(api_url: str):
    yield
    defaults = api(api_url, "/dev/settings")["defaults"]
    api(api_url, "/dev/settings", "PUT", defaults)


@pytest.fixture(scope="module")
def local_models_server():
    """A fake OpenAI-compatible server on this machine: GET /v1/models lists two models."""
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"object": "list", "data": [{"id": "qwen3:8b"}, {"id": "llama3.2"}]}).encode()
            self.send_response(200 if self.path == "/v1/models" else 404)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/v1"
    server.shutdown()


@pytest.fixture
def dev_page(browser: Browser, ui_url: str):
    contexts = []

    def _open(width=DESKTOP, scheme="light", reduced=False, setup=None) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                  reduced_motion="reduce" if reduced else "no-preference")
        contexts.append(ctx)
        if setup:
            setup(ctx)  # routes that must be in place before the first request
        page = ctx.new_page()
        page.goto(ui_url)
        page.get_by_role("button", name="Dev", exact=True).click()
        expect(page.get_by_role("heading", name="Model", exact=True)).to_be_visible()
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def css_var(page: Page, name: str) -> str:
    return page.evaluate(f"getComputedStyle(document.documentElement).getPropertyValue('{name}').trim()")


def style(locator, prop: str) -> str:
    return locator.evaluate(f"el => getComputedStyle(el).{prop}")


def resolved(page: Page, value: str, prop: str = "backgroundColor") -> str:
    return page.evaluate(f"""(() => {{ const d = document.createElement('div'); d.style.cssText = 'position:absolute';
        d.style.{prop} = {value!r}; document.body.append(d); const v = getComputedStyle(d).{prop}; d.remove(); return v }})()""")


def run_search(page: Page, query: str = Q5):
    page.get_by_label("Search query").fill(query)
    page.get_by_role("button", name="Run search").click()
    expect(page.get_by_role("region", name="Final sources")).to_be_visible()


def save(page: Page):
    page.get_by_role("button", name="Save changes").click()
    expect(page.locator(".save-bar output")).to_have_text("✓ Changes saved")


# --- A11.1: model switch and local-model discovery ------------------------------------------------------------------

def test_a11_1_fakellm_by_default_and_openrouter_needs_a_key(dev_page):
    page = dev_page()
    expect(page.get_by_role("radio", name="FakeLLM")).to_be_checked()
    expect(page.get_by_role("radio", name="OpenRouter")).to_be_disabled()  # run.sh starts the backend with no key
    expect(page.get_by_text("needs OPENROUTER_API_KEY in backend/.env")).to_be_visible()
    expect(page.get_by_text("Scripted answers: model and temperature don't apply.")).to_be_visible()


def test_a11_1_find_a_local_servers_models_and_switch_with_no_restart(dev_page, local_models_server):
    page = dev_page()
    page.get_by_role("radio", name="Local model").check()
    expect(page.get_by_role("button", name="Ollama", exact=True)).to_have_attribute("aria-pressed", "true")
    page.get_by_role("button", name="LM Studio").click()
    expect(page.get_by_label("Server URL")).to_have_value("http://localhost:1234/v1")
    page.get_by_label("Server URL").fill(local_models_server)
    page.get_by_role("button", name="Find models").click()
    expect(page.get_by_text("Found 2 models.")).to_be_visible()
    page.get_by_label("Model name").select_option("qwen3:8b")
    expect(page.get_by_label("Temperature")).to_be_visible()
    save(page)
    expect(page.locator(".side-model")).to_have_text("Local · qwen3:8b")  # the snapshot card, with no restart
    page.get_by_role("radio", name="FakeLLM").check()
    save(page)
    expect(page.locator(".side-model")).to_have_text("FakeLLM (scripted)")


def test_a11_1_find_models_says_plainly_when_nothing_is_running(dev_page):
    page = dev_page()
    page.get_by_role("radio", name="Local model").check()
    page.get_by_label("Server URL").fill("http://127.0.0.1:9/v1")  # the discard port: nothing listens
    page.get_by_role("button", name="Find models").click()
    expect(page.get_by_role("alert")).to_contain_text("Nothing answered at http://127.0.0.1:9/v1")


def test_a11_1_a_url_off_this_machine_is_refused(dev_page):
    page = dev_page()
    page.get_by_role("radio", name="Local model").check()
    page.get_by_label("Server URL").fill("http://169.254.169.254/latest")
    page.get_by_role("button", name="Find models").click()
    expect(page.get_by_role("alert")).to_contain_text("must be on this machine")
    page.get_by_label("Model name").fill("qwen3")
    page.get_by_role("button", name="Save changes").click()
    expect(page.locator(".save-bar output")).to_contain_text("must be on this machine")


# --- A11.2: sliders and switches, saved -----------------------------------------------------------------------------

def test_a11_2_sliders_and_switches_save_and_survive_a_reload(dev_page):
    page = dev_page()
    for label, value in (("Sources per search", "5"), ("Results per query", "10"), ("Chunks per document", "2"),
                         ("RRF constant k", "60"), ("Keyword vs vector", "0.5"), ("Max agent steps", "6")):
        expect(page.get_by_label(label)).to_have_value(value)
    page.get_by_label("Sources per search").fill("3")
    # Sliders move by keyboard. #67: Firefox on CI lost a keypress sent right after focus(): wait until the slider
    # has the focus, press on the slider itself, and wait for the new value before the next field takes the focus.
    rrf = page.get_by_label("RRF constant k")
    rrf.focus()
    expect(rrf).to_be_focused()
    rrf.press("ArrowRight")
    expect(rrf).to_have_value("61")
    page.get_by_label("Keyword vs vector").fill("0.75")
    page.get_by_label("Multi-query rewrites").uncheck()
    page.get_by_label("Self-query filters").uncheck()
    expect(page.locator(".slider-row", has=page.get_by_label("RRF constant k")).locator("output")).to_have_text("61")
    expect(page.locator(".slider-row", has=page.get_by_label("Keyword vs vector")).locator("output")).to_have_text("0.75")
    expect(page.get_by_role("note")).to_contain_text("use the saved settings")
    save(page)
    page.reload()
    page.get_by_role("button", name="Dev", exact=True).click()
    expect(page.get_by_label("Sources per search")).to_have_value("3")
    expect(page.get_by_label("RRF constant k")).to_have_value("61")
    expect(page.get_by_label("Multi-query rewrites")).not_to_be_checked()
    page.get_by_role("button", name="Reset to the defaults").click()
    expect(page.get_by_label("Sources per search")).to_have_value("5")
    expect(page.get_by_label("Self-query filters")).to_be_checked()
    page.get_by_role("button", name="Discard").click()
    expect(page.get_by_label("Sources per search")).to_have_value("3")


def test_a11_2_filters_off_are_shown_as_dropped(dev_page):
    page = dev_page()
    page.get_by_label("Self-query filters").uncheck()
    save(page)
    run_search(page, "Which critical Langflow vulnerabilities were published in 2026?")
    expect(page.locator(".play-plan")).to_contain_text("product=langflow (filters off)")


# --- A11.3: the playground ------------------------------------------------------------------------------------------

def test_a11_3_playground_shows_plan_each_list_fused_and_final(dev_page, api_url):
    page = dev_page()
    run_search(page)
    expected = api(api_url, "/dev/search", "POST", {"query": Q5})
    plan = page.locator(".play-plan")
    expect(plan).to_contain_text(expected["query"]["semantic_query"])
    for name in ("Semantic query", "Rewrite 1", "Rewrite 2", "Rewrite 3"):
        col = page.get_by_role("region", name=name, exact=True)
        expect(col.get_by_role("heading", name="Vector")).to_be_visible()
        expect(col.get_by_role("heading", name="Keyword (BM25)")).to_be_visible()
    final = page.get_by_role("region", name="Final sources")
    expect(final.get_by_role("listitem")).to_have_count(len(expected["final"]))
    expect(final).to_contain_text(expected["final"][0]["title"])
    expect(page.get_by_role("region", name="Fused").get_by_role("listitem")).to_have_count(len(expected["fused"]))


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a11_3_playground_columns_as_designed(dev_page, scheme):
    page = dev_page(scheme=scheme)
    run_search(page)
    nested = resolved(page, css_var(page, "--nested-fill"))
    accent = resolved(page, css_var(page, "--accent"), "color")
    ok = resolved(page, css_var(page, "--ok"), "color")
    for col in page.locator(".play-col").all():
        assert style(col, "borderTopLeftRadius") == "18px" and style(col, "backgroundColor") == nested
    fused, final = page.locator(".play-col.fused"), page.locator(".play-col.final")
    assert style(fused, "boxShadow") == f"{accent} 0px 0px 0px 2px inset"
    assert style(final, "boxShadow") == f"{ok} 0px 0px 0px 2px inset"
    assert style(final.get_by_role("heading", name="Final sources"), "color") == ok
    assert style(page.locator(".play-col").first.locator("h3"), "color") == accent
    assert style(page.locator(".play-col h3").first, "fontFamily").startswith('Fredoka')
    assert style(page.get_by_label("Search query"), "borderTopLeftRadius") == "999px"  # a full pill
    assert style(page.locator(".play-plan"), "backgroundColor") == nested


# --- A11.4: the embedding map ---------------------------------------------------------------------------------------

def map_points(page: Page) -> int:
    return page.locator(".emap .pts > g").count()


@pytest.mark.parametrize("scheme,dim", [("light", "0.4"), ("dark", "0.6")])
def test_a11_4_map_groups_shapes_colours_and_dimming(dev_page, api_url, scheme, dim):
    page = dev_page(scheme=scheme)
    info = api(api_url, "/dev/info")
    expect(page.locator(".emap-box svg")).to_be_visible()
    assert map_points(page) == info["chunks"]
    for group, shape, token in (("owasp", "circle", "--cat-1"), ("atlas", "rect", "--cat-2"), ("cve", "path", "--cat-3")):
        g = page.locator(f".emap .pts.grp-{group}")
        assert style(g, "fill") == resolved(page, css_var(page, token), "color")
        assert g.locator(f"> g > {shape}").count() == g.locator("> g").count() > 0
    assert style(page.locator(".emap .pts > g > *").first, "fillOpacity") == "0.9"
    assert style(page.locator(".emap-box"), "borderTopLeftRadius") == "18px"
    assert style(page.locator(".emap-box"), "backgroundColor") == resolved(page, css_var(page, "--nested-fill"))
    run_search(page)
    assert style(page.locator(".emap .dimmed"), "opacity") == dim
    expected = api(api_url, "/dev/search", "POST", {"query": Q5})
    expect(page.locator(".emap .qmark")).to_have_count(len(expected["map"]))  # query and rewrites as ✕
    expect(page.locator(".emap .qmark.main")).to_have_count(1)
    expect(page.locator(".emap .hit")).to_have_count(len(expected["final"]))
    expect(page.locator(".emap .emap-link")).to_have_count(len(expected["final"]))  # lines to the final sources
    assert style(page.locator(".emap .emap-link").first, "strokeDasharray") in ("3px, 3px", "3, 3", "3px 3px")


def test_a11_4_map_group_toggles_zoom_and_table(dev_page, api_url):
    page = dev_page()
    info = api(api_url, "/dev/info")
    total = info["chunks"]
    cves = info["by_doc_type"]["cve"]
    toggle = page.get_by_role("main").get_by_role("button", name="CVEs")  # the sidebar has a CVEs page too (A04b)
    expect(toggle).to_have_attribute("aria-pressed", "true")
    expect(toggle).to_contain_text(str(cves))
    toggle.click()
    expect(toggle).to_have_attribute("aria-pressed", "false")
    assert map_points(page) == total - cves
    toggle.click()
    run_search(page)
    expect(page.get_by_role("button", name="Show all")).to_be_visible()  # zoomed to the query after a search
    page.get_by_role("button", name="Show all").click()
    expect(page.get_by_role("button", name="Zoom to query")).to_be_visible()
    page.locator(".emap").get_by_text("Show as table").click()
    table = page.locator(".emap table.data").first
    expect(table).to_contain_text("CVEs")
    expect(table).to_contain_text(str(cves))
    expect(page.locator(".emap table.data").nth(1)).to_contain_text("Semantic query")


# --- A11.6: save bar and controls as designed -----------------------------------------------------------------------

def patch_button_box(width: int, height: int = 900) -> dict:
    bottom = 80 if width <= 800 else 20
    return {"x": width - 20 - 84, "y": height - bottom - 66, "width": 84, "height": 66}


def overlaps(a: dict, b: dict) -> bool:
    return (a["x"] < b["x"] + b["width"] and b["x"] < a["x"] + a["width"]
            and a["y"] < b["y"] + b["height"] and b["y"] < a["y"] + a["height"])


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_a11_6_save_bar_floats_clear_of_patch(dev_page, width):
    page = dev_page(width=width)
    bar = page.locator(".save-bar")
    assert style(bar, "position") == "sticky" and style(bar, "borderTopLeftRadius") == "20px"
    page.get_by_label("Sources per search").fill("7")
    page.evaluate("window.scrollTo(0, 0)")
    box = bar.bounding_box()
    assert box and box["y"] + box["height"] <= 900
    for name in ("Discard", "Save changes"):
        button = page.get_by_role("button", name=name).bounding_box()
        assert button and not overlaps(button, patch_button_box(width)), name
    expect(bar).to_contain_text("Unsaved changes")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a11_6_sliders_buttons_and_cards_on_brand(dev_page, scheme):
    page = dev_page(scheme=scheme)
    slider = page.get_by_label("Sources per search")
    page.get_by_label("Max agent steps").focus()
    page.keyboard.press("Tab")  # focus by keyboard: the focus ring shows
    expect(slider).to_be_focused()
    assert style(slider, "outlineStyle") == "solid" and style(slider, "outlineWidth") == "2px"
    assert style(slider, "outlineOffset") == "4px"
    assert style(slider, "outlineColor") == resolved(page, css_var(page, "--accent"), "color")
    assert style(slider, "appearance") == "none"
    for card in page.locator("section.card").all():
        assert style(card, "backgroundColor") == resolved(page, css_var(page, "--surface"))
        assert style(card, "borderTopLeftRadius") == "26px"
    run = page.get_by_role("button", name="Run search")
    assert style(run, "borderTopLeftRadius") == "999px"
    assert "gradient" in style(run, "backgroundImage")  # primary: the purple gradient


# --- A11.7: reduced motion ------------------------------------------------------------------------------------------

# Reduced motion: scene a11_7 at the end of this file, in the shared check (reduced_motion.py).


def test_a11_7_nothing_on_the_dev_page_animates_even_with_normal_motion(dev_page):
    page = dev_page()
    run_search(page)
    names = page.evaluate("""document.getAnimations().map(a => a.target && a.target.closest
        && a.target.closest('main') ? (a.animationName || a.transitionProperty) : null).filter(Boolean)""")
    assert names == []


# --- A11.8: light and dark, phone and desktop -----------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a11_8_works_in_both_themes_at_both_widths(dev_page, browser_name, width, scheme):
    page = dev_page(width=width, scheme=scheme, reduced=True)
    run_search(page)
    wide = page.evaluate("""[...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right >
        document.documentElement.clientWidth + 1).map(e => e.tagName + '.' + e.className).slice(0, 5)""")
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), wide
    cards = page.locator(".settings-grid > section.card")
    one_column = len({round(c.bounding_box()["x"]) for c in cards.all()}) == 1
    assert one_column == (width == PHONE)
    if width == PHONE:  # ≤ 520px: the slider's label sits above it
        row = page.locator(".slider-row", has=page.get_by_label("Sources per search"))
        label, slider = row.locator("label").bounding_box(), page.get_by_label("Sources per search").bounding_box()
        assert label and slider and label["y"] + label["height"] <= slider["y"] + 1
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a11-{browser_name}-{width}-{scheme}-dev.png", full_page=True)


# --- A11.9: keyboard and names --------------------------------------------------------------------------------------

def test_a11_9_every_control_reachable_by_keyboard_with_visible_focus(dev_page):
    page = dev_page()
    page.get_by_role("radio", name="Local model").check()
    page.get_by_role("radio", name="Local model").focus()
    seen = []
    for _ in range(45):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement === document.body"):
            break  # past the last control: focus left the page
        seen.append(page.evaluate("""(() => { const a = document.activeElement;
            const label = a.labels && a.labels[0] ? a.labels[0].textContent : '';
            return (a.getAttribute('aria-label') || label || a.textContent || '').trim() })()"""))
        outline = page.evaluate("""(() => { const s = getComputedStyle(document.activeElement);
            return [s.outlineStyle, s.outlineWidth] })()""")
        assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2, seen[-1]
    text = " | ".join(seen)
    for name in ("Server URL", "Ollama", "LM Studio", "Find models", "Max agent steps", "Sources per search",
                 "Keyword vs vector", "Multi-query rewrites", "Self-query filters", "Reset to the defaults",
                 "Search query", "Run search"):
        assert name in text, (name, seen)


def test_a11_9_buttons_have_accessible_names(dev_page):
    page = dev_page()
    run_search(page)
    for name in ("Run search", "Discard", "Save changes", "Reset to the defaults", "OWASP pages", "MITRE ATLAS", "CVEs",
                 "Show all"):
        expect(page.get_by_role("main").get_by_role("button", name=name)).to_have_count(1)
    unnamed = page.evaluate("""[...document.querySelectorAll('main button, main input, main select')].filter(b =>
        !(b.getAttribute('aria-label') || (b.labels && b.labels.length && b.labels[0].textContent) || b.textContent || '')
        .trim()).length""")
    assert unnamed == 0
    assert page.locator(".emap-box svg").get_attribute("aria-label").startswith("Map of ")


# --- A11.10: the OpenRouter model as a dropdown of the models this key may use ---------------------------------------
# The throwaway backend has no key, so OpenRouter can't be picked or saved there, and the real OpenRouter must never
# be asked. These checks route /dev/settings (a key, OpenRouter saved) and /dev/openrouter-models in the browser; the
# backend's own tests check the route and the save's validation.

DEFAULT = "anthropic/claude-haiku-5.5"
LISTED = [
    {"id": "google/gemini-flash", "name": "Google: Gemini Flash", "input_per_m": 0.1, "output_per_m": 0.4,
     "context_length": 1048576, "check": None},
    {"id": "openai/gpt-5-mini", "name": "OpenAI: GPT-5 mini", "input_per_m": 0.25, "output_per_m": 2.0,
     "context_length": 400000, "check": {"passed": 9, "total": 14, "run": "r2"}},
    {"id": DEFAULT, "name": "Anthropic: Claude Haiku 5.5", "input_per_m": 1.0, "output_per_m": 5.0,
     "context_length": 200000, "check": {"passed": 12, "total": 14, "run": "r1"}},
]


class OpenRouterRoutes:
    """The browser's view of a backend with a key: OpenRouter saved with `saved`, the list given, saves recorded.
    With hold=True the list waits until release(), to see the loading state."""

    def __init__(self, api_url: str, saved: str = DEFAULT, models=None, reason=None, hold=False):
        self.api_url, self.saved, self.hold = api_url, saved, hold
        self.list = {"models": LISTED if models is None else models, "reason": reason}
        self.puts: list[dict] = []
        self.held = []

    def __call__(self, ctx):
        ctx.route(f"{self.api_url}/dev/settings", self._settings)
        ctx.route(f"{self.api_url}/dev/openrouter-models", self._models)

    def _settings(self, route):
        if route.request.method == "PUT":
            body = route.request.post_data_json
            self.puts.append(body)
            route.fulfill(json={"settings": body})
            return
        reply = route.fetch().json()
        reply["settings"] |= {"provider": "openrouter", "openrouter_model": self.saved}
        route.fulfill(json=reply | {"openrouter_key": True})

    def _models(self, route):
        if self.hold:
            self.held.append(route)
        else:
            route.fulfill(json=self.list)

    def release(self):
        for route in self.held:
            route.fulfill(json=self.list)


def saved_body(page: Page, routes: OpenRouterRoutes) -> dict:
    save(page)
    return routes.puts[-1]


def test_a11_10_the_select_lists_the_models_with_prices_and_scores_and_saves_one(dev_page, api_url):
    routes = OpenRouterRoutes(api_url, hold=True)
    page = dev_page(setup=routes)
    select = page.get_by_label("OpenRouter model")
    expect(select).to_be_disabled()  # loading
    expect(select).to_contain_text("Loading the models")
    routes.release()
    expect(select).to_be_enabled()
    expect(select).to_have_value(DEFAULT)
    texts = [t.strip() for t in select.locator("option").all_inner_texts()]
    assert texts == [
        "google/gemini-flash · $0.10 / $0.40 per M tokens",
        "openai/gpt-5-mini · $0.25 / $2.00 per M tokens · 9/14 in the model check",
        f"{DEFAULT} (default) · $1.00 / $5.00 per M tokens · 12/14 in the model check",
        "Other…",
    ]
    expect(page.get_by_label("Model id")).to_have_count(0)  # the text field is only for Other
    picked = page.locator(".or-picked")  # the picked model in full: a phone's closed select cuts the option
    expect(picked).to_have_text("Anthropic: Claude Haiku 5.5 · $1.00 / $5.00 per M tokens · 12/14 in the model check"
                                " · 200K context")
    assert select.get_attribute("aria-describedby") == picked.get_attribute("id")
    select.select_option("openai/gpt-5-mini")
    expect(picked).to_contain_text("OpenAI: GPT-5 mini · $0.25 / $2.00 per M tokens · 9/14 in the model check")
    assert saved_body(page, routes)["openrouter_model"] == "openai/gpt-5-mini"
    expect(select).to_have_value("openai/gpt-5-mini")


def test_a11_10_other_shows_the_text_field_and_saves_a_custom_id(dev_page, api_url):
    routes = OpenRouterRoutes(api_url)
    page = dev_page(setup=routes)
    page.get_by_label("OpenRouter model").select_option(label="Other…")
    field = page.get_by_label("Model id")
    expect(field).to_be_visible()
    expect(field).to_be_focused()  # straight to typing
    field.fill("meta-llama/llama-4-scout:free")
    assert saved_body(page, routes)["openrouter_model"] == "meta-llama/llama-4-scout:free"
    expect(page.get_by_label("OpenRouter model")).to_have_value("other")  # still Other after the save


def test_a11_10_a_saved_model_not_in_the_list_shows_as_other_with_its_value(dev_page, api_url):
    routes = OpenRouterRoutes(api_url, saved="mistralai/mistral-small")
    page = dev_page(setup=routes)
    expect(page.get_by_label("OpenRouter model")).to_have_value("other")
    expect(page.get_by_label("Model id")).to_have_value("mistralai/mistral-small")
    expect(page.get_by_text("Not in the list for this key")).to_be_visible()
    expect(page.locator(".save-bar")).to_contain_text("All changes saved")  # nothing changed silently


def test_a11_10_an_empty_list_falls_back_to_the_text_field_with_the_reason(dev_page, api_url):
    routes = OpenRouterRoutes(api_url, models=[], reason="Can't reach OpenRouter (ConnectError).")
    page = dev_page(setup=routes)
    field = page.get_by_label("OpenRouter model")
    expect(field).to_have_value(DEFAULT)
    assert field.evaluate("el => el.tagName") == "INPUT"
    expect(page.get_by_role("note").filter(has_text="Can't reach OpenRouter")).to_be_visible()
    field.fill("openai/gpt-5-mini")
    assert saved_body(page, routes)["openrouter_model"] == "openai/gpt-5-mini"


def test_a11_10_the_select_and_other_field_by_keyboard(dev_page, api_url):
    routes = OpenRouterRoutes(api_url)
    page = dev_page(setup=routes)
    select = page.get_by_label("OpenRouter model")
    expect(select).to_be_enabled()
    page.get_by_role("radio", name="OpenRouter").focus()
    page.keyboard.press("Tab")
    expect(select).to_be_focused()
    assert style(select, "outlineStyle") != "none"
    select.select_option("other")  # a keyboard pick fires the same change
    expect(page.get_by_label("Model id")).to_be_focused()


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a11_10_the_dropdown_in_both_themes_at_both_widths(dev_page, api_url, browser_name, width, scheme):
    routes = OpenRouterRoutes(api_url, saved="mistralai/mistral-small")
    page = dev_page(width=width, scheme=scheme, reduced=True, setup=routes)
    select = page.get_by_label("OpenRouter model")
    expect(page.get_by_label("Model id")).to_be_visible()
    assert style(select, "borderTopLeftRadius") == "14px"  # DESIGN.md §5.3: selects 14px
    card = page.locator("section.card", has=select).bounding_box()
    box = select.bounding_box()
    assert card and box and box["x"] + box["width"] <= card["x"] + card["width"]  # the long options don't widen it
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")
    SHOTS.mkdir(exist_ok=True)
    shot = SHOTS / f"a11-10-{browser_name}-{width}-{scheme}-openrouter"
    page.locator("section.card", has=select).screenshot(path=f"{shot}-other.png")
    select.select_option(DEFAULT)  # the longest option: cut in the closed select, never wider than the card
    expect(page.get_by_label("Model id")).to_have_count(0)
    box = select.bounding_box()
    assert box and box["x"] + box["width"] <= card["x"] + card["width"]
    page.locator("section.card", has=select).screenshot(path=f"{shot}-listed.png")


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def a11_7_dev_page(fx):
    page = fx("dev_page")(reduced=True)
    page.get_by_label("Sources per search").fill("4")
    run_search(page)
    page.get_by_role("button", name="Show all").click()
    page.locator(".emap .hit").first.hover(force=True)
    page.get_by_role("button", name="Discard").hover()
    still(page, "the dev page")

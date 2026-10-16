"""Browser check (seam 3) for explain levels: Settings, the chat header's switch, "Explain it". Check ids: A19.n, #21.

Runs in Firefox and Chromium against run.sh's throwaway servers, on FakeLLM. Each test starts from the defaults
(reset through the API). Expected values come from the ticket and docs/design/DESIGN.md (§5.3, §6.2, §7, §10).
"""
import json
import urllib.request

import pytest
from playwright.sync_api import Locator, Page, expect

from test_chat import ask, open_chat, window
from test_shell import DESKTOP, PHONE, SHOTS, contrast, no_sideways_scroll, open_app  # noqa: F401 (fixture)
from reduced_motion import scene, still

Q12 = "What is prompt injection and how do I prevent it?"
ALERT_CVE = "CVE-2025-3248"
LABEL = {"simple": "Simple", "normal": "Normal", "deep_dive": "Deep dive"}


def api(api_url: str, path: str, body: dict | None = None, method: str = "GET") -> dict:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(api_url + path, data=data, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


@pytest.fixture(autouse=True)
def fresh_state(api_url):
    api(api_url, "/state/reset", {"confirm": "reset"}, "POST")
    yield
    api(api_url, "/state/reset", {"confirm": "reset"}, "POST")


def save_level(api_url: str, level: str) -> None:
    body = api(api_url, "/settings")["settings"] | {"explain_level": level}
    api(api_url, "/settings", body, "PUT")


def switch(page: Page) -> Locator:
    return window(page).get_by_role("group", name="Explain level")


def settings_group(page: Page) -> Locator:
    return page.locator("main").get_by_role("group", name="Explain level")


def chat_bodies(page: Page) -> list[dict]:
    """Every /chat request body the page sends, as it sends them."""
    seen: list[dict] = []
    page.on("request", lambda r: seen.append(json.loads(r.post_data or "{}")) if r.url.endswith("/chat") else None)
    return seen


def level_note(answer: Locator) -> Locator:
    return answer.locator(".level-used")


# --- A19.1: the saved level on the Settings page -----------------------------------------------------------------

def test_a19_1_settings_saves_the_explain_level_default_normal(open_app, api_url):
    page = open_app()
    page.get_by_role("button", name="Settings", exact=True).click()
    card = settings_group(page)
    expect(card.get_by_role("radio", name="Normal")).to_be_checked()
    card.get_by_role("radio", name="Deep dive").check()
    page.get_by_role("button", name="Save changes").click()
    expect(page.get_by_text("Changes saved")).to_be_visible()
    assert api(api_url, "/settings")["settings"]["explain_level"] == "deep_dive"
    page.reload()
    page.get_by_role("button", name="Settings", exact=True).click()
    expect(settings_group(page).get_by_role("radio", name="Deep dive")).to_be_checked()


# --- A19.2: the chat header's switch: the next question only; the reply says which level -------------------------

def test_a19_2_switch_shows_the_saved_level_and_applies_another_to_the_next_question_only(open_app, api_url):
    save_level(api_url, "simple")
    page = open_app()
    bodies = chat_bodies(page)
    open_chat(page)
    expect(switch(page).get_by_role("radio", name="Simple")).to_be_checked()
    switch(page).get_by_role("radio", name="Deep dive").check()
    expect(switch(page)).to_contain_text("next question")
    first = ask(page, Q12)
    assert bodies[-1]["explain_level"] == "deep_dive"
    expect(level_note(first)).to_contain_text("Deep dive")
    expect(switch(page).get_by_role("radio", name="Simple")).to_be_checked()  # back to the saved level
    second = ask(page, Q12)
    assert bodies[-1].get("explain_level") is None  # no override: the backend uses the saved level
    expect(level_note(second)).to_contain_text("Simple")
    assert first.locator(".answer-text").inner_text() != second.locator(".answer-text").inner_text()
    assert api(api_url, "/settings")["settings"]["explain_level"] == "simple"  # the switch never saves


def test_a19_2_the_switch_follows_a_level_saved_on_the_settings_page(open_app):
    page = open_app()
    open_chat(page)
    window(page).get_by_role("button", name="Make larger").click()
    window(page).get_by_role("button", name="Pin: dock the chat beside the page").click()
    expect(switch(page).get_by_role("radio", name="Normal")).to_be_checked()
    page.get_by_role("button", name="Settings", exact=True).click()
    settings_group(page).get_by_role("radio", name="Simple").check()
    page.get_by_role("button", name="Save changes").click()
    expect(switch(page).get_by_role("radio", name="Simple")).to_be_checked()


# --- A19.4: "Explain it" on the alert banner uses the saved level -----------------------------------------------

def test_a19_4_explain_it_uses_the_saved_level(open_app, api_url):
    save_level(api_url, "deep_dive")
    page = open_app(query=f"#cve={ALERT_CVE}")
    bodies = chat_bodies(page)
    page.get_by_role("region", name="Alert", exact=True).get_by_role("button", name="Explain it").click()
    answer = window(page).locator(".message.assistant").first
    expect(answer).to_be_visible(timeout=10_000)
    assert bodies[-1].get("explain_level") is None
    expect(level_note(answer)).to_contain_text("Deep dive")


def test_a19_4_explain_it_ignores_a_level_picked_for_the_next_question(open_app, api_url):
    save_level(api_url, "deep_dive")
    page = open_app()
    open_chat(page)
    switch(page).get_by_role("radio", name="Simple").check()
    page.evaluate(f"location.hash = 'cve={ALERT_CVE}'")
    page.get_by_role("region", name="Alert", exact=True).get_by_role("button", name="Explain it").click()
    answer = window(page).locator(".message.assistant").first
    expect(answer).to_be_visible(timeout=10_000)
    expect(level_note(answer)).to_contain_text("Deep dive")


# --- A19.6: reduced motion: nothing in this ticket moves ---------------------------------------------------------

# Reduced motion: scene a19_6 at the end of this file, in the shared check (reduced_motion.py).


# --- A19.7: light and dark, phone and desktop ---------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a19_7_switch_and_level_note_work_in_light_and_dark_at_phone_and_desktop(open_app, browser_name, width, scheme):
    page = open_app(width=width, scheme=scheme, reduced=True)
    chat = open_chat(page)
    group = switch(page)
    g, c = group.bounding_box(), chat.bounding_box()
    assert g and c and g["x"] >= c["x"] and g["x"] + g["width"] <= c["x"] + c["width"]  # inside the window
    picked = group.locator("label", has=page.get_by_role("radio", name="Deep dive"))
    picked.click()
    for label in group.locator("label").all():
        fg = label.evaluate("el => getComputedStyle(el).color")
        bg = label.evaluate("el => getComputedStyle(el).backgroundColor")
        if bg in ("rgba(0, 0, 0, 0)", "transparent"):
            bg = chat.evaluate("el => getComputedStyle(el).backgroundColor")
        assert contrast(fg, bg) >= 4.5, label.inner_text()
    assert picked.evaluate("el => getComputedStyle(el).borderTopColor") != \
        group.locator("label", has=page.get_by_role("radio", name="Simple")).evaluate(
            "el => getComputedStyle(el).borderTopColor")  # the picked level stands out, not only by colour of text
    ask(page, Q12)
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a19-{browser_name}-{width}-{scheme}-chat.png")
    chat.get_by_role("button", name="Close the chat").click()
    page.get_by_role("button", name="Settings", exact=True).click()
    settings_group(page).scroll_into_view_if_needed()
    assert no_sideways_scroll(page)
    page.screenshot(path=SHOTS / f"a19-{browser_name}-{width}-{scheme}-settings.png")


# --- A19.8: keyboard and names ------------------------------------------------------------------------------------

def test_a19_8_switch_by_keyboard_with_visible_focus_and_names(open_app):
    page = open_app()
    page.keyboard.press("Control+k")
    expect(window(page).get_by_role("textbox", name="Message")).to_be_focused()
    for _ in range(8):  # back from the message box to the switch
        page.keyboard.press("Shift+Tab")
        if page.evaluate("document.activeElement.type") == "radio":
            break
    focused = page.evaluate("document.activeElement.labels[0].textContent.trim()")
    assert focused == "Normal"
    label = switch(page).locator("label", has=page.get_by_role("radio", name="Normal"))
    ring = label.evaluate("el => [getComputedStyle(el).outlineStyle, getComputedStyle(el).outlineWidth]")
    assert ring[0] != "none" and float(ring[1].rstrip("px")) >= 2  # visible focus on the pill
    page.keyboard.press("ArrowRight")  # radios: arrows move and pick
    expect(switch(page).get_by_role("radio", name="Deep dive")).to_be_checked()
    expect(switch(page).get_by_role("radio", name="Deep dive")).to_be_focused()
    for name in LABEL.values():
        expect(switch(page).get_by_role("radio", name=name, exact=True)).to_have_count(1)


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def a19_6_explain_levels(fx):
    page = fx("open_app")(reduced=True)
    open_chat(page)
    for name in ("Simple", "Deep dive", "Normal"):
        switch(page).get_by_role("radio", name=name).check()
        still(page, f"the switch at {name}")
    page.get_by_role("button", name="Settings", exact=True).click()
    settings_group(page).get_by_role("radio", name="Simple").check()
    still(page, "the saved level on Settings")

"""Browser check (seam 3) for the chat on FakeLLM: the bubble and Patch. Check ids: A06.n, from ticket #8.

Runs in Firefox and Chromium (run.sh). Expected values come from docs/design/DESIGN.md §6 and §8, not from the CSS.
"""
import re
import time

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from test_shell import DESKTOP, PHONE, SHOTS, contrast, css_var, no_sideways_scroll, open_app  # noqa: F401 (fixture)

Q2 = "Explain CVE-2024-8309 and how to prevent that kind of bug"
Q3 = "Which OWASP category is CWE-918?"
Q6 = 'What does an "ignore previous instructions" attack look like?'
Q9 = "Add Ollama to my watchlist"
Q11 = "Look up CVE-1999-0001"
GREETING = ("Hi, I'm Patch! I know the OWASP LLM Top 10, MITRE ATLAS and the CVEs in your LLM stack. "
            "What shall we look at?")
REM = 15  # px: the base font size (DESIGN.md §3.4)


def fab(page: Page) -> Locator:
    return page.locator("button.patch-fab")


def window(page: Page) -> Locator:
    return page.get_by_role("complementary", name="Chat with Patch")


def sidebar_ask(page: Page) -> Locator:
    return page.get_by_role("complementary", name="Main").get_by_role("button", name="Ask Patch")


def open_chat(page: Page) -> Locator:
    fab(page).click()
    expect(window(page)).to_be_visible()
    return window(page)


def send(page: Page, text: str) -> None:
    box = window(page).get_by_role("textbox", name="Message")
    box.fill(text)
    box.press("Enter")


def last_answer(page: Page) -> Locator:
    return window(page).locator(".message.assistant").last


def ask(page: Page, text: str) -> Locator:
    """Send a question and wait for its answer."""
    before = window(page).locator(".message.assistant").count()
    send(page, text)
    expect(window(page).locator(".message.assistant")).to_have_count(before + 1, timeout=10_000)
    return window(page).locator(".message.assistant").nth(before)


def mood(robot: Locator) -> str:
    cls = robot.get_attribute("class") or ""
    found = re.search(r"mood-(\w+)", cls)
    return found.group(1) if found else ""


def head_bot(page: Page) -> Locator:
    return window(page).locator(".chat-head svg.robot")


def fab_bot(page: Page) -> Locator:
    return fab(page).locator("svg.robot")


def box(loc: Locator) -> dict:
    b = loc.bounding_box()
    assert b is not None
    return b


def hold_chat(page: Page) -> list[Route]:
    """Hold /chat requests until the test lets them go, so 'thinking' can be seen."""
    held: list[Route] = []
    page.route("**/chat", lambda route: held.append(route))
    return held


def release(page: Page, held: list[Route]) -> None:
    for _ in range(50):  # let the request reach the route handler
        if held:
            break
        page.wait_for_timeout(100)
    held.pop().continue_()
    page.unroute("**/chat")


# --- Patch: the drawing and where he appears (DESIGN.md §8.1, §8.2) ----------------------------------------------

def test_a06_3_patch_drawn_hidden_from_screen_readers_with_unique_gradient_ids(open_app):
    page = open_app()
    open_chat(page)
    fab(page).focus()  # still on the page while open (just the pill)
    robots = page.locator("svg.robot")
    assert robots.count() >= 3  # snapshot card, chat header, greeting
    for i in range(robots.count()):
        r = robots.nth(i)
        assert r.get_attribute("aria-hidden") == "true"
        assert r.get_attribute("viewBox") == "0 0 120 130"
        w, h = float(r.get_attribute("width") or 0), float(r.get_attribute("height") or 0)
        assert h == pytest.approx(w * 1.08)
    ids = page.evaluate("[...document.querySelectorAll('svg.robot [id]')].map(e => e.id)")
    assert ids and len(ids) == len(set(ids)), ids
    refs = page.evaluate("[...document.querySelectorAll('svg.robot [fill^=\"url(\"]')].map(e => e.getAttribute('fill'))")
    assert all(ref[5:-1] in ids for ref in refs), refs  # every gradient points at its own instance


def test_a06_3_patch_on_the_chat_button_stands_in_front_of_the_pill(open_app):
    page = open_app()
    button = fab(page)
    expect(button).to_have_accessible_name("Ask Patch")
    b = box(button)
    assert (round(b["width"]), round(b["height"])) == (84, 66)
    assert round(1400 - (b["x"] + b["width"])) == round(1.25 * REM)
    assert round(900 - (b["y"] + b["height"])) == round(1.25 * REM)
    robot, pill = fab_bot(page), button.locator(".patch-pill")
    assert robot.get_attribute("width") == "58"
    rb, pb = box(robot), box(pill)
    assert round(pb["height"]) == 30 and round(pb["width"]) == 84
    assert rb["y"] < pb["y"] < rb["y"] + rb["height"]  # overlaps the pill's top edge
    z = lambda loc: int(loc.evaluate("el => getComputedStyle(el).zIndex"))  # noqa: E731
    assert z(robot) > z(pill)  # Patch in front, the pill behind


def test_a06_3_patch_in_the_header_and_behind_the_greeting_bubble(open_app):
    page = open_app()
    chat = open_chat(page)
    assert head_bot(page).get_attribute("width") == "34"
    expect(chat.locator(".chat-head")).to_contain_text("Patch")
    greeting_bot = chat.locator(".greeting svg.robot")
    assert greeting_bot.get_attribute("width") == "92"
    assert "wave" in (greeting_bot.get_attribute("class") or "")  # always waving
    bubble = chat.locator(".greeting-bubble")
    expect(bubble).to_have_text(GREETING)
    gb, bb = box(greeting_bot), box(bubble)
    assert gb["y"] + gb["height"] - bb["y"] == pytest.approx(2.1 * REM, abs=3)  # tucked behind, 2.1rem overlap
    z = lambda loc: int(loc.evaluate("el => getComputedStyle(el).zIndex"))  # noqa: E731
    assert z(bubble) > z(chat.locator(".greeting .robot-slot"))  # the bubble in front


# --- Moods and the unread dot (DESIGN.md §8.3) -------------------------------------------------------------------

def test_a06_4_idle_then_thinking_then_happy_for_3_seconds_then_idle(open_app):
    page = open_app()
    assert mood(fab_bot(page)) == "idle"
    open_chat(page)
    assert mood(head_bot(page)) == "idle"
    held = hold_chat(page)
    send(page, Q3)
    expect(head_bot(page)).to_have_class(re.compile("mood-thinking"))
    release(page, held)
    expect(head_bot(page)).to_have_class(re.compile("mood-happy"))
    start = time.monotonic()
    expect(head_bot(page)).to_have_class(re.compile("mood-idle"), timeout=6000)
    assert 2.5 <= time.monotonic() - start <= 4.5


def test_a06_4_alert_when_the_last_message_is_an_error(open_app):
    page = open_app()
    open_chat(page)
    page.route("**/chat", lambda route: route.fulfill(
        status=502, headers={"Access-Control-Allow-Origin": "*"},
        json={"error": {"code": "llm_error", "message": "The language model didn't respond properly."}}))
    send(page, Q3)
    expect(last_answer(page)).to_have_text("The language model didn't respond properly.")
    expect(head_bot(page)).to_have_class(re.compile("mood-alert"))
    page.unroute("**/chat")
    ask(page, Q3)
    expect(head_bot(page)).not_to_have_class(re.compile("mood-alert"))


def test_a06_4_button_and_header_share_one_mood_and_an_unread_answer_makes_patch_happy(open_app):
    page = open_app()
    open_chat(page)
    held = hold_chat(page)
    send(page, Q3)
    expect(head_bot(page)).to_have_class(re.compile("mood-thinking"))
    fab(page).click()  # close while the answer is on its way
    expect(window(page)).to_be_hidden()
    expect(fab_bot(page)).to_have_class(re.compile("mood-thinking"))  # the button agrees with the header
    expect(fab(page).locator(".unread-dot")).to_have_count(0)
    release(page, held)
    expect(fab(page).locator(".unread-dot")).to_be_visible()
    expect(sidebar_ask(page).locator(".unread-dot")).to_be_visible()
    page.wait_for_timeout(3500)  # past the 3 s happy spell: still happy while unread
    expect(fab_bot(page)).to_have_class(re.compile("mood-happy"))
    open_chat(page)
    expect(page.locator(".unread-dot")).to_have_count(0)


# --- The bubble window (DESIGN.md §6.2) --------------------------------------------------------------------------

def test_a06_5_opens_above_the_pill_and_patch_steps_off(open_app):
    page = open_app()
    chat = open_chat(page)
    expect(fab(page)).to_have_accessible_name("Close the chat")
    expect(fab_bot(page)).to_have_count(0)  # Patch stepped off: just the pill
    pill = fab(page).locator(".patch-pill")
    expect(pill).to_have_text("✕")
    # Purple: the primary gradient (white passes on it in both modes; dark --accent would give 2.6:1).
    assert pill.evaluate("el => getComputedStyle(el).backgroundImage").startswith("linear-gradient")
    assert pill.evaluate("el => getComputedStyle(el).color") == "rgb(255, 255, 255)"
    page.wait_for_timeout(300)  # the pop (0.16s) scales the window while it runs
    w = box(chat)
    assert round(1400 - (w["x"] + w["width"])) == round(1.25 * REM)
    assert round(900 - (w["y"] + w["height"])) == round(3.6 * REM)
    assert w["width"] <= 400 and w["height"] <= 600
    assert chat.evaluate("el => getComputedStyle(el).borderTopLeftRadius") == "26px"
    fab(page).click()
    expect(window(page)).to_be_hidden()
    expect(fab(page)).to_have_accessible_name("Ask Patch")


def test_a06_5_opens_with_the_pop(open_app):
    page = open_app()
    chat = open_chat(page)
    anim = chat.evaluate("el => { const s = getComputedStyle(el); return [s.animationName, s.animationDuration] }")
    assert anim == ["pop", "0.16s"]


def test_a06_5_header_names_the_page_and_has_new_chat_make_larger_and_close(open_app):
    page = open_app()
    chat = open_chat(page)
    head = chat.locator(".chat-head")
    expect(head.locator(".context-chip")).to_have_text("on Dashboard")
    for name in ("New chat", "Make larger", "Close the chat"):
        expect(head.get_by_role("button", name=name)).to_be_visible()
    page.get_by_role("button", name="Settings", exact=True).click()
    expect(head.locator(".context-chip")).to_have_text("on Settings")


def test_a06_5_greeting_with_suggestions_and_folded_more_examples(open_app):
    page = open_app()
    chat = open_chat(page)
    suggestions = chat.locator(".suggestions > button")
    assert 1 <= suggestions.count() <= 2
    more = chat.locator("details.more-examples")
    expect(more.locator("summary")).to_have_text("More examples")
    expect(more).not_to_have_attribute("open", "")
    more.locator("summary").click()
    expect(more.get_by_role("button")).to_have_count(11)
    suggestions.first.click()
    expect(chat.locator(".message.assistant")).to_have_count(1, timeout=10_000)
    expect(chat.locator(".greeting")).to_have_count(0)
    chat.get_by_role("button", name="New chat").click()
    expect(chat.locator(".greeting")).to_be_visible()


def test_a06_5_sidebar_ask_patch_opens_the_chat(open_app):
    page = open_app()
    sidebar_ask(page).click()
    expect(window(page)).to_be_visible()
    expect(sidebar_ask(page)).to_have_attribute("aria-expanded", "true")
    sidebar_ask(page).click()
    expect(window(page)).to_be_hidden()


# --- Inline details, citations, flags (DESIGN.md §6.2) -----------------------------------------------------------

def in_view(page: Page, item: Locator) -> bool:
    b, w = box(item), box(window(page).locator(".messages"))
    return b["y"] >= w["y"] - 1 and b["y"] + min(b["height"], 40) <= w["y"] + w["height"] + 1


def test_a06_6_citation_opens_the_details_and_scrolls_to_its_source(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, Q2)
    toggle = answer.get_by_role("button", name=re.compile(r"(Show|Hide) \d+ sources · 2 tool calls"))
    expect(toggle).to_have_text(re.compile("^Show"))
    expect(toggle).to_have_attribute("aria-expanded", "false")
    cites = answer.locator("a.cite")
    assert cites.count() >= 2
    last = cites.last
    n = re.sub(r"\D", "", last.inner_text())
    last.click()
    expect(toggle).to_have_attribute("aria-expanded", "true")
    expect(answer.get_by_role("tab", name=re.compile("Sources"))).to_have_attribute("aria-selected", "true")
    source = answer.locator(f"li.source[data-n='{n}']")
    expect(source).to_be_visible()
    page.wait_for_timeout(800)  # smooth scroll
    assert in_view(page, source)
    expect(source.locator(".source-n")).to_have_text(n)


def test_a06_6_tool_cards_and_query_plan(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, Q2)
    answer.get_by_role("button", name=re.compile("Show")).click()
    answer.get_by_role("tab", name=re.compile("Tool calls")).click()
    cards = answer.locator(".tool-card")
    expect(cards).to_have_count(2)
    expect(cards.first.locator("code").first).to_have_text("lookup_cve")
    expect(cards.first.locator(".cve-card")).to_contain_text("CVE-2024-8309")
    expect(cards.first.locator(".cve-card")).to_contain_text("Critical")
    expect(cards.first).to_contain_text(re.compile(r"\d+\.\d ms"))
    answer.get_by_role("tab", name="Query plan").click()
    plan = answer.locator(".query-plan")
    expect(plan).to_contain_text("prevent prompt injection leading to SQL injection")
    expect(plan.locator(".rewrites li")).to_have_count(3)
    # A10.4: the plan says which retriever found each source (Q2's search adds sources from [2] on)
    expect(plan).to_contain_text("Found by")
    expect(plan.locator(".chip", has_text=re.compile(r"^\[2\] (keyword|vector)"))).to_have_count(1)

    weak = ask(page, Q3)
    weak.get_by_role("button", name=re.compile("Show")).click()
    expect(weak.locator(".tool-card .weakness-card")).to_contain_text("A01:2025 Broken Access Control")

    watch = ask(page, Q9)
    watch.get_by_role("button", name=re.compile("Show")).click()
    # The servers live for the whole run, so another test (or browser) may have added Ollama already.
    expect(watch.locator(".tool-card .watchlist-card")).to_contain_text(
        re.compile(r"(Added Ollama to|Ollama is already on) your watchlist\."))


def test_a06_6_tool_errors_in_red(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, Q11)
    answer.get_by_role("button", name=re.compile("Show")).click()
    card = answer.locator(".tool-card")
    expect(card).to_have_class(re.compile("error"))
    err = card.locator(".tool-error")
    expect(err).to_contain_text("cve_not_in_snapshot")
    red = page.evaluate("(() => { const d = document.createElement('div'); d.style.color = 'var(--error)'; "
                        "document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c })()")
    assert err.evaluate("el => getComputedStyle(el).color") == red
    assert card.evaluate("el => getComputedStyle(el).borderLeftColor") == red


def test_a06_6_flag_notice_under_a_flagged_answer(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, Q6)
    expect(answer.locator(".flag-note")).to_have_text(
        "This message looks like an injection attempt. It was answered, and logged.")
    window(page).get_by_role("button", name="New chat").click()  # the flagged turn would be in the history
    plain = ask(page, Q3)
    expect(plain.locator(".flag-note")).to_have_count(0)


def test_a06_6_answers_render_markdown_but_never_raw_html(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, Q2)
    expect(answer.locator("strong").first).to_be_visible()  # **bold** rendered
    page.route("**/chat", lambda route: route.fulfill(
        status=200, headers={"Access-Control-Allow-Origin": "*"},
        json={"answer": "<img src=x onerror=\"window.pwned=1\"> plain", "sources": [], "tool_calls": [],
              "query": None, "usage": {"input_tokens": 1, "output_tokens": 1, "llm_calls": 1, "estimated": True,
                                       "cost": 0}, "steps": 1, "flags": [], "bad_citations": [], "no_citations": False}))
    send(page, "hi")
    expect(window(page).locator(".message.assistant")).to_have_count(2)
    expect(last_answer(page).locator("img")).to_have_count(0)
    assert page.evaluate("window.pwned") is None


# --- Motion (DESIGN.md §7, §8.3) ---------------------------------------------------------------------------------

def test_a06_8_normal_motion_patch_moves(open_app):
    page = open_app()
    names = fab_bot(page).evaluate("el => [...el.querySelectorAll('*')].map(c => getComputedStyle(c).animationName)")
    assert {"bot-bob", "bot-blink", "bot-hand", "bot-shadow"} <= set(names)
    running = fab_bot(page).evaluate("el => el.getAnimations({ subtree: true }).length")
    assert running > 0


def test_a06_8_reduced_motion_nothing_in_the_chat_moves(open_app):
    page = open_app(reduced=True)
    assert page.evaluate("document.getAnimations().length") == 0  # Patch on the button
    chat = open_chat(page)
    held = hold_chat(page)
    send(page, Q3)
    expect(head_bot(page)).to_have_class(re.compile("mood-thinking"))
    assert page.evaluate("document.getAnimations().length") == 0  # no pop, no thinking motion
    release(page, held)
    expect(head_bot(page)).to_have_class(re.compile("mood-happy"))
    assert page.evaluate("document.getAnimations().length") == 0  # no waving
    page.route("**/chat", lambda route: route.fulfill(
        status=502, headers={"Access-Control-Allow-Origin": "*"}, json={"error": {"code": "x", "message": "Down."}}))
    send(page, Q3)
    expect(head_bot(page)).to_have_class(re.compile("mood-alert"))
    assert page.evaluate("document.getAnimations().length") == 0  # no shake
    assert chat.evaluate("el => getComputedStyle(el).animationName") == "none"


# --- Light, dark, phone, desktop (DESIGN.md §9, §4.2) ------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a06_9_works_in_light_and_dark_at_phone_and_desktop_width(open_app, browser_name, width, scheme):
    page = open_app(width=width, scheme=scheme, reduced=True)
    button = box(fab(page))
    if width == PHONE:  # above the bottom tab bar
        assert button["y"] + button["height"] <= box(page.locator(".sidenav"))["y"]
    chat = open_chat(page)
    answer = ask(page, Q2)
    answer.locator("a.cite").first.click()
    w = box(chat)
    assert w["x"] >= 0 and w["x"] + w["width"] <= width and w["y"] >= 0
    assert no_sideways_scroll(page)
    text = css_var(page, "--text")
    surface = css_var(page, "--surface")
    assert contrast(text, surface) >= 4.5
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"a06-{browser_name}-{width}-{scheme}-chat.png")


# --- Keyboard and names (DESIGN.md §10) --------------------------------------------------------------------------

def test_a06_10_keyboard_open_ask_and_reach_every_chat_control(open_app):
    page = open_app()
    button = fab(page)
    page.get_by_role("button", name="Dev", exact=True).click()  # the page with the fewest controls before Patch
    page.get_by_role("button", name="Switch to dark mode").focus()
    for _ in range(80):  # by keyboard, so :focus-visible applies; Patch's button comes after the page's controls
        page.keyboard.press("Tab")
        if button.evaluate("el => el === document.activeElement"):
            break
    expect(button).to_be_focused()
    outline = button.evaluate("el => [getComputedStyle(el).outlineStyle, getComputedStyle(el).outlineWidth]")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2
    page.wait_for_timeout(300)  # the pill's 0.15s colour transition
    pill_border = button.locator(".patch-pill").evaluate("el => getComputedStyle(el).borderTopColor")
    accent = page.evaluate("(() => { const d = document.createElement('div'); d.style.color = 'var(--accent)'; "
                           "document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c })()")
    assert pill_border == accent  # visible focus: the pill's border turns purple
    page.keyboard.press("Enter")
    expect(window(page)).to_be_visible()
    box_ = window(page).get_by_role("textbox", name="Message")
    expect(box_).to_be_focused()
    page.keyboard.type(Q3)
    page.keyboard.press("Enter")
    expect(window(page).locator(".message.assistant")).to_have_count(1, timeout=10_000)
    names = []
    for _ in range(14):
        page.keyboard.press("Shift+Tab")
        names.append(page.evaluate("(() => { const a = document.activeElement; "
                                   "return a.getAttribute('aria-label') || a.textContent.trim() })()"))
    for name in ("New chat", "Make larger", "Close the chat"):
        assert name in names, names
    assert any(n.startswith("Show 0 sources · 1 tool calls") for n in names), names
    window(page).get_by_role("button", name=re.compile("Show")).focus()
    page.keyboard.press("Enter")
    expect(window(page).get_by_role("tab", name=re.compile("Tool calls"))).to_be_visible()
    outline = page.evaluate("(() => { const s = getComputedStyle(document.activeElement); "
                            "return [s.outlineStyle, s.outlineWidth] })()")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2

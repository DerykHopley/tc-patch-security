"""Browser check (seam 3) for the chat on FakeLLM: the bubble and Patch. Check ids: A06.n, from ticket #8.

Runs in Firefox and Chromium (run.sh). Expected values come from docs/design/DESIGN.md §6 and §8, not from the CSS.
"""
import re
import time

import pytest
from playwright.sync_api import Locator, Page, Route, expect

from test_shell import (  # noqa: F401 (fixture)
    DESKTOP, PHONE, SHOTS, contrast, css_var, eventually, no_sideways_scroll, open_app, settled)
from reduced_motion import scene, still

Q2 = "Explain CVE-2024-8309 and how to prevent that kind of bug"
Q3 = "Which OWASP category is CWE-918?"
Q6 = 'What does an "ignore previous instructions" attack look like?'
Q9 = "Add vLLM to my watchlist"
Q11 = "Look up CVE-1999-0001"
GREETING = ("Hi, I'm Patch! I know the OWASP LLM Top 10, MITRE ATLAS and the CVEs on your watchlist. "
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
    eventually(page, lambda: bool(held))  # the request has reached the route handler
    held.pop().continue_()
    page.unroute("**/chat")


# --- Patch: the drawing and where he appears (DESIGN.md §8.1, §8.2) ----------------------------------------------

def test_a06b_2_patch_is_the_squircle_hidden_from_screen_readers_with_unique_ids(open_app):
    page = open_app()
    open_chat(page)
    fab(page).focus()  # still on the page while open (just the pill)
    robots = page.locator("svg.robot")
    assert robots.count() >= 3  # snapshot card, chat header, greeting
    for i in range(robots.count()):
        r = robots.nth(i)
        assert r.get_attribute("aria-hidden") == "true"
        assert r.get_attribute("viewBox") == "0 0 160 170"
        w, h = float(r.get_attribute("width") or 0), float(r.get_attribute("height") or 0)
        assert h == pytest.approx(w * 170 / 160)
        # The canvas colours (DESIGN.md §8.1): body, visor, eyes, antenna light.
        assert r.locator("rect[rx='44']").get_attribute("fill") == "#9483FF"
        assert r.locator("rect[rx='20']").get_attribute("fill") == "#2A2457"
        assert r.locator("[fill='#7FF0DD']").count() == 2
        assert r.locator("circle[cx='80'][cy='19'][r='7']").last.get_attribute("fill") == "#FFC94D"
    ids = page.evaluate("[...document.querySelectorAll('svg.robot [id]')].map(e => e.id)")
    assert len(ids) == len(set(ids)), ids  # several Patches on one page never share an id


def test_a06_3_patch_on_the_chat_button_stands_in_front_of_the_pill(open_app):
    page = open_app()
    button = fab(page)
    expect(button).to_have_accessible_name("Ask Patch")
    b = box(button)
    assert (round(b["width"]), round(b["height"])) == (84, 66)
    assert round(1400 - (b["x"] + b["width"])) == round(1.25 * REM)
    assert round(900 - (b["y"] + b["height"])) == round(1.25 * REM)
    robot, pill = fab_bot(page), button.locator(".patch-pill")
    assert robot.get_attribute("width") == "68"  # the chat button's Patch (Deryk, 2026-10-16: 58 was a bit small)
    rb, pb = box(robot), box(pill)
    assert round(pb["height"]) == 30 and round(pb["width"]) == 84
    assert rb["y"] < pb["y"] < rb["y"] + rb["height"]  # overlaps the pill's top edge
    assert round(b["y"] - rb["y"]) == 8  # no higher than the 58px Patch was: he covers no more of the page
    assert rb["y"] + rb["height"] <= pb["y"] + pb["height"]  # the extra size goes down, still within the pill
    z = lambda loc: int(loc.evaluate("el => getComputedStyle(el).zIndex"))  # noqa: E731
    assert z(robot) > z(pill)  # Patch in front, the pill behind


def test_a06_3_patch_in_the_header_and_at_the_greeting_bubble_s_corner(open_app):
    """The greeting's Patch (58px, in front, as on the chat button) sits on the bubble's top-left corner; only the
    first line of text sits beside him (Deryk, 2026-10-15: at 92px behind the bubble, half of him was hidden)."""
    page = open_app()
    chat = open_chat(page)
    assert head_bot(page).get_attribute("width") == "34"
    expect(chat.locator(".chat-head")).to_contain_text("Patch")
    greeting_bot = chat.locator(".greeting svg.robot")
    assert greeting_bot.get_attribute("width") == "58"
    assert greeting_bot.get_attribute("data-mood") == "idle"  # no mood here: idle (A06b)
    bubble = chat.locator(".greeting-bubble")
    expect(bubble).to_have_text(GREETING)
    gb, bb = box(greeting_bot), box(bubble)
    assert gb["x"] < bb["x"] < gb["x"] + gb["width"]  # over the left edge
    assert gb["y"] < bb["y"] < gb["y"] + gb["height"]  # over the top edge
    z = lambda loc: int(loc.evaluate("el => getComputedStyle(el).zIndex"))  # noqa: E731
    assert z(chat.locator(".greeting .robot-slot")) > z(bubble)  # Patch in front, as on the button
    lines = bubble.locator("p").evaluate(
        "p => { const r = document.createRange(); r.selectNodeContents(p);"
        " const seen = new Map(); for (const b of r.getClientRects()) {"
        "   const k = Math.round(b.top); if (!seen.has(k) || b.left < seen.get(k)) seen.set(k, b.left); }"
        " return [...seen.entries()].sort((a, b) => a[0] - b[0]).map(e => e[1]); }")
    assert len(lines) >= 2
    right_of_patch = gb["x"] + gb["width"]
    assert lines[0] >= right_of_patch - 2  # the first line beside him
    assert all(left < right_of_patch for left in lines[1:])  # the rest under him, from the bubble's left


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
    page.wait_for_timeout(3500)  # allowed: past the 3 s happy spell, still happy while unread
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
    settled(chat)  # the pop (0.16s) scales the window while it runs
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


def test_a06_5_greeting_with_suggestions_and_folded_more_examples(open_app, api_url):
    import json
    import urllib.request

    n_examples = len(json.load(urllib.request.urlopen(api_url + "/examples")))  # later tickets add questions
    page = open_app()
    chat = open_chat(page)
    suggestions = chat.locator(".suggestions > button")
    assert 1 <= suggestions.count() <= 2
    more = chat.locator("details.more-examples")
    expect(more.locator("summary")).to_have_text("More examples")
    expect(more).not_to_have_attribute("open", "")
    more.locator("summary").click()
    expect(more.get_by_role("button")).to_have_count(n_examples)
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


# --- B65 (#112): the open chat button never covers Send (DESIGN.md §6.2) -----------------------------------------
# The open button was still 84 × 66px with only its 30px pill drawn. Its empty top lay over the window's bottom-right
# corner (z 21 over the window's 20), where Send sits: a click on Send's lower half closed the chat. 750px is the
# tab-bar layout's bubble (701–800px); at 390px the sheet covers the button.

def send_button(page: Page) -> Locator:
    return window(page).get_by_role("button", name="Send", exact=True)


# Which element a click at the top, middle and bottom of Send (3px in from each edge) lands on: Send or inside it.
SEND_HITS = """send => {
  const b = send.getBoundingClientRect(), x = b.left + b.width / 2
  return [b.top + 3, b.top + b.height / 2, b.bottom - 3].map(y => send.contains(document.elementFromPoint(x, y)))
}"""


@pytest.mark.parametrize("width", [PHONE, 750, DESKTOP])
@pytest.mark.parametrize("enlarged", [False, True])
def test_b65_1_send_takes_a_click_at_its_top_middle_and_bottom(open_app, width, enlarged):
    page = open_app(width=width)
    chat = open_chat(page)
    if enlarged and width > 700:  # a phone's sheet has no Make larger
        chat.locator(".chat-head").get_by_role("button", name="Make larger", exact=True).click()
    settled(chat)
    assert send_button(page).evaluate(SEND_HITS) == [True, True, True]


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b65_2_a_click_on_send_s_lower_edge_sends_and_the_chat_stays_open(open_app, width):
    page = open_app(width=width)
    chat = open_chat(page)
    settled(chat)
    chat.get_by_role("textbox", name="Message").fill(Q3)
    b = box(send_button(page))
    # The mouse itself, as a person clicks: Playwright's click would wait for the covering button to move away.
    page.mouse.click(b["x"] + b["width"] / 2, b["y"] + b["height"] - 3)
    expect(chat.locator(".message.user").last).to_have_text(Q3)
    expect(chat.locator(".message.assistant")).to_have_count(1, timeout=10_000)
    expect(chat).to_be_visible()
    ask(page, Q2)  # Enter still sends
    expect(chat.locator(".message.user")).to_have_count(2)
    expect(chat).to_be_visible()


# --- Inline details, citations, flags (DESIGN.md §6.2) -----------------------------------------------------------

def in_view(page: Page, item: Locator) -> bool:
    b, w = box(item), box(window(page).locator(".messages"))
    return b["y"] >= w["y"] - 1 and b["y"] + min(b["height"], 40) <= w["y"] + w["height"] + 1


def test_a06_6_citation_opens_the_details_and_scrolls_to_its_source(open_app):
    page = open_app()
    open_chat(page)
    answer = ask(page, Q2)
    toggle = answer.get_by_role("button", name=re.compile(r"(Show|Hide) \d+ sources? · 2 tool calls"))
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
    eventually(page, lambda: in_view(page, source))  # smooth scroll
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
    # Patch only proposes (B21). The servers live for the whole run, so another test may have added vLLM already.
    expect(watch.locator(".tool-card .watchlist-card")).to_contain_text(
        re.compile(r"(Proposed: Add vLLM to your watchlist|vLLM is already on your watchlist)"))


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
    page = open_app(init_script=pick(0))  # idle A, float
    names = fab_bot(page).evaluate("el => [...el.querySelectorAll('*')].map(c => getComputedStyle(c).animationName)")
    assert {"pb-float-7", "pb-blink", "pb-wiggle", "pb-shadow"} <= set(names)
    running = fab_bot(page).evaluate("el => el.getAnimations({ subtree: true }).length")
    assert running > 0


# Reduced motion: scenes a06_8 and a06b_7 at the end of this file, in the shared check (reduced_motion.py).


# --- A06b: the squircle robot, four animations per mood, one picked at random (ticket #29) -----------------------

OPTIONS = {  # the canvas order, A to D (docs/design/patch/)
    "idle": ["float", "breathe", "look", "hop"],
    "thinking": ["scan", "typing", "ponder", "radar"],
    "happy": ["bounce", "spin", "dance", "hearts"],
    "alert": ["shake", "startle", "siren", "pop"],
}

# Each variant's keyframes as "name duration delay", read from the canvas artboards (docs/design/patch/*.dc.html).
KEYFRAMES = {
    "float": {"pb-shadow 2.6s 0s", "pb-float-7 2.6s 0s", "pb-wiggle 1.8s 0s", "pb-blink 4s 0s"},
    "breathe": {"pb-breathe 3.2s 0s", "pb-glow 3.2s 0s", "pb-blink 6s 0s"},
    "look": {"pb-lean 5s 0s", "pb-look 5s 0s", "pb-blink 4s 0s"},
    "hop": {"pb-hopshadow 3s 0s", "pb-hop 3s 0s", "pb-blink 4s 0s"},
    "scan": {"pb-pulse 1.2s 0s", "pb-pulse 1.2s 0.2s", "pb-pulse 1.2s 0.4s", "pb-scan 1.6s 0s"},
    "typing": {"pb-float-5 2.6s 0s", "pb-typing 1.2s 0s", "pb-typing 1.2s 0.15s", "pb-typing 1.2s 0.3s"},
    "ponder": {"pb-rock 3s 0s", "pb-pulse 1.2s 0s", "pb-blink 4s 0s"},
    "radar": {"pb-ping 1.8s 0s", "pb-ping 1.8s 0.9s", "pb-blink 4s 0s"},
    "bounce": {"pb-pulse 1.2s 0s", "pb-pulse 1.2s 0.4s", "pb-squish 1s 0s", "pb-wiggle 0.45s 0s"},
    "spin": {"pb-spinshadow 2.2s 0s", "pb-spinjump 2.2s 0s"},
    "dance": {"pb-rise 1.8s 0s", "pb-rise 1.8s 0.9s", "pb-dance 0.9s 0s", "pb-wiggle 0.45s 0s"},
    "hearts": {"pb-rise 1.8s 0s", "pb-rise 1.8s 0.9s", "pb-float-6 2.6s 0s", "pb-beat 1.2s 0s"},
    "shake": {"pb-shake 0.5s 0s"},
    "startle": {"pb-startleshadow 2.4s 0s", "pb-startle 2.4s 0s"},
    "siren": {"pb-spin 1.2s 0s", "pb-halo 0.6s 0s", "pb-siren 0.6s 0s"},
    "pop": {"pb-pop 2.6s 0s", "pb-freeze 2.6s 0s", "pb-widen 2.6s 0s"},
}

# Each variant's face and extras (selector: how many), as on the canvas. They must also show in the still pose.
EYE = "#7FF0DD"
FACES = {
    "float": {f"ellipse[fill='{EYE}']": 2},
    "breathe": {f"ellipse[fill='{EYE}']": 2, "ellipse[fill='#FFB3CF']": 2},  # cheeks
    "look": {f"ellipse[fill='{EYE}']": 2},
    "hop": {f"ellipse[fill='{EYE}']": 2, "ellipse[fill='#FFB3CF']": 2},
    "scan": {f"circle[fill='{EYE}']": 2, ".bot-extra circle": 3},  # scanning eyes, three thought dots
    "typing": {f"circle[fill='{EYE}'][r='5']": 3},  # the eyes are a loader
    "ponder": {f"ellipse[fill='{EYE}']": 2},
    "radar": {f"ellipse[fill='{EYE}']": 2, ".bot-extra circle[stroke='#FFC94D']": 2},  # pings
    "bounce": {f"path[stroke='{EYE}']": 2, ".bot-extra path[fill='#FFC94D']": 2},  # arc eyes, sparkles
    "spin": {f"path[stroke='{EYE}']": 2},
    "dance": {f"path[stroke='{EYE}']": 2, ".bot-extra text": 2},  # arc eyes, notes
    "hearts": {".pb-beat": 2, ".bot-extra path": 2},  # heart eyes, hearts floating up
    "shake": {f"circle[r='9'][fill='{EYE}']": 2, "path.bot-extra": 1},  # wide eyes, alarm lines
    "startle": {f"circle[r='9'][fill='{EYE}']": 2, "circle[r='3.5']": 2},  # pinprick pupils
    "siren": {f"circle[r='9'][fill='{EYE}']": 2, ".pb-beam path": 3},  # the siren beam
    "pop": {f"circle[r='9'][fill='{EYE}']": 2, ".pb-pop circle[fill='#FF4D6D']": 1},  # the "!" badge
}


def pick(option: int) -> str:
    """Init script: Patch's random source (Math.random) gives option 0-3 (A-D) until a test calls set_pick."""
    return (f"(() => {{ window.__patchPick = {option / 4 + 0.01}; const real = Math.random;"
            " Math.random = () => window.__patchPick ?? real() })()")


def set_pick(page: Page, option: int) -> None:
    page.evaluate(f"window.__patchPick = {option / 4 + 0.01}")


def variant(robot: Locator) -> str:
    return robot.get_attribute("data-variant") or ""


def keyframes(robot: Locator) -> set[str]:
    return set(robot.evaluate("""el => [...el.querySelectorAll('*')].map(c => getComputedStyle(c))
        .filter(s => s.animationName !== 'none')
        .map(s => `${s.animationName} ${s.animationDuration} ${s.animationDelay}`)"""))


def has_face(robot: Locator, name: str) -> None:
    for selector, count in FACES[name].items():
        expect(robot.locator(selector)).to_have_count(count)


def to_thinking(page: Page) -> list[Route]:
    held = hold_chat(page)
    send(page, Q3)
    expect(head_bot(page)).to_have_attribute("data-mood", "thinking")
    return held


def to_alert(page: Page) -> None:
    page.route("**/chat", lambda route: route.fulfill(
        status=502, headers={"Access-Control-Allow-Origin": "*"}, json={"error": {"code": "x", "message": "Down."}}))
    send(page, Q3)
    expect(head_bot(page)).to_have_attribute("data-mood", "alert")
    page.unroute("**/chat")


@pytest.mark.parametrize("option", range(4), ids="ABCD")
def test_a06b_3_every_variant_has_its_canvas_keyframes_and_face(open_app, option):
    page = open_app(init_script=pick(option))
    open_chat(page)
    seen = []

    def check(mood_: str) -> None:
        name = OPTIONS[mood_][option]
        expect(head_bot(page)).to_have_attribute("data-variant", name)
        assert keyframes(head_bot(page)) == KEYFRAMES[name], name
        has_face(head_bot(page), name)
        seen.append(name)

    check("idle")
    held = to_thinking(page)
    check("thinking")
    release(page, held)
    expect(head_bot(page)).to_have_attribute("data-mood", "happy")
    check("happy")
    to_alert(page)
    check("alert")
    assert seen == [OPTIONS[m][option] for m in OPTIONS]


def test_a06b_4_a_new_pick_only_on_entering_a_mood_and_the_button_and_header_agree(open_app):
    page = open_app(init_script=pick(1))
    expect(fab_bot(page)).to_have_attribute("data-variant", "breathe")
    open_chat(page)
    expect(head_bot(page)).to_have_attribute("data-variant", "breathe")  # still idle: no new pick
    held = to_thinking(page)
    expect(head_bot(page)).to_have_attribute("data-variant", "typing")
    set_pick(page, 3)  # the random source moves on; staying in "thinking" must not pick again
    window(page).get_by_role("textbox", name="Message").fill("re-renders while typing")
    expect(head_bot(page)).to_have_attribute("data-variant", "typing")
    fab(page).click()  # close: the button shows the same mood and the same animation
    expect(fab_bot(page)).to_have_attribute("data-mood", "thinking")
    expect(fab_bot(page)).to_have_attribute("data-variant", "typing")
    release(page, held)  # entering "happy" picks: option D
    expect(fab_bot(page)).to_have_attribute("data-mood", "happy")
    expect(fab_bot(page)).to_have_attribute("data-variant", "hearts")
    set_pick(page, 2)
    open_chat(page)
    to_alert(page)
    expect(head_bot(page)).to_have_attribute("data-variant", "siren")
    fab(page).click()
    expect(fab_bot(page)).to_have_attribute("data-variant", "siren")


def test_a06b_5_places_without_a_mood_show_idle_picked_on_page_load(open_app):
    page = open_app(init_script=pick(3))
    places = [page.locator(".hello svg.robot"), page.locator(".side-card svg.robot")]
    open_chat(page)
    places.append(window(page).locator(".greeting svg.robot"))
    for robot in places:
        expect(robot).to_have_attribute("data-mood", "idle")
        expect(robot).to_have_attribute("data-variant", "hop")
    set_pick(page, 0)
    to_thinking(page)  # Patch's mood changes; the places without one keep the pick from page load
    for robot in places[:2]:
        expect(robot).to_have_attribute("data-variant", "hop")


# The motion envelope: every part's box, sampled through each animation's cycle (paused and stepped with the Web
# Animations API, so no waiting). `extra` is the same for the parts outside the body (`.bot-extra`).
ENVELOPE = """svg => {
    const parts = [...svg.querySelectorAll('ellipse, rect, circle, path, line, text')]
    const empty = () => ({ left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity })
    const all = empty(), extra = empty()
    const grow = (u, r) => { u.left = Math.min(u.left, r.left); u.top = Math.min(u.top, r.top);
        u.right = Math.max(u.right, r.right); u.bottom = Math.max(u.bottom, r.bottom) }
    const anims = svg.getAnimations({ subtree: true })
    anims.forEach(a => a.pause())
    const steps = anims.length ? 48 : 1
    for (let i = 0; i < steps; i++) {
        for (const a of anims) {
            const t = a.effect.getComputedTiming()
            a.currentTime = (a.effect.getTiming().delay || 0) + t.duration * i / steps
        }
        for (const el of parts) {
            const r = el.getBoundingClientRect()
            if (!r.width && !r.height) continue
            grow(all, r)
            if (el.closest('.bot-extra')) grow(extra, r)
        }
    }
    anims.forEach(a => a.play())
    return { all, extra: extra.left === Infinity ? null : extra }
}"""

# Every ancestor that cuts off what sticks out of it (overflow other than visible), and the window.
CLIPS = """svg => {
    const out = [{ name: 'the window', left: 0, top: 0, right: innerWidth, bottom: innerHeight }]
    for (let el = svg.parentElement; el && el !== document.documentElement; el = el.parentElement) {
        const s = getComputedStyle(el)
        if (s.overflowX === 'visible' && s.overflowY === 'visible') continue
        const r = el.getBoundingClientRect()
        out.push({ name: el.className || el.tagName, left: r.left, top: r.top, right: r.right, bottom: r.bottom })
    }
    return out
}"""


def close_chat(page: Page) -> None:
    """With the header's ✕: on a phone the sheet covers Patch's button."""
    window(page).locator(".chat-head").get_by_role("button", name="Close the chat").click()
    expect(window(page)).to_have_count(0)


def overlaps(a: dict, b: dict) -> bool:
    return a["left"] < b["right"] and b["left"] < a["right"] and a["top"] < b["bottom"] and b["top"] < a["bottom"]


def rect(loc: Locator) -> dict:
    return loc.evaluate("el => { const r = el.getBoundingClientRect(); "
                        "return { left: r.left, top: r.top, right: r.right, bottom: r.bottom } }")


def fits(robot: Locator, avoid: list[Locator], extras_only: bool = False) -> None:
    """Patch, through all of his animation, isn't cut off, and doesn't cover the controls next to him."""
    env = robot.evaluate(ENVELOPE)
    where = f"{robot.get_attribute('data-mood')} {variant(robot)}"
    for clip in robot.evaluate(CLIPS):
        for side in ("left", "top"):
            assert env["all"][side] >= clip[side] - 0.5, (where, "cut off by", clip, env["all"])
        for side in ("right", "bottom"):
            assert env["all"][side] <= clip[side] + 0.5, (where, "cut off by", clip, env["all"])
    mine = env["extra"] if extras_only else env["all"]
    for control in avoid:
        for i in range(control.count()):
            if mine and control.nth(i).is_visible():
                assert not overlaps(mine, rect(control.nth(i))), (where, "covers", control.nth(i), mine)


@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("option", range(4), ids="ABCD")
def test_a06b_6_every_variant_fits_its_places_in_both_themes(open_app, browser_name, option, width, scheme):
    page = open_app(width=width, scheme=scheme, init_script=pick(option))
    SHOTS.mkdir(exist_ok=True)

    def name(mood_: str) -> str:
        return OPTIONS[mood_][option]

    def shot(what: str) -> None:
        if browser_name == "chromium":
            page.screenshot(path=SHOTS / f"a06b-{width}-{scheme}-{'ABCD'[option]}-{what}.png")

    dot = fab(page).locator(".unread-dot")
    head_buttons = window(page).locator(".chat-head button")

    # Idle: the button, the welcome banner, the snapshot card (desktop: on a phone it's the tab bar).
    expect(fab_bot(page)).to_have_attribute("data-variant", name("idle"))
    fits(fab_bot(page), [dot], extras_only=True)
    hello = page.locator(".hello")
    fits(hello.locator("svg.robot"), [hello.get_by_role("button")])
    if width == DESKTOP:
        fits(page.locator(".side-card svg.robot"), [page.locator(".side-links button")])
    shot("idle")
    # Open: the header (34px) and the greeting (92px, behind the bubble).
    open_chat(page)
    settled(window(page))
    fits(head_bot(page), [head_buttons])
    fits(window(page).locator(".greeting svg.robot"), [])
    # Thinking in the header, then on the button.
    held = to_thinking(page)
    expect(head_bot(page)).to_have_attribute("data-variant", name("thinking"))
    fits(head_bot(page), [head_buttons])
    shot("thinking")
    close_chat(page)
    expect(fab_bot(page)).to_have_attribute("data-variant", name("thinking"))
    fits(fab_bot(page), [dot], extras_only=True)
    # Happy with an unread answer: his extras keep clear of the unread dot.
    release(page, held)
    expect(dot).to_be_visible()
    expect(fab_bot(page)).to_have_attribute("data-variant", name("happy"))
    fits(fab_bot(page), [dot], extras_only=True)
    shot("happy")
    # Happy in the header, then alert in the header and on the button.
    open_chat(page)
    release(page, to_thinking(page))
    expect(head_bot(page)).to_have_attribute("data-mood", "happy")
    fits(head_bot(page), [head_buttons])
    to_alert(page)
    expect(head_bot(page)).to_have_attribute("data-variant", name("alert"))
    fits(head_bot(page), [head_buttons])
    shot("alert")
    close_chat(page)
    expect(fab_bot(page)).to_have_attribute("data-variant", name("alert"))
    fits(fab_bot(page), [dot], extras_only=True)


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
    pill_border = lambda: button.locator(".patch-pill").evaluate("el => getComputedStyle(el).borderTopColor")  # noqa: E731
    accent = page.evaluate("(() => { const d = document.createElement('div'); d.style.color = 'var(--accent)'; "
                           "document.body.append(d); const c = getComputedStyle(d).color; d.remove(); return c })()")
    eventually(page, lambda: pill_border() == accent)  # visible focus: the border turns purple (a 0.15s transition)
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
    assert any(n.startswith("Show 0 sources · 1 tool call") for n in names), names
    window(page).get_by_role("button", name=re.compile("Show")).focus()
    page.keyboard.press("Enter")
    expect(window(page).get_by_role("tab", name=re.compile("Tool calls"))).to_be_visible()
    outline = page.evaluate("(() => { const s = getComputedStyle(document.activeElement); "
                            "return [s.outlineStyle, s.outlineWidth] })()")
    assert outline[0] != "none" and float(outline[1].rstrip("px")) >= 2


# --- Reduced motion: this file's scenes in the shared check (reduced_motion.py) --------------------------------------

@scene
def a06_8_chat(fx):
    page = fx("open_app")(reduced=True)
    still(page, "Patch on the button")
    chat = open_chat(page)
    held = hold_chat(page)
    send(page, Q3)
    expect(head_bot(page)).to_have_class(re.compile("mood-thinking"))
    still(page, "no pop, no thinking motion")
    release(page, held)
    expect(head_bot(page)).to_have_class(re.compile("mood-happy"))
    still(page, "no waving")
    page.route("**/chat", lambda route: route.fulfill(
        status=502, headers={"Access-Control-Allow-Origin": "*"}, json={"error": {"code": "x", "message": "Down."}}))
    send(page, Q3)
    expect(head_bot(page)).to_have_class(re.compile("mood-alert"))
    still(page, "no shake")
    assert chat.evaluate("el => getComputedStyle(el).animationName") == "none"


@scene
def a06b_7_patch_variants(fx):
    """All 16 of Patch's animations stand still, each in a pose that keeps its face (arc eyes, wide eyes, ...)."""
    for option in range(4):
        page = fx("open_app")(reduced=True, init_script=pick(option))
        places = [page.locator(".patch-fab svg.robot"), page.locator(".hello svg.robot"),
                  page.locator(".side-card svg.robot")]
        for robot in places:
            expect(robot).to_have_attribute("data-variant", OPTIONS["idle"][option])
        still(page, f"idle {OPTIONS['idle'][option]}: the button, the banner, the snapshot card")
        has_face(places[0], OPTIONS["idle"][option])
        open_chat(page)
        held = to_thinking(page)
        still(page, f"thinking {OPTIONS['thinking'][option]}")
        has_face(head_bot(page), OPTIONS["thinking"][option])
        release(page, held)
        expect(head_bot(page)).to_have_attribute("data-mood", "happy")
        still(page, f"happy {OPTIONS['happy'][option]}")
        has_face(head_bot(page), OPTIONS["happy"][option])
        to_alert(page)
        still(page, f"alert {OPTIONS['alert'][option]}")
        has_face(head_bot(page), OPTIONS["alert"][option])
        # The still pose shows every part: nothing is left at a keyframe's scale(0) or opacity 0.
        hidden = head_bot(page).evaluate("""el => [...el.querySelectorAll('*')].filter(c => {
            const s = getComputedStyle(c); return s.transform.startsWith('matrix(0, 0, 0, 0') || s.opacity === '0' })
            .length""")
        assert hidden == 0

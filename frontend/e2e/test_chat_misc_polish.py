"""Browser check for the chat, loading, not-found and chip polish from the page review (B49, #96). Check ids: B49.n.

The words are unit-tested (`npm test`: plural.test.ts, toolCalls.test.ts, chat/chatStore.test.ts, chat/messages.test.ts,
route.test.ts, monthAxis.test.ts, access.test.ts); this checks them on the page. The loading screen's new words are
in test_loading_screen.py, the measured contrast in test_contrast.py. Expected looks: docs/design/DESIGN.md §5.14,
§5.18, §5.19, §6.2, §11. Every test starts from and leaves the default state, since all tests share one backend.
"""
import re

import pytest
from playwright.sync_api import Browser, BrowserContext, Page, expect

from reduced_motion import scene, still
from test_access import OWNER, FakeAccess
from test_chat import ask, open_chat, send, window
from test_contrast import low_contrast, show
from test_dashboard import api, ask_about
from test_partial import text_contrast
from test_affected import set_stack
from test_card_actions import tool_cards
from test_fix_first import FIX_FIRST
from test_research_decision import ASK_KNOWN as RESEARCH, CVE as RESEARCH_CVE
from test_shell import SHOTS, no_sideways_scroll, settled

PHONE, DESKTOP = 390, 1440
SIZES = [(PHONE, "light"), (PHONE, "dark"), (DESKTOP, "light"), (DESKTOP, "dark")]
Q = "What is prompt injection?"
LIMIT = "You've sent 10 messages in the last minute, the most allowed. Try again at 09:01 UTC."
CORS = {"Access-Control-Allow-Origin": "*"}
NO_SESSION_STORAGE = """Object.defineProperty(window, 'sessionStorage', {
  get() { throw new DOMException('The operation is insecure.', 'SecurityError') } })"""


@pytest.fixture(autouse=True)
def fresh_state(api_url: str):
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})
    yield
    api(api_url, "/state/reset", "POST", {"confirm": "reset"})


@pytest.fixture
def known_langflow(api_url: str):
    """Langflow 1.3.0 recorded (not affected), so the research question ends in a proposal: Patch proposes nothing
    for this KEV CVE while the version is unknown (B62) or affected (#133). fresh_state resets it after."""
    set_stack(api_url, langflow={"version": "1.3.0"})


@pytest.fixture
def open_page(browser: Browser, ui_url: str, api_url: str):
    """Opens Patch at `path`; `role`: answer /access as that role (FakeAccess), else the sign-in-off owner."""
    contexts: list[BrowserContext] = []

    def _open(path="/", width=DESKTOP, scheme="light", reduced=False, role: str | None = None,
              init_script: str | None = None, ctx: BrowserContext | None = None) -> Page:
        if ctx is None:
            ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme,
                                      reduced_motion="reduce" if reduced else "no-preference")
            contexts.append(ctx)
            if role:
                FakeAccess({**OWNER, "owner": role == "owner", "role": role}).route(ctx, api_url)
            if init_script:
                ctx.add_init_script(init_script)
        page = ctx.new_page()
        page.goto(ui_url + path)
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        page.evaluate("document.fonts.ready.then(() => null)")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


# --- B49.8 (C1): the usage line is for the owner and Reviewers ------------------------------------------------------

@pytest.mark.parametrize("role,shown", [("owner", True), ("reviewer", True), ("trusted", False), ("viewer", False)])
def test_b49_8_the_usage_line_shows_to_the_owner_and_reviewers_only(open_page, role, shown):
    page = open_page(role=role)
    open_chat(page)
    answer = ask(page, Q)
    expect(answer.locator(".level-used")).to_be_visible()  # the rest of the answer's line stays
    expect(answer.locator(".usage")).to_have_count(1 if shown else 0)


def test_b49_8_sign_in_off_the_one_user_is_the_owner_and_sees_it(open_page):
    page = open_page()
    open_chat(page)
    expect(ask(page, Q).locator(".usage")).to_contain_text(re.compile(r"\bin · .* out · \d+ LLM calls? · \d+ steps? · \$"))


# --- B49.9 (C2): counts in words: "1 source", never "1 sources" -------------------------------------------------------

def singular_when_one(text: str, word: str) -> None:
    n, noun = re.search(rf"(\d+) ({word}s?)\b", text).groups()
    assert (noun == word) == (n == "1"), text


def test_b49_9_the_details_button_and_usage_line_say_one_source_one_tool_call(open_page):
    page = open_page()
    open_chat(page)
    answer = ask(page, Q)
    toggle = answer.get_by_role("button", name=re.compile(r"^Show "))
    expect(toggle).to_have_text(re.compile(r"^Show \d+ sources? · \d+ tool calls?$"))
    singular_when_one(toggle.inner_text(), "source")
    singular_when_one(toggle.inner_text(), "tool call")
    usage = answer.locator(".usage").inner_text()
    singular_when_one(usage, "LLM call")
    singular_when_one(usage, "step")


# --- B49.10 (C3): the proposal's after value, the reason on its own line ----------------------------------------------

def test_b49_10_an_accepted_risk_reads_accepted_review_date_with_the_reason_under_it(open_page):
    # Patch no longer proposes accepting the research CVE (#133): the card is from "Mark accepted…" (B24)
    page = open_page()
    open_chat(page)
    row = tool_cards(ask(page, FIX_FIRST)).filter(has=page.locator(".fix-first-card")).locator(".fix-list > li").first
    cve = row.locator("strong").first.inner_text()
    row.get_by_role("button", name=f"Mark accepted… {cve}").click()
    form = row.get_by_role("form", name="Mark accepted")
    form.get_by_role("textbox", name="Reason (required)").fill("Only reachable over the VPN until the upgrade")
    form.get_by_role("button", name="Propose").click()
    card = row.locator(".proposal-card")
    expect(card.get_by_text(f"Accept the risk of {cve}", exact=True)).to_be_visible()
    after = card.locator(".before-after .after")
    expect(after).to_have_text(re.compile(r"^After: Accepted, review \d{4}-\d{2}-\d{2}$"))
    reason = card.locator(".after-line").first
    expect(reason).to_be_visible()
    assert reason.bounding_box()["y"] > after.bounding_box()["y"]  # on its own line, under the value
    assert "(" not in after.inner_text()  # no sentence in brackets inside the value
    assert text_contrast(reason, ".proposal-card") >= 4.5


# --- B49.11 (C4): a question the rate limit refused shows once: in the box ------------------------------------------

def refuse(page: Page) -> None:
    page.route("**/chat", lambda route: route.fulfill(status=429, headers=CORS, json={"error": {
        "code": "rate_limited", "message": LIMIT, "retry_at": "2026-10-16T09:01:00+00:00", "retry_after": 60}}))


@pytest.mark.parametrize("width,scheme", SIZES)
def test_b49_11_a_refused_question_is_only_in_the_box_and_the_refusal_shows_once(open_page, width, scheme):
    page = open_page(width=width, scheme=scheme)
    open_chat(page)
    ask(page, "Hello")  # an earlier turn stays
    refuse(page)
    send(page, Q)
    box = window(page).get_by_role("textbox", name="Message")
    expect(box).to_have_value(Q)  # back in the box (B20)
    expect(window(page).locator(".chat-limit")).to_have_text(LIMIT)
    expect(window(page).locator(".message.user").filter(has_text=Q)).to_have_count(0)  # not also a sent bubble
    expect(window(page).locator(".message.user")).to_have_count(1)  # "Hello" is still there
    box.press("Enter")  # refused again: still one note
    expect(box).to_have_value(Q)
    expect(window(page).locator(".chat-limit")).to_have_count(1)
    assert text_contrast(window(page).locator(".chat-limit"), ".chat-window") >= 4.5
    assert no_sideways_scroll(page)
    page.unroute("**/chat")
    send(page, Q)  # allowed again: the note goes with the next question
    expect(window(page).locator(".message.user").filter(has_text=Q)).to_have_count(1)
    expect(window(page).locator(".chat-limit")).to_have_count(0)


# --- B49.12 (C5): the conversation is kept for the tab's life -------------------------------------------------------

def test_b49_12_a_reload_keeps_the_conversation_a_new_tab_does_not(open_page, browser: Browser, ui_url: str):
    page = open_page()
    open_chat(page)
    answer = ask(page, Q)
    expect(answer.locator(".answer-text")).not_to_be_empty()
    words = answer.locator(".answer-text").inner_text()
    page.reload()
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    open_chat(page)
    expect(window(page).locator(".message.user")).to_have_text([Q])
    expect(window(page).locator(".message.assistant .answer-text")).to_have_text([words])
    expect(window(page).get_by_role("textbox", name="Message")).to_be_focused()  # not stolen by an old message
    # A new question after the reload carries on the same conversation
    ask(page, "Hello")
    expect(window(page).locator(".message.user")).to_have_count(2)
    # sessionStorage: another tab (a new browsing session here) starts empty
    other = open_page()
    open_chat(other)
    expect(window(other).locator(".message")).to_have_count(0)
    # New chat clears it for the reload too
    window(page).get_by_role("button", name="New chat").click()
    page.reload()
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    open_chat(page)
    expect(window(page).locator(".message")).to_have_count(0)


def test_b49_12_with_storage_blocked_the_chat_still_works(open_page):
    page = open_page(init_script=NO_SESSION_STORAGE)
    open_chat(page)
    expect(ask(page, Q).locator(".answer-text")).not_to_be_empty()
    page.reload()
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    open_chat(page)
    expect(window(page).locator(".message")).to_have_count(0)  # nothing kept, nothing broken


def test_b49_12_a_kept_proposal_shows_its_state_after_the_reload(open_page, known_langflow):
    page = open_page()
    open_chat(page)
    card = ask(page, RESEARCH).locator(".proposal-card")
    card.get_by_role("button", name="Cancel").click()
    expect(card.locator(".chip.proposal-state")).to_have_text("Cancelled")
    page.reload()
    expect(page.get_by_role("heading", level=1)).to_be_visible()
    open_chat(page)
    # The stored answer still says "proposed": the card asks the server once and shows what it is now
    expect(window(page).locator(".proposal-card .chip.proposal-state")).to_have_text("Cancelled")


# --- B49.14 (O1): "Page not found" for an address the app has no page for ---------------------------------------------

def not_found(page: Page):
    return page.locator("section.not-found")


@pytest.mark.parametrize("width,scheme", SIZES)
def test_b49_14_an_unknown_address_is_page_not_found_with_the_way_back(open_page, width, scheme):
    page = open_page("/nope", width=width, scheme=scheme)
    expect(page.get_by_role("heading", level=1)).to_have_text("Page not found")
    expect(page).to_have_url(re.compile(r"/nope$"))  # the address stays as typed
    card = not_found(page)
    expect(card.get_by_role("heading", level=2)).to_have_text("Patch has no page here")
    expect(card).to_contain_text("Nothing lives at /nope.")
    expect(page.locator(".side-link[aria-current=page]")).to_have_count(0)  # no page of the sidebar is this one
    settled(card)
    robot, box = card.locator("svg.robot").bounding_box(), card.bounding_box()
    assert robot["y"] < box["y"], "Patch's head over the card's top edge (§5.8)"
    assert box["x"] >= 0 and box["x"] + box["width"] <= width
    found = low_contrast(page, "section.not-found")  # on the card's gradient, where the text is (test_contrast.py)
    assert not found, show(found)
    assert no_sideways_scroll(page)
    SHOTS.mkdir(exist_ok=True)
    page.screenshot(path=SHOTS / f"b49-not-found-{scheme}-{width}.png")
    card.get_by_role("link", name="Open the dashboard").click()
    expect(page.get_by_role("heading", level=1)).to_have_text("Dashboard")
    expect(page).to_have_url(re.compile(r"/$"))
    page.go_back()  # a new history entry: Back returns to the bad address
    expect(page.get_by_role("heading", level=1)).to_have_text("Page not found")


def test_b49_14_the_way_back_by_keyboard(open_page):
    page = open_page("/nope/deeper")
    link = not_found(page).get_by_role("link", name="Open the dashboard")
    link.focus()
    page.keyboard.press("Enter")
    expect(page.get_by_role("heading", level=1)).to_have_text("Dashboard")


def test_b49_14_a_long_address_is_cut_short_and_the_known_ones_still_open(open_page, ui_url):
    page = open_page("/" + "x" * 200)
    expect(not_found(page)).to_contain_text("x" * 59 + "…")
    for path, title in (("/", "Dashboard"), ("/cves", "CVEs"), ("/about", "About"), ("/cves/CVE-2025-3248", "CVE-2025-3248")):
        page.goto(ui_url + path)
        expect(page.get_by_role("heading", level=1)).to_have_text(title)


def test_b49_14_patch_is_told_no_page(open_page):
    page = open_page("/nope")
    sent: list[dict] = []
    page.on("request", lambda r: sent.append(r.post_data_json) if r.url.endswith("/chat") and r.method == "POST" else None)
    open_chat(page)
    expect(window(page).locator(".context-chip")).to_have_text("on Page not found")
    answer = ask(page, Q)
    assert "page" not in sent[-1].get("page", {}), sent[-1]  # no page of the app: none is sent
    expect(answer.locator(".context-dropped")).to_have_count(0)  # so nothing is dropped as crafted


@scene
def b49_14_page_not_found(fx):
    page = fx("open_page")("/nope", reduced=True)
    expect(not_found(page)).to_be_visible()
    still(page, "Page not found")


def test_b49_14_page_not_found_fades_up_with_normal_motion(open_page):
    page = open_page("/nope")
    names = not_found(page).evaluate("el => el.getAnimations().map(a => a.animationName)")
    assert "fade-up" in names


# --- B49.15: the KEV, New and Selected chips explain themselves by mouse, keyboard and touch -------------------------

def test_b49_15_the_kev_chip_is_a_tip_by_keyboard(open_page):
    page = open_page("/cves")
    chip = page.locator("table.cves .chip.kev").first
    expect(chip).to_have_accessible_description("In CISA KEV: known to be exploited")
    expect(chip).not_to_have_attribute("title", re.compile(".*"))  # no mouse-only title any more
    chip.focus()
    page.keyboard.press("Shift+Tab")
    page.keyboard.press("Tab")  # a keyboard focus (:focus-visible) opens it
    expect(page.get_by_role("tooltip")).to_have_text("In CISA KEV: known to be exploited")
    page.keyboard.press("Escape")
    expect(page.get_by_role("tooltip")).to_have_count(0)


def test_b49_15_the_kev_chip_on_the_cve_page_and_the_top_5_says_its_deadline(open_page):
    page = open_page("/")
    top = page.locator(".top-id .chip.kev").first
    expect(top).to_have_accessible_description(re.compile(r"^In CISA KEV: known exploited\. KEV deadline \d{4}-\d{2}-\d{2}$"))
    page2 = open_page("/cves/CVE-2025-3248")
    expect(page2.locator(".cve-title-row .chip.kev")).to_have_accessible_description(
        re.compile(r"^In CISA KEV: known exploited\. KEV deadline "))


def test_b49_15_the_selected_chip_is_a_tip_by_touch(browser: Browser, ui_url: str):
    ctx = browser.new_context(viewport={"width": PHONE, "height": 900}, has_touch=True, is_mobile=True)
    try:
        page = ctx.new_page()
        page.goto(ui_url + "/cves?product=langflow")
        ask_about(page, RESEARCH_CVE).click()
        expect(window(page)).to_be_visible()
        window(page).get_by_role("button", name="Close the chat").click()
        chip = page.locator(".chip.selected-chip")
        chip.tap()
        expect(page.get_by_role("tooltip")).to_have_text("Patch knows this is the CVE you asked about")
        chip.tap()
        expect(page.get_by_role("tooltip")).to_have_count(0)
    finally:
        ctx.close()


# --- B49.16: the CVEs per month axis on a phone ----------------------------------------------------------------------

@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b49_16_the_month_axis_labels_never_overlap(open_page, width):
    page = open_page("/", width=width)
    labels = page.get_by_role("region", name="CVEs per month", exact=True).locator("svg text.axis-label[y='174']")
    expect(labels.last).to_have_text(re.compile(r"^\d{4}-\d{2}$"))  # the latest month always shows
    boxes = sorted((b["x"], b["x"] + b["width"]) for b in (labels.nth(i).bounding_box() for i in range(labels.count())))
    for (_, end), (start, _) in zip(boxes, boxes[1:]):
        assert end <= start, boxes

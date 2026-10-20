"""README screenshots for spec B (#48). Not a test (no `test_` prefix in the file name... run it by name):

    frontend/e2e/run.sh --browser chromium readme_shots.py -s

run.sh's throwaway servers only (FakeLLM, temp state, fake Tavily, the live pair on the fake feeds), never 8000/5173.
Writes PNGs to $SHOTS_OUT (default: <repo>/.scratch/shots/) for the owner to review before anything is committed.
"""
import os
import pathlib
import re

import pytest
from playwright.sync_api import Browser, Page, expect

from landing_shots import EXAMPLE_STACK, call
from test_live import DONE_LINE

ROOT = pathlib.Path(__file__).resolve().parents[2]
OUT = pathlib.Path(os.environ.get("SHOTS_OUT", ROOT / ".scratch" / "shots"))
W, H = 1440, 900
CVE = "CVE-2025-3248"


def example_stack(api_url: str) -> None:
    call(api_url, "/state/reset", "POST", {"confirm": "reset"})
    watched = call(api_url, "/watchlist")["watchlist"]
    call(api_url, "/watchlist", "PUT", {"products": [{"product": p, **EXAMPLE_STACK.get(p, {})} for p in watched]})


@pytest.fixture
def opener(browser: Browser):
    contexts = []

    def _open(scheme: str = "light") -> Page:
        ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme=scheme, reduced_motion="reduce")
        contexts.append(ctx)
        page = ctx.new_page()
        page.add_init_script("try { localStorage.setItem('helloHidden', '1') } catch {}")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


def save(page: Page, name: str) -> None:
    page.evaluate("document.fonts.ready.then(() => null)")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path))
    print(f"wrote {path}")


def open_chat(page: Page):
    page.keyboard.press("Control+k")
    chat = page.get_by_role("complementary", name="Chat with Patch")
    chat.get_by_role("button", name="Make larger").click()
    chat.get_by_role("button", name="Pin: dock the chat beside the page").click()
    return chat


def ask(chat, text: str):
    before = chat.locator(".message.assistant").count()
    box = chat.get_by_role("textbox", name="Message")
    box.fill(text)
    box.press("Enter")
    expect(chat.locator(".message.assistant")).to_have_count(before + 1, timeout=15_000)
    return chat.locator(".message.assistant").nth(before)


def chat_top(page: Page, chat) -> None:
    chat.locator(".message.user").first.evaluate(
        """el => { let box = el.parentElement
                   while (box && box.scrollHeight <= box.clientHeight) box = box.parentElement
                   if (box) box.scrollTop = 0 }""")
    page.evaluate("window.scrollTo(0, 0)")


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_dashboard(opener, ui_url, api_url, scheme):
    example_stack(api_url)
    page = opener(scheme)
    page.goto(ui_url + "/")
    expect(page.locator(".tile")).to_have_count(4)
    expect(page.locator("svg[aria-label='Open CVEs by product and severity']")).to_be_visible()
    save(page, f"dashboard-{scheme}")


def test_pages(opener, ui_url, api_url):
    example_stack(api_url)
    page = opener()
    page.goto(ui_url + "/cves")
    expect(page.locator("tbody tr").first).to_be_visible()
    save(page, "cves-light")

    page.goto(ui_url + "/settings")
    expect(page.get_by_role("heading", level=1, name="Settings")).to_be_visible()
    expect(page.locator("section.card").first).to_be_visible()
    save(page, "settings-light")

    page.goto(ui_url + "/about")
    expect(page.get_by_role("heading", level=1).first).to_be_visible()
    save(page, "landing-light")

    page.goto(ui_url + f"/cves/{CVE}")
    expect(page.get_by_role("heading", level=1, name=CVE)).to_be_visible()
    save(page, "cve-page-light")


def test_chat(opener, ui_url, api_url):
    example_stack(api_url)
    page = opener()
    page.goto(ui_url + f"/cves/{CVE}")
    expect(page.get_by_role("heading", level=1, name=CVE)).to_be_visible()
    chat = open_chat(page)
    answer = ask(chat, f"Am I affected by {CVE}?")
    answer.get_by_role("button", name=re.compile(r"^Show")).first.click()
    answer.get_by_role("tab", name="Tool calls", exact=False).click()
    chat_top(page, chat)
    save(page, "chat-light")


def test_web_research(opener, ui_url, api_url):
    example_stack(api_url)
    page = opener()
    page.goto(ui_url + "/")
    expect(page.locator(".tile")).to_have_count(4)
    chat = open_chat(page)
    answer = ask(chat, f"Who's talking about {CVE} on the web?")
    answer.get_by_role("button", name=re.compile(r"^Show")).first.click()
    answer.get_by_role("tab", name="Tool calls", exact=False).click()
    expect(answer.locator(".research-card")).to_be_visible()
    answer.locator(".research-card").scroll_into_view_if_needed()
    page.evaluate("window.scrollTo(0, 0)")
    save(page, "web-research-light")


def test_check_now(browser: Browser, live_ui_url, live_api_url):
    call(live_api_url, "/refresh/reset", "POST", {"confirm": "reset"})
    call(live_api_url, "/state/reset", "POST", {"confirm": "reset"})
    ctx = browser.new_context(viewport={"width": W, "height": H}, color_scheme="light", reduced_motion="reduce")
    page = ctx.new_page()
    page.add_init_script("try { localStorage.setItem('helloHidden', '1') } catch {}")
    try:
        page.goto(live_ui_url + "/settings")
        card = page.locator("section.card", has=page.get_by_role("heading", name="Refresh runs", exact=True))
        card.get_by_role("button", name="Check now").click()
        expect(card.get_by_role("status")).to_have_text(DONE_LINE, timeout=30_000)
        card.scroll_into_view_if_needed()
        save(page, "check-now-settings-light")
        page.goto(live_ui_url + "/")
        fresh = page.get_by_role("region", name="Data freshness")
        expect(fresh).to_be_visible()
        fresh.scroll_into_view_if_needed()
        save(page, "check-now-dashboard-light")
    finally:
        ctx.close()
        call(live_api_url, "/refresh/reset", "POST", {"confirm": "reset"})
        call(live_api_url, "/state/reset", "POST", {"confirm": "reset"})

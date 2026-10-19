"""The landing page's screenshots (B42, #80): the dashboard, the CVEs page and Patch answering, light and dark.

Not part of the browser check (the file name doesn't start with `test_`, so the check never collects it). Run it on
its own, through run.sh's throwaway servers (FakeLLM, the example watchlist, a temp state file; never 8000/5173):

    scripts/landing-shots.sh

It writes six WebP images to frontend/src/landing/shots/, where the landing page imports them (Vite hashes the
names, so a re-take is never served from an old cache). Re-run it after a change to those pages (#93 to #96), look
at the six images, and commit them.

Each shot: a 1280 x 800 window at device scale 1, reduced motion (charts and Patch drawn still, in their final
pose), the welcome banner closed so the tiles and charts show. The PNG is turned into WebP by the browser itself
(canvas.toBlob), so no image tool is needed.
"""
import base64
import json
import pathlib
import re
import urllib.request

import pytest
from playwright.sync_api import Browser, Page, expect

OUT = pathlib.Path(__file__).resolve().parents[1] / "src" / "landing" / "shots"
WIDTH, HEIGHT = 1280, 800
QUALITY = 0.8  # WebP quality: text stays sharp, each image about 40 to 90 KB
CVE = "CVE-2025-3248"  # Langflow, on the example watchlist and in CISA KEV
QUESTION = f"Am I affected by {CVE}?"  # FakeLLM answers it with the verdict and its sources


# How the example team runs two of its products (made up; fixed so the shots look the same each time)
EXAMPLE_STACK = {
    "langflow": {"usage": "self_hosted", "version": "1.2.0", "internet_facing": True},
    "litellm": {"usage": "self_hosted", "version": "1.80.0", "internet_facing": False},
}


def call(api_url: str, path: str, method: str = "GET", body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(api_url + path, data=data, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def to_webp(page: Page, png: bytes) -> bytes:
    """The PNG as WebP, encoded by the browser (Chromium encodes WebP on a canvas)."""
    data = page.evaluate(
        """async ([src, q]) => {
            const img = new Image()
            img.src = src
            await img.decode()
            const canvas = document.createElement('canvas')
            canvas.width = img.naturalWidth
            canvas.height = img.naturalHeight
            canvas.getContext('2d').drawImage(img, 0, 0)
            const blob = await new Promise((done) => canvas.toBlob(done, 'image/webp', q))
            if (!blob || blob.type !== 'image/webp') throw new Error('this browser cannot encode WebP: use Chromium')
            const bytes = new Uint8Array(await blob.arrayBuffer())
            let s = ''
            for (const b of bytes) s += String.fromCharCode(b)
            return btoa(s)
        }""",
        ["data:image/png;base64," + base64.b64encode(png).decode(), QUALITY],
    )
    return base64.b64decode(data)


def save(page: Page, name: str, scheme: str) -> None:
    page.evaluate("document.fonts.ready.then(() => null)")
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{name}-{scheme}.webp"
    path.write_bytes(to_webp(page, page.screenshot()))
    print(f"wrote {path} ({path.stat().st_size // 1024} KB)")


@pytest.fixture
def shot_page(browser: Browser, ui_url: str, api_url: str):
    """A fresh window per theme, on the example data: reset first (so earlier runs can't leak in), then two
    versions set, so the verdicts say "Affected" instead of "no version given"."""
    call(api_url, "/state/reset", "POST", {"confirm": "reset"})
    watched = call(api_url, "/watchlist")["watchlist"]
    call(api_url, "/watchlist", "PUT", {"products": [{"product": p, **EXAMPLE_STACK.get(p, {})} for p in watched]})
    contexts = []

    def _open(scheme: str) -> Page:
        ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1,
                                  color_scheme=scheme, reduced_motion="reduce")
        contexts.append(ctx)
        page = ctx.new_page()
        page.add_init_script("try { localStorage.setItem('helloHidden', '1') } catch {}")
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_take_landing_shots(shot_page, ui_url, scheme):
    page = shot_page(scheme)

    # The dashboard: tiles, charts, Top 5
    page.goto(ui_url + "/")
    expect(page.get_by_role("heading", level=1, name="Dashboard")).to_be_visible()
    expect(page.locator(".tile")).to_have_count(4)
    expect(page.locator("svg[aria-label='Open CVEs by product and severity']")).to_be_visible()
    save(page, "dashboard", scheme)

    # The CVEs page: the list with verdicts, priorities and due dates
    page.goto(ui_url + "/cves")
    expect(page.get_by_role("heading", level=1, name="CVEs")).to_be_visible()
    expect(page.locator("tbody tr").first).to_be_visible()
    save(page, "cves", scheme)

    # Patch answering: on the CVE's page, the chat pinned beside it, a short question with its sources open
    page.goto(ui_url + f"/cves/{CVE}")
    expect(page.get_by_role("heading", level=1, name=CVE)).to_be_visible()
    page.keyboard.press("Control+k")
    chat = page.get_by_role("complementary", name="Chat with Patch")
    chat.get_by_role("button", name="Make larger").click()
    chat.get_by_role("button", name="Pin: dock the chat beside the page").click()
    box = chat.get_by_role("textbox", name="Message")
    box.fill(QUESTION)
    box.press("Enter")
    expect(chat.locator(".message.assistant")).to_have_count(1, timeout=15_000)
    chat.get_by_role("button", name=re.compile(r"^Show \d+ sources")).first.click()
    expect(chat.get_by_role("tab", name="Sources")).to_be_visible()
    # the chat's own scroll back to the question (not the page's), so the question, the answer and its first
    # sources show together
    chat.locator(".message.user").first.evaluate(
        """el => { let box = el.parentElement
                   while (box && box.scrollHeight <= box.clientHeight) box = box.parentElement
                   if (box) box.scrollTop = 0 }""")
    page.evaluate("window.scrollTo(0, 0)")
    save(page, "chat", scheme)

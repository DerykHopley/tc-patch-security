"""The link-preview image (B61, #108): the picture a chat app shows in the card for a link to `/` or `/about`.

Not part of the browser check (the file name doesn't start with `test_`, so the check never collects it). Run it on
its own, through run.sh's throwaway servers (never 8000/5173):

    scripts/link-preview-image.sh

It writes frontend/public/link-preview/patch.png (1200 x 630, the size Open Graph cards use), which the build copies
to dist/link-preview/patch.png, where the server's tags point (backend/app/link_preview.py). Look at it, then commit.

How: it opens About in light mode with reduced motion, so the page's own tokens, fonts and Patch (the real robot
component, in a fixed idle pose) are loaded, then draws the card over the page from them and takes a screenshot.
Light, because previews show on light and dark chat backgrounds alike, and the light look is the landing page's
first impression. Big type only: the card is often shown at a few hundred pixels wide.
"""
import pathlib

from playwright.sync_api import Browser, expect

OUT = pathlib.Path(__file__).resolve().parents[1] / "public" / "link-preview" / "patch.png"
WIDTH, HEIGHT = 1200, 630

CARD = """
<div class="og-card">
  <div class="og-text">
    <div class="og-brand"><span class="og-mark">SHIELD</span><span class="og-name">Patch</span></div>
    <p class="og-line">Security flaws in your LLM stack, tracked for you</p>
    <p class="og-sub">The LLM-security assistant</p>
    <div class="og-tiles"><span class="t1">Watch</span><span class="t2">Judge</span><span class="t3">Alert</span><span class="t4">Ask</span></div>
  </div>
  <div class="og-art">ROBOT</div>
</div>
"""

STYLE = """
.og-card { position: fixed; inset: 0; z-index: 99999; width: 1200px; height: 630px; box-sizing: border-box;
  display: grid; grid-template-columns: 1fr 400px; align-items: center; gap: 24px; padding: 64px 72px;
  background: var(--page-glow), linear-gradient(120deg, var(--surface) 35%, var(--accent-soft));
  background-color: var(--bg); font-family: var(--font-body); color: var(--text); }
.og-brand { display: flex; align-items: center; gap: 22px; }
.og-mark { display: grid; place-items: center; width: 96px; height: 96px; border-radius: 28px;
  background: var(--gradient-primary); color: var(--on-primary); box-shadow: 0 14px 30px rgba(108, 76, 245, .28); }
.og-mark svg { width: 56px; height: 56px; }
.og-name { font-family: var(--font-display); font-weight: 700; font-size: 112px; line-height: 1; color: var(--accent); }
.og-line { margin: 34px 0 0; font-family: var(--font-display); font-weight: 600; font-size: 50px; line-height: 1.12;
  color: var(--text); max-width: 640px; }
.og-sub { margin: 18px 0 0; font-size: 30px; font-weight: 700; color: var(--muted); }
.og-tiles { display: flex; gap: 12px; margin-top: 34px; }
.og-tiles span { padding: 10px 22px; border-radius: 999px; color: #fff; font-weight: 800; font-size: 24px; }
.og-tiles .t1 { background: linear-gradient(135deg, #5b3fe0 35%, #8b6cff); }
.og-tiles .t2 { background: linear-gradient(135deg, #c24a0a 35%, #f5933f); }
.og-tiles .t3 { background: linear-gradient(135deg, #c42a50 35%, #ff6b8b); }
.og-tiles .t4 { background: linear-gradient(135deg, #26265f 35%, #4a4aa8); }
.og-art { display: grid; place-items: center; }
.og-art svg.robot { width: 380px; height: auto; }
"""


def test_make_link_preview_image(browser: Browser, ui_url: str):
    ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1,
                              color_scheme="light", reduced_motion="reduce")
    page = ctx.new_page()
    page.add_init_script("Math.random = () => 0")  # Patch's idle pose is picked at random: the first, every time
    page.goto(ui_url + "/about")
    robot = page.locator(".landing-art svg.robot").first
    expect(robot).to_be_visible()
    page.evaluate("document.fonts.ready.then(() => null)")
    page.evaluate(
        """([card, style]) => {
            const robot = document.querySelector('.landing-art svg.robot').outerHTML
            const shield = document.querySelector('.brand-mark svg').outerHTML
            const css = document.createElement('style')
            css.textContent = style
            document.head.append(css)
            const box = document.createElement('div')
            box.innerHTML = card.replace('ROBOT', robot).replace('SHIELD', shield)
            document.body.append(box.firstElementChild)
        }""",
        [CARD, STYLE],
    )
    page.evaluate("document.fonts.ready.then(() => null)")  # Fredoka at the card's sizes
    OUT.parent.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(OUT), clip={"x": 0, "y": 0, "width": WIDTH, "height": HEIGHT}, animations="disabled")
    size = OUT.stat().st_size
    print(f"wrote {OUT} ({size // 1024} KB)")
    assert size < 1_000_000
    ctx.close()

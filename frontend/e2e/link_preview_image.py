"""The link-preview image (B61, #108): the picture a chat app shows in the card for a link to `/` or `/about`.

Not part of the browser check (the file name doesn't start with `test_`, so the check never collects it). Run it on
its own, through run.sh's throwaway servers (never 8000/5173):

    scripts/link-preview-image.sh

It writes frontend/public/link-preview/patch.png (1200 x 630, the size Open Graph cards use), which the build copies
to dist/link-preview/patch.png, where the server's tags point (backend/app/link_preview.py). Look at it, then commit.

What: the launch video's last screen (the owner's choice), redrawn at 1200 x 630 rather than cropped from the 16:9
video, so it stays sharp and Patch stays inside the frame. How: it opens About in light mode with reduced motion, so
the page's own tokens, fonts, app icon and Patch (the real robot component: the end card's, happy, in a fixed pose)
are loaded, then draws the card over the page from them and takes a screenshot. Light, because previews show on
light and dark chat backgrounds alike. Big type only: the card is often shown at a few hundred pixels wide.
"""
import pathlib

from playwright.sync_api import Browser, expect

OUT = pathlib.Path(__file__).resolve().parents[1] / "public" / "link-preview" / "patch.png"
WIDTH, HEIGHT = 1200, 630

CARD = """
<div class="og-card">
  <div class="og-brand"><span class="og-mark">SHIELD</span><span class="og-name">Patch.</span></div>
  <p class="og-verbs"><span>Watch.</span><span>Judge.</span><span>Alert.</span><span>Ask.</span></p>
  <p class="og-repo">github.com/DerykHopley/tc-patch-security</p>
  <div class="og-art">ROBOT</div>
</div>
"""

# The launch video's last screen (B47, its light cut), laid out for 1.91:1: the app icon and "Patch." in dark
# Fredoka, the four verbs in accent purple, the repo address, Patch happy in the bottom right, on the page's soft
# lavender background. Larger type than the video, and a larger Patch, for a card a few hundred pixels wide.
STYLE = """
.og-card { position: fixed; inset: 0; z-index: 99999; width: 1200px; height: 630px; box-sizing: border-box;
  display: flex; flex-direction: column; align-items: center; justify-content: center; padding-bottom: 20px;
  background: var(--page-glow), var(--bg); font-family: var(--font-body); color: var(--text); }
.og-brand { display: flex; align-items: center; gap: 30px; }
.og-mark { display: grid; place-items: center; width: 132px; height: 132px; border-radius: 34px;
  background: var(--gradient-primary); color: var(--on-primary); box-shadow: 0 16px 34px rgba(108, 76, 245, .28); }
.og-mark svg { width: 74px; height: 74px; }
.og-name { font-family: var(--font-display); font-weight: 700; font-size: 150px; line-height: 1; color: var(--text); }
.og-verbs { display: flex; gap: 34px; margin: 44px 0 0; font-family: var(--font-display); font-weight: 700;
  font-size: 58px; line-height: 1; color: var(--accent); }
.og-repo { margin: 40px 0 0; font-size: 30px; font-weight: 700; color: var(--muted); }
.og-art { position: absolute; right: 44px; bottom: 30px; }
.og-art svg.robot { width: 140px; height: auto; }
"""


def test_make_link_preview_image(browser: Browser, ui_url: str):
    ctx = browser.new_context(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1,
                              color_scheme="light", reduced_motion="reduce")
    page = ctx.new_page()
    page.add_init_script("Math.random = () => 0")  # Patch's happy pose is picked at random: the first, every time
    page.goto(ui_url + "/about")
    robot = page.locator(".landing-end svg.robot").first
    expect(robot).to_be_visible()
    page.evaluate("document.fonts.ready.then(() => null)")
    page.evaluate(
        """([card, style]) => {
            const robot = document.querySelector('.landing-end svg.robot').outerHTML
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

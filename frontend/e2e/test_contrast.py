"""Measured text contrast on every page (B49, #96; extends A02.3). Check ids: B49.20.

The page review judged colours by eye. This measures every piece of text the browser draws on each page, in light
and dark, at a phone's width and a desktop's, against WCAG 2's AA rule: 4.5:1, or 3:1 for large text (at least 24px,
or 18.66px and bold). A02.3 (test_shell.py) checks the token pairs; this checks what the pages actually put together.

How one text is measured (TEXT_CONTRAST below):
- Text: each visible element with its own text (an HTML element's `color`, an SVG text's `fill`), with the opacity of
  it and its ancestors applied. Not measured: text in `aria-hidden` (decorative: icons, Patch's arrows), visually
  hidden text (screen readers only), disabled controls and their fieldsets (WCAG exempts them), and form controls'
  typed values and placeholders (no text node).
- Background: the element's fills and its ancestors', composited until an opaque one. Under a linear gradient (a
  candy tile, a primary button, the welcome look) the gradient's colour is worked out where the text is (its four
  corners and middle): the text must pass on the worst of them. Another gradient counts each colour stop. The page's
  own background is `--bg` (the body's soft glows, fixed in two corners, are left out, as DESIGN.md §3.1 measures it).
- Two things this can't see: text over a picture (none in the app; the landing page's screenshots carry no text of
  ours), and text overlapping a sibling that isn't its ancestor (a floating bubble is measured on its own fill).
Expected values come from WCAG, not from the CSS.
"""
import pytest
from playwright.sync_api import Browser, Page, expect

from test_chat import ask, open_chat, window
from test_shell import settled

PHONE, DESKTOP = 390, 1440

# Pages by address. The CVE page is the dashboard's KEV example (B35); "/nope" is "Page not found" (B49).
PAGES = ["/", "/cves", "/cves/CVE-2025-3248", "/settings", "/dev", "/about", "/nope"]

TEXT_CONTRAST = """({ root, pending }) => {
  const ctx = document.createElement('canvas').getContext('2d', { willReadFrequently: true })
  // Any CSS colour (rgb(), color(srgb …), oklch …) as [r, g, b, a] in 0..255 and 0..1, through the canvas
  const rgba = (c) => {
    ctx.clearRect(0, 0, 1, 1)
    ctx.fillStyle = 'rgba(0, 0, 0, 0)'
    ctx.fillStyle = c
    ctx.fillRect(0, 0, 1, 1)
    const [r, g, b, a] = ctx.getImageData(0, 0, 1, 1).data
    return a === 0 ? [0, 0, 0, 0] : [r, g, b, a / 255]
  }
  const over = (top, under) => {
    const a = top[3]
    return [0, 1, 2].map((i) => top[i] * a + under[i] * (1 - a)).concat(1)
  }
  const lum = (c) => {
    const [r, g, b] = c.slice(0, 3).map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 })
    return 0.2126 * r + 0.7152 * g + 0.0722 * b
  }
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05) }
  const COLOR = /(rgba?\\([^)]*\\)|color\\([^)]*\\)|oklch\\([^)]*\\)|oklab\\([^)]*\\)|#[0-9a-f]{3,8}\\b)/gi
  const page = rgba(getComputedStyle(document.body).backgroundColor)[3] > 0
    ? rgba(getComputedStyle(document.body).backgroundColor) : rgba(getComputedStyle(document.documentElement).backgroundColor)

  // Splits at the top level's commas: "linear-gradient(135deg, rgb(1, 2, 3) 35%, …)" → its parts
  const parts = (text) => {
    const out = []
    let depth = 0, from = 0
    for (let i = 0; i < text.length; i++) {
      if (text[i] === '(') depth++
      else if (text[i] === ')') depth--
      else if (text[i] === ',' && depth === 0) { out.push(text.slice(from, i).trim()); from = i + 1 }
    }
    out.push(text.slice(from).trim())
    return out
  }
  // A linear gradient's colours at the text's points (CSS Images 3: the gradient line through the box's middle at the
  // given angle, 0deg pointing up), or null when it isn't one this reads (then every stop counts)
  const SIDES = { 'to top': 0, 'to right': 90, 'to bottom': 180, 'to left': 270 }
  const linearAt = (img, box, points) => {
    const m = /^linear-gradient\\((.*)\\)$/.exec(parts(img)[0])
    if (!m) return null
    const args = parts(m[1])
    let angle = 180
    if (/deg$/.test(args[0])) angle = parseFloat(args.shift())
    else if (args[0] in SIDES) angle = SIDES[args.shift()]
    else if (/^to /.test(args[0])) return null
    const stops = args.map((a) => {
      const pos = /\\s(-?[\\d.]+)%$/.exec(a)
      return { c: rgba(pos ? a.slice(0, pos.index) : a), at: pos ? parseFloat(pos[1]) / 100 : null }
    })
    stops[0].at ??= 0
    stops[stops.length - 1].at ??= 1
    for (let i = 1; i < stops.length - 1; i++) {
      if (stops[i].at !== null) continue
      let j = i
      while (stops[j].at === null) j++
      for (let k = i; k < j; k++) stops[k].at = stops[i - 1].at + ((stops[j].at - stops[i - 1].at) * (k - i + 1)) / (j - i + 1)
    }
    const rad = (angle * Math.PI) / 180
    const [dx, dy] = [Math.sin(rad), -Math.cos(rad)]
    const len = Math.abs(box.width * dx) + Math.abs(box.height * dy)
    const [cx, cy] = [box.left + box.width / 2, box.top + box.height / 2]
    return points.map(([x, y]) => {
      const t = ((x - cx) * dx + (y - cy) * dy) / len + 0.5
      if (t <= stops[0].at) return stops[0].c
      for (let i = 1; i < stops.length; i++) {
        if (t <= stops[i].at) {
          const f = (t - stops[i - 1].at) / (stops[i].at - stops[i - 1].at || 1)
          return stops[i].c.map((v, k) => stops[i - 1].c[k] + (v - stops[i - 1].c[k]) * f)
        }
      }
      return stops[stops.length - 1].c
    })
  }

  // The backgrounds behind an element: each a fully composited colour (several when a gradient is in the way)
  const backgrounds = (el) => {
    const r = el.getBoundingClientRect()
    const points = [[r.left + 1, r.top + 1], [r.right - 1, r.top + 1], [r.left + 1, r.bottom - 1],
      [r.right - 1, r.bottom - 1], [(r.left + r.right) / 2, (r.top + r.bottom) / 2]]
    const layers = [] // nearest first: { colours: [rgba...] }
    for (let n = el; n && n !== document.body && n !== document.documentElement; n = n.parentElement) {
      const s = getComputedStyle(n)
      const img = s.backgroundImage
      if (img && img !== 'none' && /gradient/.test(img)) {
        const stops = linearAt(img, n.getBoundingClientRect(), points)
          ?? (img.match(COLOR) || []).map(rgba).filter((c) => c[3] > 0)
        const fill = rgba(s.backgroundColor)
        if (stops.length) layers.push(stops.map((c) => (fill[3] > 0 ? over(c, fill) : c)))
        if (stops.length && stops.every((c) => c[3] >= 1)) break
        if (fill[3] >= 1) break
        continue
      }
      const fill = rgba(s.backgroundColor)
      if (fill[3] > 0) layers.push([fill])
      if (fill[3] >= 1) break
    }
    let out = [page]
    for (const layer of layers.reverse()) out = out.flatMap((under) => layer.map((c) => over(c, under)))
    return out
  }

  const hidden = (el) => {
    if (el.closest('[aria-hidden="true"], .visually-hidden, [hidden]')) return true
    if (el.closest(':disabled, [aria-disabled="true"], fieldset:disabled')) return true
    const r = el.getBoundingClientRect()
    if (r.width < 2 || r.height < 2) return true
    if (el.checkVisibility && !el.checkVisibility({ checkOpacity: true, checkVisibilityCSS: true })) return true
    for (let n = el; n; n = n.parentElement) {
      const s = getComputedStyle(n)
      if (s.clip === 'rect(0px, 0px, 0px, 0px)' || s.clipPath === 'inset(50%)') return true
    }
    return false
  }

  const found = []
  const seen = new Set()
  const walker = document.createTreeWalker(document.querySelector(root), NodeFilter.SHOW_TEXT)
  for (let t = walker.nextNode(); t; t = walker.nextNode()) {
    const el = t.parentElement
    if (!el || seen.has(el) || !t.textContent.trim()) continue
    seen.add(el)
    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'TITLE', 'OPTION'].includes(el.tagName) || hidden(el)) continue
    const s = getComputedStyle(el)
    const svg = el instanceof SVGElement
    let fg = rgba(svg ? s.fill : s.color)
    let alpha = fg[3]
    for (let n = el; n; n = n.parentElement) alpha *= Number(getComputedStyle(n).opacity)
    if (alpha === 0) continue
    fg = [fg[0], fg[1], fg[2], alpha]
    const size = parseFloat(s.fontSize)
    const large = size >= 24 || (size >= 18.66 && Number(s.fontWeight) >= 700)
    const need = large ? 3 : 4.5
    const worst = Math.min(...backgrounds(el).map((bg) => ratio(over(fg, bg), bg)))
    if (worst < need) {
      const path = []
      for (let n = el; n && n !== document.body && path.length < 4; n = n.parentElement) {
        path.unshift(n.tagName.toLowerCase() + (n.classList.length ? '.' + [...n.classList].join('.') : ''))
      }
      found.push({ pending: Boolean(el.closest(pending)), where: path.join(' > '), text: t.textContent.trim().slice(0, 50), ratio: Math.round(worst * 100) / 100,
        need, fg: s.color || s.fill, size })
    }
  }
  return found
}"""


# Design calls waiting for the owner (B49 report, #96): measured under AA, but the fix changes a brand colour, so it
# isn't made here. Left out of the page checks and kept by the strict xfail below, which fails once they pass, so
# this list can't outlive the fix.
# - The candy tiles (dashboard, landing page): their labels run from the deep start of the gradient into the bright
#   end (§5.1 measured them on the deep colour only): 2.5 to 4.1:1 where the text ends, worst on a phone.
PENDING = ".tile, .landing-tile"


def low_contrast(page: Page, root: str = "body") -> list[dict]:
    """Every text under `root` below WCAG AA, with where it is, its words, its ratio, what it needed, and whether it
    is a pending design call (PENDING)."""
    return page.evaluate(TEXT_CONTRAST, {"root": root, "pending": PENDING})


def show(found: list[dict]) -> str:
    return "\n".join(f"{f['ratio']}:1 (needs {f['need']}) {f['where']}: {f['text']!r}" for f in found)


@pytest.fixture
def open_at(browser: Browser, ui_url: str):
    contexts = []

    def _open(path: str, width: int, scheme: str) -> Page:
        ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
        contexts.append(ctx)
        page = ctx.new_page()
        page.goto(ui_url + path)
        expect(page.get_by_role("heading", level=1)).to_be_visible()
        page.wait_for_load_state("networkidle")  # the page's data has loaded: its text is all there
        page.evaluate("document.fonts.ready.then(() => null)")
        settled(page.locator("body"))  # the cards' fade up is over: no text is half transparent
        return page

    yield _open
    for ctx in contexts:
        ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
@pytest.mark.parametrize("path", PAGES)
def test_b49_20_every_text_on_every_page_meets_wcag_aa(open_at, path, width, scheme):
    page = open_at(path, width, scheme)
    found = [f for f in low_contrast(page) if not f["pending"]]
    assert not found, f"{path} at {width}px, {scheme}:\n{show(found)}"


@pytest.mark.xfail(strict=True, reason="design call for the owner: the candy tiles' text on the bright end (B49)")
@pytest.mark.parametrize("path", ["/", "/about"])
def test_b49_20_pending_design_call_the_candy_tiles(open_at, path):
    page = open_at(path, PHONE, "light")
    found = [f for f in low_contrast(page) if f["pending"]]
    assert not found, show(found)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [PHONE, DESKTOP])
def test_b49_20_the_chat_with_an_answer_and_its_details(open_at, width, scheme):
    page = open_at("/", width, scheme)
    open_chat(page)
    answer = ask(page, "What is prompt injection?")
    answer.get_by_role("button", name="Show").click()
    settled(window(page))
    found = low_contrast(page, ".chat-window")  # on a phone the sheet covers the page: only the chat is seen
    assert not found, f"the chat at {width}px, {scheme}:\n{show(found)}"

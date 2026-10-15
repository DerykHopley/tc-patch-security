"""The report's charts: plain inline SVG, drawn here, no library (the page loads nothing from anywhere).

Each chart is a <figure>: the SVG (role="img", named by its <title> and <desc>), a caption, and the data as a table
under "Show as table". Colours come from the design tokens through CSS classes (CHART_STYLE), so dark mode follows
the theme toggle. The SVGs have a fixed viewBox and a minimum width: on a narrow screen they scroll inside their card
instead of shrinking the text. Nothing moves (no animation): a report is read, not watched.

Series follow DESIGN.md §3.2's categorical order: the first is --cat-1 (purple, circles), the second --cat-2
(orange, squares). Colour is never alone: the shape differs too, and every chart has a legend.
"""
import math
from html import escape

CHART_STYLE = """
figure.chart { margin: 0.6rem 0 1rem; }
figure.chart figcaption { color: var(--muted); font-size: 0.82rem; margin-top: 0.3rem; }
.chart-scroll { overflow-x: auto; }
.chart-scroll svg { display: block; width: 100%; height: auto; }
figure.chart [hidden] { display: none; }
.scroll-hint { display: none; color: var(--muted); font-size: 0.78rem; margin: 0.2rem 0; }
@media (max-width: 760px) { .scroll-hint { display: block; } }
svg text { fill: var(--text); font-family: var(--font-body); font-size: 12px; }
svg text.axis, svg text.lane { fill: var(--muted); }
svg text.axis-title { fill: var(--muted); font-weight: 700; }
svg .gridline { stroke: var(--grid); stroke-width: 1; }
svg .baseline { stroke: var(--muted); stroke-width: 1; }
svg .lane-fill { fill: var(--nested-fill); }
svg .leader { stroke: var(--muted); stroke-width: 1; }
svg .mark { stroke: var(--surface); stroke-width: 2; }
.chart-pair { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 0.4rem 1.5rem; }
.chart-pair h4 { margin: 0 0 0.2rem; font-size: 0.88rem; }
svg .s1, svg .cloud, svg .on-topic { fill: var(--cat-1); }
svg .s2, svg .local, svg .off-topic { fill: var(--cat-2); }
svg .threshold { stroke: var(--text); stroke-width: 2; stroke-dasharray: 5 3; }
.legend { display: flex; flex-wrap: wrap; gap: 0.3rem 1rem; font-size: 0.82rem; margin: 0.3rem 0; }
.legend span { display: inline-flex; align-items: center; gap: 0.35rem; }
.legend svg { width: 12px; height: 12px; }
.switch { display: inline-flex; gap: 0.3rem; margin: 0.2rem 0 0.4rem; }
.switch button { font-size: 0.82rem; padding: 0.15rem 0.8rem; }
.switch button[aria-pressed='true'] { background: var(--accent-soft); border-color: var(--accent); }
details.as-table > summary { cursor: pointer; color: var(--accent); font-weight: 700; font-size: 0.82rem; }
"""

SWITCH_SCRIPT = """
document.querySelectorAll('[data-switch]').forEach(group => {
  group.hidden = false;
  const buttons = group.querySelectorAll('button');
  buttons.forEach(b => b.addEventListener('click', () => {
    buttons.forEach(o => {
      o.setAttribute('aria-pressed', String(o === b));
      // toggleAttribute, not .hidden: the charts are <svg>s, and only HTML elements have .hidden
      document.getElementById(o.dataset.show).toggleAttribute('hidden', o !== b);
    });
  }));
});
"""

FONT_W = 6.6  # px per character at 12px, roughly: enough to keep labels apart
LINE = 15


def _e(value) -> str:
    return escape(str(value))


def _f(x: float) -> str:
    return f"{x:.1f}".rstrip("0").rstrip(".")


def nice_ticks(hi: float, count: int = 5) -> list[float]:
    """0, step, 2·step … up to at least `hi`, with a step of 1, 2, 2.5 or 5 × a power of ten."""
    if hi <= 0:
        return [0.0, 1.0]
    raw = hi / count
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if m * mag >= raw)
    n = math.ceil(hi / step - 1e-9)
    return [round(i * step, 12) for i in range(n + 1)]


def legend(items: list[tuple[str, str, str]]) -> str:
    """(shape, css class, label): a key that shows the shape as well as the colour."""
    out = ""
    for shape, cls, label in items:
        mark = (f'<circle class="{cls}" cx="6" cy="6" r="5"/>' if shape == "circle"
                else f'<rect class="{cls}" x="1" y="1" width="10" height="10" rx="2"/>')
        out += f'<span><svg viewBox="0 0 12 12" aria-hidden="true">{mark}</svg>{_e(label)}</span>'
    return f'<div class="legend">{out}</div>'


def _mark(shape: str, cls: str, x: float, y: float, size: float = 6) -> str:
    if shape == "circle":
        return f'<circle class="mark {cls}" cx="{_f(x)}" cy="{_f(y)}" r="{_f(size)}"/>'
    return (f'<rect class="mark {cls}" x="{_f(x - size)}" y="{_f(y - size)}" width="{_f(2 * size)}" '
            f'height="{_f(2 * size)}" rx="2"/>')


def _svg(svg_id: str, width: int, height: int, title: str, desc: str, body: str, hidden: bool = False,
         min_width: int = 680) -> str:
    """min_width keeps 12px text at 10px or more on a narrow screen (the card scrolls); max_width stops it growing
    past about 14px on a wide one."""
    return (f'<svg id="{svg_id}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="{svg_id}-t {svg_id}-d" '
            f'style="min-width: {min_width}px; max-width: {round(width * 1.15)}px"{" hidden" if hidden else ""}>'
            f'<title id="{svg_id}-t">{_e(title)}</title>'
            f'<desc id="{svg_id}-d">{_e(desc)}</desc>{body}</svg>')


def figure(chart: str, caption: str, table: str, before: str = "", wide: bool = True) -> str:
    hint = '<p class="scroll-hint">Scroll sideways for the whole chart.</p>' if wide else ""
    return (f'<figure class="chart">{before}{hint}<div class="chart-scroll">{chart}</div>'
            f'<figcaption>{caption}</figcaption>'
            f'<details class="as-table"><summary>Show as table</summary>{table}</details></figure>')


def _place_labels(points: list[dict], left: float, right: float, top: float, bottom: float) -> list[dict]:
    """A label beside each point, nudged up or down (or to the left) until it overlaps no other label or mark."""
    boxes = [(p["x"] - 7, p["y"] - 7, p["x"] + 7, p["y"] + 7) for p in points]
    placed = []

    def clear(b):
        return all(b[2] < o[0] or b[0] > o[2] or b[3] < o[1] or b[1] > o[3] for o in boxes)

    for p in sorted(points, key=lambda p: (p["y"], p["x"])):
        w = len(p["label"]) * FONT_W
        spot = None
        for dy in (0, -LINE, LINE, -2 * LINE, 2 * LINE, -3 * LINE, 3 * LINE, -4 * LINE, 4 * LINE):
            y = min(max(p["y"] + dy, top + 10), bottom - 4)
            for x in (p["x"] + 10, p["x"] - 10 - w):
                b = (x, y - 10, x + w, y + 3)
                if x >= left and x + w <= right and clear(b):
                    spot = (x, y, b)
                    break
            if spot:
                break
        if spot is None:  # crowded: right of the point, overlap and all
            x = min(p["x"] + 10, right - w)
            spot = (x, p["y"] + 4, (x, p["y"] - 6, x + w, p["y"] + 7))
        boxes.append(spot[2])
        placed.append(p | {"lx": spot[0], "ly": spot[1]})
    return placed


def scatter(svg_id: str, points: list[dict], x_kind: str, title: str, desc: str, hidden: bool = False) -> str:
    """Quality (y, %) against cost or time (x). points: {label, title, quality, x, shape, cls}. For cost, $0 points
    sit in a "free" lane at the left edge and the paid ones on a linear scale beside it."""
    w, h = 760, 380
    left, right, top, bottom = 58, w - 16, 14, h - 50
    qs = [p["quality"] for p in points] or [100]
    lo = max(0, math.floor((min(qs) - 2) / 10) * 10)
    y_of = lambda q: bottom - (q - lo) / (100 - lo) * (bottom - top)  # noqa: E731
    body = ""
    step = 10 if 100 - lo <= 50 else 20
    for q in range(lo, 101, step):
        body += (f'<line class="gridline" x1="{left}" x2="{right}" y1="{_f(y_of(q))}" y2="{_f(y_of(q))}"/>'
                 f'<text class="axis" x="{left - 8}" y="{_f(y_of(q) + 4)}" text-anchor="end">{q}%</text>')

    xs = [p["x"] for p in points]
    if x_kind == "cost":
        lane_w = 100
        paid_left = left + lane_w + 26
        paid = [x for x in xs if x > 0]
        ticks = nice_ticks(max(paid)) if paid else []
        hi = ticks[-1] if ticks else 1
        x_of = lambda x: left + lane_w / 2 if x == 0 else paid_left + x / hi * (right - 120 - paid_left)  # noqa: E731
        body += (f'<rect class="lane-fill" x="{left}" y="{top}" width="{lane_w}" height="{bottom - top}" rx="8"/>'
                 f'<text class="lane" x="{left + lane_w / 2}" y="{bottom + 18}" text-anchor="middle">free ($0)</text>')
        for t in ticks[1:]:
            body += f'<text class="axis" x="{_f(x_of(t))}" y="{bottom + 18}" text-anchor="middle">{_money(t)}</text>'
        axis_title = "Cost per question (USD)"
    else:
        ticks = nice_ticks(max(xs) if xs else 1)
        hi = ticks[-1]
        x_of = lambda x: left + 12 + x / hi * (right - 120 - left - 12)  # noqa: E731
        for t in ticks:
            body += f'<text class="axis" x="{_f(x_of(t))}" y="{bottom + 18}" text-anchor="middle">{_f(t)} s</text>'
        axis_title = "Seconds per question"
    body += (f'<line class="baseline" x1="{left}" x2="{right}" y1="{bottom}" y2="{bottom}"/>'
             f'<text class="axis-title" x="{(left + right) / 2}" y="{h - 8}" text-anchor="middle">{axis_title}</text>'
             f'<text class="axis-title" transform="translate(14 {(top + bottom) / 2}) rotate(-90)" '
             f'text-anchor="middle">Checks passed</text>')

    at: dict[tuple, int] = {}  # points on the same spot step sideways, so none hides another
    pts = []
    for p in points:
        x, y = x_of(p["x"]), y_of(p["quality"])
        n = at.get((round(x), round(y)), 0)
        at[(round(x), round(y))] = n + 1
        pts.append(p | {"x": x + 14 * n, "y": y})
    for p in _place_labels(pts, left + 2, right, top, bottom):
        if abs(p["ly"] - 4 - p["y"]) > 8:
            lx = p["lx"] if p["lx"] > p["x"] else p["lx"] + len(p["label"]) * FONT_W
            body += f'<line class="leader" x1="{_f(p["x"])}" y1="{_f(p["y"])}" x2="{_f(lx)}" y2="{_f(p["ly"] - 4)}"/>'
        body += (f'<g><title>{_e(p["title"])}</title>{_mark(p["shape"], p["cls"], p["x"], p["y"])}'
                 f'<text x="{_f(p["lx"])}" y="{_f(p["ly"])}">{_e(p["label"])}</text></g>')
    return _svg(svg_id, w, h, title, desc, body, hidden)


def bars(svg_id: str, groups: list[dict], title: str, desc: str) -> str:
    """Grouped horizontal bars on a 0–1 scale. groups: {label, title, bars: [(css class, series name, value)]}. The
    group's name sits above its bars, so long names don't eat the bars' width; each bar ends in its value."""
    w, left, right, bar, gap, top = 380, 8, 330, 12, 2, 8
    per = lambda g: 18 + len(g["bars"]) * (bar + gap) + 10  # noqa: E731
    h = top + sum(per(g) for g in groups) + 26
    x_of = lambda v: left + v * (right - left)  # noqa: E731
    body = ""
    for t in (0, 0.25, 0.5, 0.75, 1):
        body += (f'<line class="gridline" x1="{_f(x_of(t))}" x2="{_f(x_of(t))}" y1="{top}" y2="{h - 22}"/>'
                 f'<text class="axis" x="{_f(x_of(t))}" y="{h - 6}" text-anchor="middle">{t:g}</text>')
    y = top
    for g in groups:
        body += f'<text x="{left}" y="{y + 12}"><title>{_e(g["title"])}</title>{_e(g["label"])}</text>'
        y += 18
        for cls, series, value in g["bars"]:
            label = "–" if value is None else f"{value:.2f}"
            width = max(0.0, x_of(value or 0) - left)
            body += (f'<g><title>{_e(g["title"])}, {_e(series)}: {label}</title>'
                     f'<rect class="bar {cls}" x="{left}" y="{y}" width="{_f(width)}" height="{bar}" rx="3"/>'
                     f'<text x="{_f(left + width + 5)}" y="{y + 10}">{label}</text></g>')
            y += bar + gap
        y += 10
    body += f'<line class="baseline" x1="{left}" x2="{left}" y1="{top}" y2="{h - 22}"/>'
    return _svg(svg_id, w, h, title, desc, body, min_width=320)


def strips(svg_id: str, rows: list[dict], title: str, desc: str) -> str:
    """Per embedder, two strips of dots on one shared score axis: on-topic questions (circles) and off-topic ones
    (squares), with the embedder's threshold as a dashed line. rows: {label, title, threshold, on: [(score, name)],
    off: [(score, name)]}, or {label, title, missing: text} for a run without the scores."""
    w, left, right, top = 760, 150, 744, 6
    lane, head = 30, 20
    scores = [s for r in rows if "missing" not in r for s, _ in r["on"] + r["off"]]
    scores += [r["threshold"] for r in rows if "missing" not in r]
    lo = max(-1.0, math.floor(min(scores, default=0) * 10) / 10)
    hi = min(1.0, math.ceil(max(scores, default=1) * 10) / 10)
    hi = hi if hi > lo else lo + 0.1
    x_of = lambda v: left + 8 + (v - lo) / (hi - lo) * (right - left - 16)  # noqa: E731
    heights = [head + (lane if "missing" in r else 2 * lane) + 12 for r in rows]
    h = top + sum(heights) + 34
    body = ""
    step = 0.1 if hi - lo <= 1 else 0.2
    t = lo
    while t <= hi + 1e-9:
        body += (f'<line class="gridline" x1="{_f(x_of(t))}" x2="{_f(x_of(t))}" y1="{top}" y2="{h - 34}"/>'
                 f'<text class="axis" x="{_f(x_of(t))}" y="{h - 20}" text-anchor="middle">{t:.1f}</text>')
        t = round(t + step, 10)
    body += (f'<text class="axis-title" x="{(left + right) / 2}" y="{h - 4}" text-anchor="middle">'
             f'Top-1 vector score (cosine), threshold ignored</text>')
    y = top
    for r, height in zip(rows, heights):
        body += f'<text class="axis-title" x="8" y="{y + 14}"><title>{_e(r["title"])}</title>{_e(r["label"])}</text>'
        if "missing" in r:
            body += f'<text class="lane" x="{left}" y="{y + head + 18}">{_e(r["missing"])}</text>'
            y += height
            continue
        tx = x_of(r["threshold"])
        body += (f'<line class="threshold" x1="{_f(tx)}" x2="{_f(tx)}" y1="{y + head - 4}" y2="{y + head + 2 * lane}"/>'
                 f'<text x="{_f(tx + 5)}" y="{y + 14}">threshold {r["threshold"]:.2f}</text>')
        for i, (key, cls, shape, name) in enumerate((("on", "on-topic", "circle", "on-topic"),
                                                     ("off", "off-topic", "square", "off-topic"))):
            mid = y + head + i * lane + lane / 2
            body += (f'<text class="lane" x="{left - 6}" y="{_f(mid + 4)}" text-anchor="end">'
                     f'{name} ({len(r[key])})</text>')
            for j, (score, what) in enumerate(sorted(r[key])):
                jitter = (j % 5 - 2) * 4  # neighbours step up and down, so close scores stay visible
                body += (f'<g><title>{_e(what)}: {score:.2f}</title>'
                         f'{_mark(shape, cls, x_of(score), mid + jitter, 4.5)}</g>')
        y += height
    return _svg(svg_id, w, h, title, desc, body)


def _money(x: float) -> str:
    return f"${x:.2g}" if x < 1 else f"${x:.2f}"

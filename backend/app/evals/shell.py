"""The shared shell of the review pages on GitHub Pages (docs/report/): one top bar with the four pages and a theme
switch, the app's fonts, and one remembered theme. The model-check report gets it from report.py; the hand-written
pages (the process map, the architecture review, the retro) get it written in between marker comments by
`python -m app.evals shell`, so every page stays one file that opens from disk. test_report_shell.py fails when a
page's copy differs from this one.

The architecture review and the retro use Tailwind's classes, and the review skills add new tabs in that markup. So
they aren't rewritten: their Tailwind colours become CSS variables, Patch's purple stands in for indigo, and dark
mode turns each colour scale round (a light shade becomes the matching dark one).
"""
import json
import re
from pathlib import Path

PAGES = [("index.html", "Model check"), ("process-map.html", "Process map"),
         ("architecture-review.html", "Architecture review"), ("retro.html", "Retro")]
STORAGE_KEY = "patch-reports-theme"
FONTS = ("https://fonts.googleapis.com/css2?family=Fredoka:wght@500;600;700"
         "&family=Nunito:wght@400;600;700;800&display=swap")  # the same as frontend/index.html

# Light and dark, from frontend/src/styles/tokens.css (the playful design).
STYLE = """
:root { --rs-bar: #ffffff; --rs-text: #2a2559; --rs-muted: #605d8c; --rs-border: #e4e5f8; --rs-accent: #6c4cf5;
  --rs-accent-soft: #efeaff; --rs-on-accent: #ffffff; }
:root[data-theme="dark"] { --rs-bar: #1a1a2e; --rs-text: #ecebff; --rs-muted: #a9a8cc; --rs-border: #2c2b48;
  --rs-accent: #a28dff; --rs-accent-soft: #2a2550; --rs-on-accent: #0f0f1c; }
@media (prefers-color-scheme: dark) { :root:not([data-theme]) { --rs-bar: #1a1a2e; --rs-text: #ecebff;
  --rs-muted: #a9a8cc; --rs-border: #2c2b48; --rs-accent: #a28dff; --rs-accent-soft: #2a2550; --rs-on-accent: #0f0f1c; } }
.rs-bar { background: var(--rs-bar); border-bottom: 1px solid var(--rs-border); color: var(--rs-text);
  font: 400 15px/1.4 Nunito, system-ui, sans-serif; }
.rs-inner { max-width: 1280px; margin: 0 auto; padding: 0.55rem 1rem; display: flex; flex-wrap: wrap; align-items: center;
  gap: 0.5rem 1rem; }
.rs-brand { display: flex; align-items: center; gap: 0.55rem; margin-right: auto; color: var(--rs-text); text-decoration: none; }
.rs-mark { display: grid; place-items: center; width: 32px; height: 32px; border-radius: 12px; color: #ffffff;
  background: linear-gradient(135deg, #7454f7, #5a3ff0); }
.rs-name { font: 600 1.1rem/1 Fredoka, Nunito, system-ui, sans-serif; }
.rs-name small { color: var(--rs-muted); font: 600 0.95rem Nunito, system-ui, sans-serif; }
.rs-nav { display: flex; gap: 0.25rem; }
.rs-nav a { padding: 0.3rem 0.75rem; border-radius: 999px; color: var(--rs-text); text-decoration: none; font-weight: 700;
  font-size: 0.88rem; white-space: nowrap; }
.rs-nav a:hover { background: var(--rs-accent-soft); }
.rs-nav a[aria-current="page"] { background: var(--rs-accent); color: var(--rs-on-accent); }
.rs-theme { display: grid; place-items: center; width: 36px; height: 36px; padding: 0; border: 1px solid var(--rs-border);
  border-radius: 999px; background: transparent; color: var(--rs-text); cursor: pointer; }
.rs-theme svg[hidden] { display: none !important; }  /* some pages style every svg */
.rs-bar a:focus-visible, .rs-theme:focus-visible { outline: 3px solid var(--rs-accent); outline-offset: 2px; }
/* A phone: the links get their own row and wrap, so all four show. */
@media (max-width: 720px) { .rs-nav { order: 3; width: 100%; flex-wrap: wrap; } }
"""

# Before the page draws: the saved theme, else the system's. Every page's own dark styles key on data-theme.
HEAD_SCRIPT = f"""(() => {{
  let t; try {{ t = localStorage.getItem("{STORAGE_KEY}"); }} catch {{}}
  if (t !== "light" && t !== "dark") t = matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  document.documentElement.dataset.theme = t;
}})();"""

SWITCH_SCRIPT = f"""(() => {{
  const root = document.documentElement, button = document.querySelector(".rs-theme");
  const show = () => {{
    const dark = root.dataset.theme === "dark";
    button.querySelector(".rs-sun").toggleAttribute("hidden", !dark);  // an svg has no .hidden property
    button.querySelector(".rs-moon").toggleAttribute("hidden", dark);
    button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
  }};
  show();
  button.addEventListener("click", () => {{
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    try {{ localStorage.setItem("{STORAGE_KEY}", root.dataset.theme); }} catch {{}}
    show();
  }});
}})();"""

_ICON = ('<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" '
         'stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"{extra}>{paths}</svg>')
SHIELD = _ICON.format(extra="", paths='<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="m9 12 2 2 4-4"/>')
SUN = _ICON.format(extra=' class="rs-sun" hidden', paths='<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 '
                   '4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>')
MOON = _ICON.format(extra=' class="rs-moon"', paths='<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>')


def head() -> str:
    """What goes in <head>: the fonts, the theme before first paint, the bar's styles."""
    return (f'<link rel="preconnect" href="https://fonts.googleapis.com">\n'
            f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
            f'<link rel="stylesheet" href="{FONTS}">\n'
            f'<script>{HEAD_SCRIPT}</script>\n<style>{STYLE}</style>')


def bar(current: str) -> str:
    """The top bar, first in <body>: Patch, the four pages (this one marked), the theme switch."""
    mark = ' aria-current="page"'
    links = "".join(f'<a href="{href}"{mark if href == current else ""}>{name}</a>' for href, name in PAGES)
    return (f'<header class="rs-bar"><div class="rs-inner">'
            f'<a class="rs-brand" href="index.html"><span class="rs-mark">{SHIELD}</span>'
            f'<span class="rs-name">Patch <small>· review pages</small></span></a>'
            f'<nav class="rs-nav" aria-label="Review pages">{links}</nav>'
            f'<button type="button" class="rs-theme" aria-label="Switch to dark mode">{SUN}{MOON}</button>'
            f'</div></header>\n<script>{SWITCH_SCRIPT}</script>')


# --- Tailwind pages

# Tailwind 3.4's palette, only the families the pages use. Indigo is drawn with violet, nearer Patch's purple.
_PALETTE = {
    "slate": "f8fafc f1f5f9 e2e8f0 cbd5e1 94a3b8 64748b 475569 334155 1e293b 0f172a 020617",
    "stone": "fafaf9 f5f5f4 e7e5e4 d6d3d1 a8a29e 78716c 57534e 44403c 292524 1c1917 0c0a09",
    "red": "fef2f2 fee2e2 fecaca fca5a5 f87171 ef4444 dc2626 b91c1c 991b1b 7f1d1d 450a0a",
    "amber": "fffbeb fef3c7 fde68a fcd34d fbbf24 f59e0b d97706 b45309 92400e 78350f 451a03",
    "emerald": "ecfdf5 d1fae5 a7f3d0 6ee7b7 34d399 10b981 059669 047857 065f46 064e3b 022c22",
    "sky": "f0f9ff e0f2fe bae6fd 7dd3fc 38bdf8 0ea5e9 0284c7 0369a1 075985 0c4a6e 082f49",
    "indigo": "f5f3ff ede9fe ddd6fe c4b5fd a78bfa 8b5cf6 7c3aed 6d28d9 5b21b6 4c1d95 2e1065",
}
SHADES = [50, 100, 200, 300, 400, 500, 600, 700, 800, 900, 950]
# Dark mode: each shade takes the value of its opposite. 400 and 500 swap so grey text on the dark page keeps
# about 4.5:1 (500 → 400 is #94a3b8 on #1a1a2e).
DARK_OF = {50: 950, 100: 900, 200: 800, 300: 700, 400: 500, 500: 400, 600: 300, 700: 200, 800: 100, 900: 50, 950: 50}
# Patch's dark page, card and border colours where the pages use them: the body (stone-50), cards (white) and borders
# (slate-200).
DARK_OVERRIDES = {"--tw-stone-50": "#0f0f1c", "--tw-white": "#1a1a2e", "--tw-slate-200": "#2c2b48"}


def _rgb(hex_: str) -> str:
    return " ".join(str(int(hex_.lstrip("#")[i:i + 2], 16)) for i in (0, 2, 4))


def _vars(dark: bool) -> str:
    out = {"--tw-white": "#ffffff"}
    for family, values in _PALETTE.items():
        by_shade = dict(zip(SHADES, values.split()))
        for shade in SHADES:
            out[f"--tw-{family}-{shade}"] = "#" + by_shade[DARK_OF[shade] if dark else shade]
    if dark:
        out.update(DARK_OVERRIDES)
    return " ".join(f"{k}: {_rgb(v)};" for k, v in out.items())


def tailwind() -> str:
    """Right after Tailwind's script: its colours and fonts as Patch's, light and dark."""
    colours = {"white": "rgb(var(--tw-white) / <alpha-value>)"} | {
        family: {str(s): f"rgb(var(--tw-{family}-{s}) / <alpha-value>)" for s in SHADES} for family in _PALETTE}
    config = {"theme": {"extend": {"colors": colours, "fontFamily": {
        "serif": ["Fredoka", "Nunito", "system-ui", "sans-serif"], "sans": ["Nunito", "system-ui", "sans-serif"]}}}}
    return (f"<script>tailwind.config = {json.dumps(config)};</script>\n<style>\n"
            f":root {{ {_vars(False)} }}\n:root[data-theme=\"dark\"] {{ {_vars(True)} }}\n"
            # Mermaid draws in its light theme once; in dark mode each diagram sits on a light card.
            ":root[data-theme=\"dark\"] .mermaid svg { background: #f8fafc; border-radius: 12px; padding: 8px; }\n"
            "</style>")


# --- Writing it into a page

def _block(name: str, body: str) -> str:
    return f"<!-- report-shell:{name} -->\n{body}\n<!-- /report-shell:{name} -->"


def apply(text: str, page: str) -> str:
    """The page with its shell blocks replaced by the current ones, or put in on the first run: head before
    </head>, the bar after <body ...>, the Tailwind block after Tailwind's script tag."""
    wanted = {"head": head(), "bar": bar(page)}
    if "cdn.tailwindcss.com" in text:
        wanted["tailwind"] = tailwind()
    for name, body in wanted.items():
        new = _block(name, body)
        pattern = re.compile(rf"<!-- report-shell:{name} -->.*?<!-- /report-shell:{name} -->", re.S)
        if pattern.search(text):
            text = pattern.sub(lambda _: new, text, count=1)
        elif name == "head":
            text = text.replace("</head>", new + "\n</head>", 1)
        elif name == "bar":
            text = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + "\n" + new, text, count=1)
        else:
            text = re.sub(r'(<script src="https://cdn\.tailwindcss\.com"></script>)', lambda m: m.group(1) + "\n" + new,
                          text, count=1)
    return text


def write(folder: Path) -> list[str]:
    """Bring every hand-written page in the folder up to the current shell. Returns the pages that changed."""
    changed = []
    for page, _ in PAGES[1:]:
        path = folder / page
        old = path.read_text()
        new = apply(old, page)
        if new != old:
            path.write_text(new)
            changed.append(page)
    return changed

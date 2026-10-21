# Design: Patch, the LLM-security assistant ("Playful")

The design of the prototype in `proto/`, written down so it can be built again from tickets. Decided 2026-10-13, after trying six designs and four chat layouts (history: [../design-examples/README.md](../design-examples/README.md)).

- **Source of truth:** the running prototype. Every value here was read from the code on 2026-10-13: `proto/frontend/src/designs.css`, `index.css`, `App.tsx`, `components/Robot.tsx`, `hooks/useMood.ts`, `components/charts.tsx`, `index.html`.
- **Screenshots:** [img/](./img/), taken from the prototype on 2026-10-13.
- **Status marks:** *checked* = verified in this project (by the browser checks, the colour validator or a measurement). *Unverified* = not tested yet.

## 0. Read this first: design is part of every ticket

On another project, tickets were built without the design, and the animations never arrived. This document exists so that doesn't happen again.

- **Design is not a polish phase.** A ticket that adds or changes UI is not done until it matches this document: colours, shapes, motion, dark mode, phone layout, reduced motion.
- **Motion is a feature, not decoration.** The animations in section 7 are part of the spec. A ticket that draws a chart must include the bars growing in. A ticket that builds the chat must include Patch's moods.
- **Build the tokens first.** Section 3 (colours, fonts, radii, shadows) is the first ticket. Everything else uses those tokens, never hard-coded colours.
- **Each section ends with a checklist.** Copy the relevant checklist into the ticket as its acceptance criteria.

![The dashboard in light mode](img/dashboard-light.png)

---

## 1. Decisions (what we chose, and why)

| Area | Decision | Why | Rejected |
|---|---|---|---|
| Overall look | **Playful**: periwinkle background, big round white cards, candy-coloured tiles, rounded fonts, a robot mascot | A security tool doesn't have to feel scary. Friendly makes "ask me anything" inviting. The user picked it over every alternative. | Classic (plain top bar), Glass (dark navy glass, after Vision UI), Neon HUD (glowing, futuristic), Clean sidebar (calm, minimal). See [design-examples](../design-examples/README.md). |
| Navigation | A **left sidebar** that collapses to an icon rail; a **bottom tab bar** on phones | Room for more pages; the rail gives space back to the page. | Top bar of buttons (Classic). |
| Assistant | **Patch**, an original SVG robot, is the chat button and the face of the chat | Gives the assistant a personality; his mood shows what the chat is doing. | Plain "Ask" button. The stock robots that inspired him were watermarked, so he was drawn from scratch. |
| Chat layout | A **bubble** in the bottom right. Enlarged, it can be **pinned** beside the page. | The chat stays on top of what you're looking at ("Ask about this" keeps the CVE in view). Pinning covers the "side by side" need. | Tabs (chat as its own page: loses the context), drawer and side panel (overlapped with pinning, merged then removed). |
| Motion | Cards fade up, bars grow in, a blinking cursor after the page title, Patch moves | The user liked these most from Neon HUD; they make the dashboard feel alive. | Neon's grid, glow and scanline (too much for long reading). |
| Light and dark | A **toggle** in the top bar; starts from the system setting | Both modes are first-class. | Following the system only (a button can't override that). |
| Dark palette | **Near-black with a hint of indigo**, not saturated purple | Text on saturated purple felt "buzzy" even at good contrast. | The first dark Playful (`#16152f` / `#221f44`). |
| Candy tiles | Gradients **start deep where the text is** and end bright | White labels on bright orange and coral failed contrast (1.8–2.7:1). Now 4.9:1 or better. *Checked.* | Bright-to-deep gradients. |
| Severity colours | **One purple, four depths** (Low light → Critical deep) | Severity is ordered: one hue shows the order. Four candy hues would read as four unrelated groups, and orange/coral would look like warnings. | Blue ramp (off-brand), four candy colours. |
| Tinted stat tiles in a calm design | Not used | Tried on Clean (gradient, then solid); looked pasted on. | — |

---

## 2. Principles

- **Friendly, never noisy.** Round shapes, soft shadows, candy colour on a few things that matter (the four tiles), calm white cards for everything else.
- **One accent: purple.** Links, focus, active states, the series colour of every single-series chart.
- **Colour is never the only cue.** Shapes on the map, a legend on every multi-series chart, a "Show as table" under every chart, icons and labels on alerts.
- **Everything works in light, dark, phone and with reduced motion.** Not as an afterthought: each checklist below includes them.

---

## 3. Tokens (build these first)

Tokens are CSS custom properties on `<html data-design="playful">`. Dark values apply when `<html data-theme="dark">`. Components only ever use tokens.

### 3.1 Colours

| Token | Light | Dark | Used for |
|---|---|---|---|
| `--bg` | `#dfe5fd` | `#0f0f1c` | page background (under the gradients, 3.3) |
| `--surface` | `#ffffff` | `#1a1a2e` | cards, sidebar, chat, inputs |
| `--text` | `#2a2559` | `#ecebff` | body text |
| `--muted` | `#605d8c` (was `#6f6c9c`, fault 12.1) | `#a9a8cc` | secondary text, axis labels |
| `--border` | `#e4e5f8` | `#2c2b48` | hairlines |
| `--accent` | `#6c4cf5` | `#a28dff` | links, focus, active, page title |
| `--accent-soft` | `#efeaff` | `#2a2550` | soft fills: hover, chips, nested cards |
| `--user` | `#efeaff` | `#2a2550` | the user's chat messages |
| `--ok` | `#0d7b50` | `#4fd39a` | success, "final sources" |
| `--error` | `#cf1b3e` | `#ff7a95` | errors, KEV |
| `--error-soft` | `#ffe8ed` | `#3a1c2a` | error backgrounds |
| `--warn` | `#9c5508` | `#ffb547` | warnings |
| `--warn-soft` | `#fff1de` | `#33281a` | warning backgrounds |
| `--series-1` | `#7b5cff` | `#a28dff` | single-series charts |
| `--grid` | `#eceefb` | `#25243d` | chart gridlines |

Fixed colours (same in both modes):

- **Primary gradient** `--gradient-primary` (primary buttons, active sidebar item, brand mark): `linear-gradient(135deg, #7454f7, #5a3ff0)`. Started at `#8b6cff` in the prototype (fault 12.1). Text on it is `--on-primary` (`#ffffff`).
- **Purple shadow** used everywhere: `rgba(108, 76, 245, α)`, α between 0.09 and 0.4 (values per component below).
- **Patch's colours** (§8.1): body `#9483FF`, visor `#2A2457`, eyes `#7FF0DD`, antenna light `#FFC94D`, and the cheeks and extras listed there.

Contrast (*checked*: WCAG 2 formula, 2026-10-14, after the fixes; the browser check A02.3 re-measures muted and the gradient). Since B49 (#96) the browser check B49.20 (`frontend/e2e/test_contrast.py`) also measures **every text on every page** as drawn (and the chat with an answer), light and dark, 390px and 1440px, on what is really behind it (a linear gradient worked out where the text is), against 4.5:1, or 3:1 for large text (24px, or 18.66px bold). One exception, **accepted by the owner on 2026-10-19** ("reads clear enough"): the candy tiles' text where it reaches the gradient's bright end (§5.1), measured 2.3–4.3:1 in light mode; the check keeps it as a strict xfail, so it shows if the tiles ever change.

| Pair | Light | Dark |
|---|---|---|
| text on surface | 13.9:1 | 14.5:1 |
| text on page background | 11.1:1 | 16.2:1 |
| muted on surface | 6.1:1 | 7.4:1 |
| **muted on page background** | **4.9:1** (was 3.9:1) | 8.3:1 |
| **muted on `--accent-soft`** (chips, nested fills, snapshot card) | **5.2:1** (was 4.2:1) | 6.2:1 |
| accent on surface | 5.3:1 | 6.3:1 |
| accent on page background (the page title: 1.5rem bold, large text, needs 3:1) | 4.2:1 | 7.1:1 |
| accent on `--accent-soft` (fails for small text: such text is `--text` with an `--accent` edge, §5.7; B49) | 4.48:1 | 5.3:1 |
| **white on the primary gradient**, light end / deep end | **4.8:1 / 6.2:1** (was 3.7 / 6.2) | same (fixed colours) |

### 3.2 Chart colours (validated, *checked*)

All validated with the dataviz skill's `validate_palette.js`. Re-run it if any value changes.

**Severity**: an ordinal ramp, one hue. Light: dark = worse. Dark mode: light = worse (more contrast on the dark surface).

| Token | Light | Dark |
|---|---|---|
| `--sev-low` | `#a48bff` | `#5641c4` |
| `--sev-medium` | `#7b5cff` | `#7860f2` |
| `--sev-high` | `#5235d6` | `#a796ff` |
| `--sev-critical` | `#2e1a80` | `#d9d0ff` |

- Light: `--ordinal` on `#ffffff`: monotone, steps ≥ 0.06 apart, lightest step 2.72:1. Dark: on `#1a1a2e`, lightest step 2.40:1.
- Used by the "Open CVEs by product and severity" chart, its legend, and the severity swatches in the CVE table and the chat sources.

**Embedding-map groups**: categorical, candy colours. A scatter, so checked with `--pairs all`.

| Token | Group (shape) | Light | Dark |
|---|---|---|---|
| `--cat-1` | OWASP pages (circle) | `#6c4cf5` | `#8a70ff` |
| `--cat-2` | MITRE ATLAS (square) | `#e2780f` | `#d4761a` |
| `--cat-3` | CVEs (triangle) | `#e0306a` | `#e33e6e` |

- Light: colour-blind separation ΔE ≥ 12.4, normal vision ≥ 17.7. The orange is 2.8:1 on the map surface (just under 3:1): allowed because the shapes and the table view carry the same information.
- Dark: all checks pass, ΔE ≥ 9.5.

Validator commands (from the dataviz skill's folder):

```bash
node scripts/validate_palette.js "#a48bff,#7b5cff,#5235d6,#2e1a80" --mode light --surface "#ffffff" --ordinal
node scripts/validate_palette.js "#5641c4,#7860f2,#a796ff,#d9d0ff" --mode dark --surface "#1a1a2e" --ordinal
node scripts/validate_palette.js "#6c4cf5,#e2780f,#e0306a" --mode light --surface "#f7f5ff" --pairs all
node scripts/validate_palette.js "#8a70ff,#d4761a,#e33e6e" --mode dark --surface "#1e1d36" --pairs all
```

### 3.3 Page background

- Token `--page-glow` (the glows), drawn over `--bg` on `body` with `background-attachment: fixed`.
- Light: three soft glows over `#dfe5fd`, fixed (they don't scroll):
  `radial-gradient(520px 520px at 8% 12%, rgba(255,255,255,.55), transparent 70%)`, `radial-gradient(640px 640px at 96% 88%, rgba(123,92,255,.16), transparent 70%)`, `radial-gradient(360px 360px at 70% 8%, rgba(255,181,71,.16), transparent 70%)`.
- Dark: one faint purple glow over `#0f0f1c`: `radial-gradient(640px 640px at 96% 88%, rgba(123,92,255,.10), transparent 70%)`.

### 3.4 Type

- **Fredoka** (500, 600, 700) for headings, tile numbers, the brand name, the page title. **Nunito** (400, 600, 700, 800) for everything else. Base size 15px.
- Load both in `index.html` (with `preconnect`), not from JavaScript, so the first frame already has the right font.
- Tokens: `--font-display` (Fredoka), `--font-body` (Nunito), `--font-mono` (system monospace).
- Sizes: page title 1.5rem Fredoka in `--accent`; card titles 1.1rem Fredoka 600; tile numbers 2.1rem Fredoka; nested titles (playground columns, "Recent alerts") 0.95rem Fredoka 600; body 15px; meta text 0.82rem `--muted`; code in the system monospace.
- Offline, the fonts fall back to the system sans-serif. *Unverified* how that looks.

### 3.5 Shape and elevation

Token names chosen in A02 (DESIGN.md gave none); values unchanged from the prototype.

| Element | Radius | Shadow |
|---|---|---|
| Sidebar (floating card) | `--radius-sidebar` 28px | `--shadow-sidebar` `0 16px 40px rgba(108,76,245,.12)` |
| Sidebar items (pill rows) | `--radius-item` 16px | active: `--shadow-active` `0 8px 18px rgba(108,76,245,.35)` |
| Brand mark | `--radius-input` 14px | `--shadow-brand` `0 6px 14px rgba(108,76,245,.35)` |
| Snapshot card | `--radius-snapshot-card` 22px | — |
| Cards (`.card`, `.panel` in the prototype) | `--radius-card` 26px | `--shadow-card` `0 12px 30px rgba(108,76,245,.09)` |
| Chat bubble window, pinned chat | `--radius-card` 26px | (bubble) `--shadow-bubble` `0 16px 48px rgba(0,0,0,.24)`; (pinned) `--shadow-pinned` `0 12px 30px rgba(108,76,245,.12)` |
| Stat tiles | `--radius-tile` 24px | `0 12px 26px <tile colour at .3>` |
| Welcome banner | `--radius-banner` 28px | `--shadow-banner` `0 12px 30px rgba(108,76,245,.1)` |
| Save bar (floating) | `--radius-save-bar` 20px | `--shadow-save-bar` `0 10px 28px rgba(108,76,245,.16)` |
| Chat messages | `--radius-message` 20px, with the corner nearest the speaker at `--radius-message-tail` 6px | — |
| Nested cards: fieldsets, delivery channels, playground columns, map box, model-check numbers | `--radius-nested` 18px (the prototype used 18–20px) | none |
| Inputs, selects, textareas | `--radius-input` 14px | — |
| Buttons | `--radius-pill` 999px | primary: `--shadow-primary` `0 6px 14px rgba(108,76,245,.3)` |

- Nested cards have no border. Their fill is `--nested-fill`: `color-mix(in srgb, var(--accent-soft) 40%, var(--surface))` (the prototype used 35–45%).

### Checklist: tokens

- [ ] Every colour in sections 3.1 and 3.2 is a token with light and dark values.
- [ ] No component uses a hard-coded colour except the fixed ones listed (primary gradient, purple shadow, tile gradients, Patch's own colours listed in §8.1).
- [ ] Fonts load from `index.html`; no flash of the wrong font on first load.
- [ ] Dark mode is driven by `data-theme` on `<html>`, not by `prefers-color-scheme`, so the toggle can override the system.

---

## 4. Layout and navigation

![Dashboard, dark](img/dashboard-dark.png)

### 4.1 Shell

- **Sidebar** (left), then the **main column**: top bar, then the page.
- Sidebar, expanded: 250px wide, floating card with 1rem margin. Contents, top to bottom:
  1. Brand: 36px purple-gradient rounded square with a shield icon, **"Patch"**, and under it the small line "LLM-security assistant" (one name everywhere, B32, 2026-10-18; it read "LLM Security" / "assistant" before). Name and line align left, also on the centred loading and sign-in cards. One component (`frontend/src/components/Brand.tsx`) draws it on all three. Dashed line under it. *Checked* by the browser check B32.1 (sidebar), B32.2 (sign-in), B32.3 (loading screen).
  2. Section label "MONITOR": Dashboard, CVEs, Settings, Dev (Dev only when the backend allows the dev panel). CVEs added 2026-10-14 (A04b).
  3. Section label "ASSISTANT": "Ask Patch" (opens and hides the chat; shows the unread dot). Until the chat ticket (A06) it is a placeholder: named, reachable by keyboard, `aria-disabled`, described as "Coming soon".
  3b. Section label "PATCH": **About** (B42, 2026-10-19), the landing page inside the app (§5.16), with an "i" icon. On phones it is the tab bar's last item, after Ask (six items fit at 390px, *checked* by B42.11).
  4. At the bottom, the **snapshot card**: Patch (64px) with his head over the card's top edge, "Snapshot", data date, model name.
  5. Collapse button (chevron).
- Sidebar items: pill rows (radius 16px). Icon in a 32px soft-purple rounded square. **Active item**: primary gradient fill, white text, icon square at 22% white, purple shadow.
- **Collapsed rail**: 78px wide, icons only, centred. Section labels become thin lines. Brand name and snapshot card hide. Labels stay in the accessibility tree (visually hidden), so the buttons keep their names. The chevron rotates 180°. Width animates over 0.2s. Remembered per browser.
- **Top bar**: breadcrumb "Pages / Dashboard" (0.75rem muted) above the page title (1.5rem Fredoka, purple, with the blinking cursor, section 7). Right side: the light/dark toggle (36px round, sun in dark mode, moon in light).
- **Content**: max 1280px wide, centred, 1rem padding, 1.2rem gap between cards. CVEs, Settings and Dev use the same width and gap as the dashboard.
- **Paths** (A04b): each page has one: `/` (Dashboard), `/cves`, `/settings`, `/dev`, `/about` (B42). A sidebar click is a new history entry, so Back returns; a reload stays on the page. Any other address is **Page not found** (§5.19, B49); signed out with sign-in on, the landing page (§5.16). One CVE's page (B35) is `/cves/CVE-…`, under CVEs: the sidebar shows CVEs active, the breadcrumb says "Pages / CVEs" and the title is the CVE id (§5.15).

### 4.2 Breakpoints

| Width | Change |
|---|---|
| ≤ 1000px | Dashboard: one column, in page order: the Watchlist filter (above the tiles it narrows, B43), the tiles, the main column, then the side cards. The charts keep Patch's strip free on their right (§6.1). |
| ≤ 900px | Settings and Dev: one column of cards |
| ≤ 800px | Sidebar becomes a **bottom tab bar** (fixed, full width, icon over label, "Ask" short label): Dashboard, CVEs, Settings, Dev, Ask. Page gets at least 4.4rem bottom padding (more since B43: room for Patch's button above the bar, §6.1). Patch's button moves up to 5rem from the bottom. |
| Phone (≤ 800px), or chat pinned and table ≤ 760px | The CVE table's rows become **stacked cards** (§5.9). With the chat pinned it is measured on the table's card (a container query). Any other window keeps the table: at 820–1050px with the sidebar open the card is 525–755px, and a table that scrolls sideways inside its card is better there than cards (review, 2026-10-15). |
| ≤ 700px | Chat (bubble or pinned) becomes a **full-screen sheet**. The pin and Make larger buttons hide. |
| ≤ 640px | Stat tiles: 2 columns. Welcome banner: Patch at 64px beside the title, the help line and the button under both, left-aligned (B43; it stacked a 110px Patch over centred text, about 330px tall). |
| ≤ 520px | Slider rows stack (label above the slider). |

- The shell (A02) builds the ≤ 800px tab bar. The other rows belong to the dashboard, settings, dev and chat tickets, which build what they change.
- At every width there is **no sideways scrolling** (*checked* at 1400px and 400px for every page, light and dark).

### Checklist: layout

- [ ] Sidebar expands and collapses, remembered after reload; keyboard and screen reader still reach every item when collapsed.
- [ ] Active page is shown in the sidebar and the breadcrumb and title.
- [ ] Bottom tab bar on phones; nothing hidden behind it.
- [ ] No horizontal scroll at 400px or 1400px.

---

## 5. Components

### 5.1 Stat tiles (the four "candy" tiles)

- Grid of 4 (2 on phones), gap 0.75rem. Radius 24px, padding 1rem 1.2rem, white text.
- Two soft white circles (16% white) as decoration: 120px at the top right (−30px, −40px), 80px at the bottom (right 40px, −45px).
- Number 2.1rem Fredoka; label and note 700 weight at 92% white.
- Gradients (135°, deep colour until 35%, then to the bright colour) and label contrast (*checked*):

| Tile | Gradient | Shadow | White text |
|---|---|---|---|
| Open CVEs | `#5b3fe0 35%` → `#8b6cff` | `rgba(108,76,245,.3)` | 6.5:1 |
| Open and critical | `#c24a0a 35%` → `#f5933f` | `rgba(255,138,60,.3)` | 4.9:1 |
| Open and exploited (CISA KEV) | `#c42a50 35%` → `#ff6b8b` | `rgba(229,56,90,.3)` | 5.5:1 |
| New in the last 30 days | `#26265f 35%` → `#4a4aa8` | `rgba(38,38,95,.3)` | 13.8:1 |

- *Open* (B49): measured where the text is (B49.20), the labels pass on the deep start but not where they reach the bright end, worst on a phone where they wrap: "Open and critical" 2.5:1, its number 3.0:1, the KEV label 3.0:1, "Open CVEs" 3.8:1 (the landing tiles alike). A brand colour change, so the owner's call (DECISIONS.md, B49).
- The KEV tile, when there are open KEV CVEs, **wiggles** every 4 seconds (section 7) and shows "Overdue since …" with a warning icon.
- Each tile is a **link to the CVEs page with its filter** (A04b): open → `/cves`; open and critical → `?severity=CRITICAL`; open and in KEV → `?kev=1`; new in 30 days → `?status=all&since=<first of the 30 days>`. No underline; the global focus ring shows by keyboard.

### 5.2 Cards (`.panel`)

- White surface, no border, radius 26px, padding 1.1rem 1.3rem, purple shadow.
- Title: 1.1rem Fredoka 600, normal case. No status chip on Settings' and Dev's cards since B50 (#95): every card said "Live", so it told you nothing. The dashboard's Data freshness card keeps its "Live" / "Snapshot" chip (§5.10): there it says something.

### 5.3 Buttons and form controls

- All buttons are pills (999px), weight 700. **Primary** (`type="submit"`): primary gradient, white text, purple shadow. Others: surface fill, 1px border, border turns purple on hover.
- Inputs, selects, textareas: radius 14px. The playground search box is a full pill.
- Checkboxes and radios: purple (`accent-color: var(--accent)`).
- **Sliders**: 6px track in `--accent-soft`, filled part in `--accent`, 16px purple handle with a 3px surface ring and a purple shadow. A purple focus ring (2px, 4px offset) for keyboards. Styled for both Firefox (`::-moz-range-*`) and Chrome/Safari (`::-webkit-slider-*`). Chrome/Safari has no "filled part": the track there is a gradient up to `--fill`, set inline by the slider (A11, *checked* by the browser check in Chromium).

### 5.4 Charts

- Plain SVG drawn at the container's width. Every chart: a title, a legend when it has 2+ series, a hover tooltip on every bar, and "Show as table" under it.
- **Open CVEs by product and severity**: horizontal stacked bars, severity ramp (3.2), 2px gaps between segments, the total at the end of each bar.
- **CVEs per month**: columns in `--series-1`, value labels on the peaks. The axis says each year where it starts and the latest month at the end ("2026-10"); a year that would come within 6px of the label after it is left out, so on a phone "2026" and "2026-10" never overlap (B49, `monthAxis.ts`; *checked* by B49.7, B49.16).
- **Open CVEs by OWASP Top 10 (web, 2025)** (titled "by OWASP category" until B43, #25: in an LLM-security app that read like LLM01–LLM10): horizontal bars in `--series-1`. The axis shows the **code only** ("A05"), so no label is cut off at any width; the tooltip and the bar's name give it in full ("A05 Injection: 128 open CVEs"); "Show as table" keeps the full titles. A CVE counts under **every** category its CWEs map to, so the bars can add up to more than the open CVEs. The note says so: "The web list, not the LLM Top 10: CVEs reach it through their CWEs, and a CVE in two categories counts in both. 46 open CVEs have no CWE in OWASP's lists." *Checked* by B43.8, A05.3; the counts by `backend/tests/test_dashboard.py` B43.1.
- Gridlines `--grid`, axis labels 11px `--muted`, value labels 11px `--text`.
- Tooltip: `--text` background, `--surface` text, 4px radius, above the pointer.
- Bars **grow in** on load (section 7). Horizontal bars grow from the chart's axis: the chart sets `--x0` (its label width) on the `<svg>`, so a stacked bar grows as one piece.
- **Two series**: `--cat-1` circles, then `--cat-2` squares (the 3.2 order), so the shape tells them apart as well as the colour. `--cat-2` is 3.0:1 on the light surface: fine for marks, never for text (*checked*, 2026-10-15). Labels and values stay in `--text` or `--muted`.
- **The model-check report** (`backend/app/evals/charts.py`, A20) is a static page, so its charts differ in three ways: no grow-in (a report is read, not watched); a native `<title>` tooltip instead of the app's tooltip; and a fixed viewBox with a minimum width, so on a narrow screen the chart scrolls inside its card ("Scroll sideways" hint) rather than shrinking its text below about 10px.
- **The review pages' shared shell** (2026-10-21): the model-check report, the process map, the architecture review and the retro share one top bar (Patch's mark, the four pages with this one marked, a theme switch), Nunito and Fredoka, and one saved theme. Colours are the playful tokens, light and dark. How it's built and kept the same: [docs/report-src/README.md](../report-src/README.md#the-shared-shell).

### 5.5 Embedding map (Dev page)

![Search playground](img/playground-light.png)

- In a soft round box (`--radius-nested` 18px since A11, as §3.5 lists the map box; no border, nested-card fill). Legend chips are pills with counts.
- Points: circle (OWASP), square (ATLAS), triangle (CVE), in `--cat-1/2/3`, drawn at 90% opacity with a ring in the box colour.
- When a search is shown, all non-result points dim to **40%** (light) or **60%** (dark: faded colour on dark goes muddy). The query is an ✕, rewrites are smaller ✕s, results are full-colour with a dark ring, joined to the query by dashed lines.
- **Group labels** (B50, #95): one per group, just above its centre, 12px bold `--text` with a 4px halo in the box colour. Never on top of another label and never cut by the map's edge (`frontend/src/dev/mapLabels.ts`): each label is moved inside the map, then up or down by whole lines (22px: the label's box as Firefox measures it), nearest first, until it overlaps no label placed before it. Zoomed to a query, a group whose centre is off the map has no label. Why: with the owner's real embedder (ollama/mxbai-embed-large) the OWASP and ATLAS centres are about 35px apart at phone width, and the old nudge compared each label with the one placed just before it only, so two of three could overlap (measured 2026-10-19). Nothing moves. *Checked* by `npm test` B50.6 (the real index's centres) and the browser check B50.6 (390px and 1440px, the hash index).

### 5.6 Search playground (Dev page)

- The query plan (semantic query, filters) in a soft nested card.
- One column per search step (semantic query, each rewrite, fused, final): soft nested cards, radius 18px, column title in purple Fredoka. **Fused** has a 2px purple inner edge; **Final sources** a 2px green (`--ok`) edge with a green title.

#### 5.6.1 Model card: the OpenRouter model (Dev page, A11.10, 2026-10-15)

- With OpenRouter picked, "OpenRouter model" is a **native `<select>`** (§5.3: radius 14px, surface fill, border purple on hover, the global focus ring) of the models this key may use that take tools, cheapest input first. A native select: keyboard, screen readers and phones work as the platform does, and both themes come from the tokens.
- **Option text**: `id (default) · $1.00 / $5.00 per M tokens · 12/14 in the model check`. "(default)" only on the env default; the score only when a finished model check exists; a variable price reads "price unknown" (never $0), a zero price "free". The last option is **"Other…"**.
- **Under the select**, in `.meta` text: the picked model in full (name, price, score or "not in a model check yet", context size), tied to the select by `aria-describedby`. On a phone (400px) the closed select cuts its option's text; this line is where you read it. Then one line on what the list is.
- **Other…** shows a "Model id" text field (mono, as the local model's) and moves focus to it. Its value is the current id: picking Other changes nothing until you type. A saved id not in the list opens as Other with its value and a note "Not in the list for this key: OpenRouter's guardrail may refuse it."
- **Loading**: the select is disabled, `aria-busy`, with one option "Loading the models this key may use…". **No list** (no key, OpenRouter unreachable or refusing): the plain text field as before, with a `role="note"` line giving the reason.
- The select takes the row's width (`flex: 1 1 12rem`, `min-width: 0`): long options never widen the card. Nothing animates. *Checked* by the browser check A11.10 in both themes at 400px and 1400px, by keyboard; the option words by `npm test`.

#### 5.6.2 The Dev page for anyone but the owner (B29, 2026-10-16)

- The choices are the owner's and apply to everyone (B09), so anyone else reads them. The page intro becomes one line, `role="note"`: "These are the owner's choices: the chat and search use them for everyone. Only the owner can change them."
- **Model** and **Agent and search** cards: a `<dl>` instead of the form, one row per choice with the form's labels (`dev/ownersChoices.ts`): label in `--muted` on the left, value in `--text`, weight 600, on the right, a 1px `--border` line under each row; on a phone a long value wraps under its label. Not a disabled form: a disabled fieldset is drawn at 55% and its text drops under 4.5:1.
- No save bar, no Reset, no Find models. The model check and the retrieval check each say in one `.meta` line that only the owner can run them, and why; the saved runs, the index, the map and the report stay. Nothing animates. *Checked* by the browser check B29.5 (both themes, 400px and 1400px, Firefox and Chromium) and the words by `npm test` B29.4.
- **Since B45 (2026-10-19)** this is the **Trusted** person's page, and it has the search playground (it runs with the owner's choices). A **Viewer** gets no Dev item in the sidebar or the tab bar; typing `/dev` shows one `.muted` line, "The Dev page is for people the owner trusts with Patch's internals. Ask the owner if you need it.", and nothing else. *Checked* by B29.5 and B45.41.

#### 5.6.5 The owner's intro and one name, "Dev" (B50, #95, 2026-10-19)

- The page is **Dev** everywhere: the sidebar, the tab bar, the breadcrumb and the title (the title said "Dev panel").
- The owner's intro, two `.page-intro` lines in `--muted`: "Tune the model, the agent and search, then try a query to see each step. Your choices apply to everyone's chat." and "Who else sees this page: Trusted people read it and use the playground; Reviewers change their own copy, which applies only to them; Viewers don't see it. You pick each person's role on Settings, under Requests." It said `DEV_PANEL=false` before: a server setting, now in the README. Trusted and Reviewer keep their notes (§5.6.2, §5.6.4).
- The report's card is **Model-check report** (GLOSSARY.md: "model check", never "eval"). Not "Model check": that is the card above it, which runs the check.
- *Checked* by B50.1 (intro, title, report card; light and dark, 390px and 1440px, intro at 4.5:1 by B50.9) and `npm test` B50.1.

#### 5.6.4 The reviewer's Dev page (B45, 2026-10-19)

- A Reviewer gets the owner's form (every control, Reset, Find models, the playground, the save bar), but their saves are their own copy. In place of the intro, one note (`role="note"`): "Your settings apply only to you: your chat and the playground use them, everyone else keeps the owner's." then "They start as the owner's." or, once they saved, "You've changed them." and a **Back to the owner's settings** button (a plain pill, §5.3). The button applies at once (no save bar step: it drops the copy and the bar says "✓ Changes saved"); it shows only while there's a copy, so it never sits disabled.
- The note follows the §5.7 edge rule: `--text` on the surface, a 3px `--accent` edge, radius 14px; the button sits at the end of the line and wraps under the text on a phone.
- The model check and the retrieval check keep their "Only the owner can run it" lines: they spend the owner's key. Nothing animates. *Checked* by B45.42 (390px and 1440px, light and dark, Firefox and Chromium, contrast 4.5:1, the edge, no sideways scroll, Back by keyboard) and the words by `npm test` B45.23.

#### 5.6.3 Dev page layout (B39, 2026-10-19)

- Over 900px, two columns: **Model** then **Index** stacked on the left, **Agent and search** on the right, spanning both rows. The cards above the playground used to sit in grid rows, so Index started under the taller Agent and search card and left a large hole under the short Model card (the owner's report, 2026-10-19). Settings had the same hole (DECISIONS.md, 2026-10-16).
- The DOM order stays Model, Agent and search, Index: Tab order and the one-column order don't change. That is why it is a span in the grid (`.span-rows`, `grid-template-rows: auto 1fr`), not two column containers as on Settings: those would put Index before Agent and search in the DOM.
- The second row is `1fr`: when Agent and search is taller than Model and Index together, its extra height goes to that row only, so Index still starts one gap under Model (*checked*: with `auto auto` a 90px hole opened). When Model is the tallest (a local model picked), Agent and search simply ends higher.
- At ≤ 900px one column in DOM order, the span off, one 1.2rem gap between cards. The same for the owner and the read-only page (§5.6.2). *Checked* by B39.1 (1400px, light and dark, a local model, the read-only page) and B39.2 (400px, light and dark, owner and read-only, no sideways scroll).

### 5.7 Settings parts

![Settings](img/settings-light.png)

- Fieldsets ("Alert me when", "Timing"): radius 18px, nested-card fill.
- Delivery channels: one soft card each (radius 18px). The "ready" / "not set up" pill hugs its text (it must not stretch).
- Callouts (warning boxes): radius 14px. The reset is its own warning card, **Start over** (below).
- **Save bar**: sticky at the bottom of Settings and Dev, floating as a rounded card 0.8rem above the bottom, with "All changes saved" / "Unsaved changes" on the left and Discard / Save changes on the right. It keeps 96px clear on the right for Patch's button. On phones (≤ 800px) 96px leaves too little room and the bar wrapped to two rows, so there it floats just above Patch's button instead (A13, 2026-10-14; the browser check A13.6 checks it never overlaps his button at 400px and 1400px). **On a phone it shows only with something to say** (B50, #95): unsaved changes, saving, "✓ Changes saved" (until the next edit or leaving the page) or an error. Idle it is visually hidden (1px, clipped) but stays in the accessibility tree, so its status region announces "Unsaved changes" on the first edit; its buttons are disabled then, so nothing hidden takes focus. It took two rows on every phone screen. A desktop always shows it. Nothing animates: it appears and goes at once. *Checked* by B50.2 (Settings and Dev, 390px and 1440px).
- Text on the soft status fills ("Saved for later" chip, "urgent" tag, error messages) is `--text`, with the warn or error colour as an edge: `--warn` on `--warn-soft` is 3.9:1 and `--error` on the surface 4.2:1, both under 4.5:1 for small text (A13, 2026-10-14). Since the review fixes (2026-10-15) the light `--error`, `--warn` and `--ok` are darker (`#cf1b3e`, `#9c5508`, `#0d7b50`), so they also pass as text: `--error` 5.4:1 on the surface and 4.6:1 on `--error-soft`, `--warn` 5.1:1 on `--warn-soft`, `--ok` 5.3:1 on the surface (checked by the browser check A02.3, both modes). The edge rule stays.
- The page heading inside Settings and Dev is hidden: the top bar already names the page.
- **Show Patch's welcome (2026-10-16)**: a switch at the end of the "Patch's answers" card (Settings has no theme or appearance card; the banner is Patch's, so it sits with Patch's other choice). Same look as "Send alerts" (`.switch-row`): "Show Patch's welcome on the dashboard", and under it "Remembered in this browser, not saved to the server. Applies at once." (`aria-describedby`). It shows the current value: on unless the banner was closed (§5.8). Off hides the banner, on brings it back on the next visit to the dashboard, no reload. A per-browser convenience (§11), so it applies at once and is not part of the save bar: it never makes the bar say "Unsaved changes", and needs no API. With storage blocked it still works for the session. Nothing animates. *Checked* by the browser check W.1 to W.5 (both themes, 400px and 1400px, Space by keyboard, blocked storage).
- **Two parts (B48, #97, 2026-10-19)**: **Yours**, for everyone (the owner too), then **This Patch**, the owner's only (hidden for anyone else; the API refuses its routes too). Each part opens with its heading on the page background (`h2`, 1.3rem Fredoka, `--text`) and one `.page-intro` line in `--muted` ("Your profile, watchlist, alerts and answers. Everyone who uses Patch has their own. Edits wait for Save changes, at the bottom of the page." (the last sentence B50: the bar is hidden on a phone until an edit) / "Only you see this part: it sets Patch up for everyone who uses it."), 1rem more space before the second part. The cards' titles are `h3` under them (same look as an `h2` card title); headings inside a card are `h4`. **Yours**: the Watchlist across the top, then left Profile, Connected accounts (sign-in on), Alerts; right Patch's answers, Priority and due dates; then **Start over** across both columns, the last card (B50; B48 had Demo data at the end of the right column). **This Patch**: Requests first, at the top of the right column (the card the owner acts on; `/settings#requests` lands on it), then Refresh runs; Delivery then Data on the left (B50: Data moved under Delivery). The right column comes first in the DOM, so Tab and a phone's one column start with Requests; the grid puts it on the right. Why this split balances: since B50 Delivery shows 3 alerts (about 990px at 1440px), so Delivery and Data (about 1,450px) against Requests and Refresh runs with 20 runs (about 1,800px) end about 350px apart; with Data still on the right they ended about 1,265px apart (measured in Chromium 2026-10-19). B48 had Delivery alone, with its 20 alerts (about 2,440px). Still no CSS `columns`. *Checked* by B48.30 to B48.32, SL.1, SL.2.
- **Anyone but the owner (B48)**: only "Yours". Their Alerts card has no channels (their alerts show in Patch only) and says so in a note under its intro: "Your alerts show here in Patch (Recent alerts, the New badge). Phone and email alerts go to the owner." (`--text` on the nested fill, a 3px `--accent` edge, radius 14px). Under it, where the owner has Refresh runs, one `.meta` line: "Patch checks for new CVEs every 6 hours (set by the owner).", "Patch's checks for new CVEs are paused (set by the owner).", or in snapshot mode "Patch reads a snapshot that never changes, so it checks for no new CVEs (set by the owner)." No quiet hours (nothing is sent, so nothing is held). The dashboard's "Schedule and refresh runs →" link is the owner's only. *Checked* by B48.32 (390px and 1440px, light and dark, the note at 4.5:1 with its 3px edge).
- **Profile card (B48, #77)**: the first card of "Yours", every user. A `.meta` line: "Patch knows you only by your account. A display name is optional: only your user menu shows it. Nobody else sees it." (B50, owner 2026-10-19: decision records always say "you"; B48 put the name in them.) Then "Display name (optional)", a text box taking the rest of its row (at least 12rem, so on a phone it wraps under its label), empty by default, and under it "Without one, the menu says "Your account". Decision records always say "you". At most 60 characters." (`aria-describedby`). It saves with the page's save bar (trimmed, spaces made one; over 60 characters a `role="alert"` line says so and nothing is sent). With a name saved, **Remove my name** (a link button) removes it at once, outside the save bar, and the status line says "Name removed: your user menu says "Your account"." Nothing animates. *Checked* by B48.33 (keyboard, 390px dark, 1440px light).
- **Layout (2026-10-16; parts since B48)**: within each part, packed columns grouped by meaning (above). Each column stacks its cards with the 1.2rem gap, so a short card never leaves a hole. Two real column containers, not CSS `columns`: DOM order = reading order = Tab order (Watchlist, the left column, the right). At ≤ 900px one column in that same order. Why and the measurements: DECISIONS.md, 2026-10-16. *Checked* by SL.1, SL.2.
- **Delivery's setup blocks (2026-10-16)**: Alert links, Phone push (ntfy), Telegram (B57) and Email (SMTP) are native `<details>`, folded by default, under the channel rows (which stay in view with their tick box, pill and Send test). Each block is one nested card (nested fill, radius 18px); its summary is the header: a chevron, the name in bold, then its state: "set up" / "not set up" / "set in the server's environment" (alert links: "phones can open it" / "this computer only"), plus "· unsaved changes" while it holds an edit. `--text` on the nested fill. Folded, its fields stay in the page, so edits survive folding. Ticking a channel that isn't set up opens its block; a failed save opens the blocks it names (else the ones with unsaved edits) and focuses the first field. Keyboard: Tab reaches each summary, Enter or Space opens and folds, the focus ring is the accent outline. Nothing animates: the chevron turns with no transition, so reduced motion needs nothing extra (scene SL.10). *Checked* by SL.3 to SL.10 (light, dark, 400px, 1400px).
- **Requests card (B38, #81)**: the owner's only, and only with sign-in on; the first card of "This Patch", at the top of its right column (B48; it was the last of the left column). An alert's tap opens `/settings#requests`: the card scrolls into view (again while the page around it loads, until you scroll or 3 s pass), with 1rem room above (`scroll-margin-top`). A `.meta` line: "N waiting. Only you see this card and the notes." (or "No one has asked…"); without names from Clerk, a `role="note"` line says why. Then one nested card per person (nested fill, radius 18px, as the delivery channels), newest first: the name in bold (else the user id), the email in `--muted`, and the status as a word in a small tag on the right: `--text` on the surface with a 3px edge (`--warn` waiting, `--ok` approved, `--error` refused; radius 4px, so the edge stays a bar). Under it "Asked … UTC · Approved by you … UTC" (0.8rem). The note, a stranger's text, as plain text in its own block (surface fill, a 3px `--accent` edge, line breaks kept, long words wrap), labelled "Note from <name>". Then the buttons (pills, named "Approve: <name>" etc.): waiting → **Approve** (primary), Refuse; approved → Remove; refused → Undo refusal, **Approve**. The result in a status line ("Alice approved: Patch opens for them on their next visit."). Nothing animates. *Checked* by B38.43 (owner only, plain-text note, Approve by keyboard, Undo, Remove, the alert link, 390px and 1440px, light and dark).
- **The role choice on the Requests card (B45, #90)**: on a waiting or approved person, a row above the buttons: "Role" in bold, a native `<select>` (§5.3; Viewer, Trusted, Reviewer; named "Role for <name>"), and what the picked role allows in 0.8rem `--text` (tied by `aria-describedby`, it changes with the pick). A waiting person's Approve gives the picked role (Viewer unless changed). On an approved person a primary **Save role** button ("Save role: <name>") appears only when the pick differs from the saved role; the status line then says "Bob is now Reviewer: it applies on their next page load." A refused person has no choice (approving them makes a Viewer). A native select, not a set of radios: three options fit one control on a phone, and keyboard and screen readers work as the platform does. On a phone the hint wraps under the select. Nothing animates. *Checked* by B45.40 (keyboard pick and Approve, Save role, 390px and 1440px, light and dark, contrast 4.5:1, inside the card).
- **Connected accounts card (B38, #81)**: every signed-in user; in "Yours", right under Profile (B48; it was the last card of the right column). A `.meta` line on what linking does, then one nested card per way to sign in: "Password" (when set), each linked provider with its email or username in `--muted`; a failed link with Clerk's reason as a line with a 3px `--error` edge. Each linked provider has **Unlink**, except the last way to sign in, which says "Your only way to sign in: link another first." (3px `--warn` edge, `--text`). Under the list, **Link Google** / **Link Discord** for those not linked ("Opening Discord…" while Clerk answers), which leave for the provider and come back to `/settings#connected-accounts`. Errors in a `role="alert"` line. Nothing animates. *Unverified* in the browser: it needs a real Clerk user (the browser check has none); its rules are checked by `npm test` B38.30–B38.33.
- **Watchlist card (A15b, 2026-10-15)**: the first card, across both columns. The fixed product list as checkboxes (by name, in a grid that wraps), then "How you run them" and one fieldset per ticked product, in watch order (as every Settings fieldset: nested-card fill, radius 18px, no border; legend = the product in `--text`): Usage, Version (placeholder by ecosystem: `e.g. 0.3.27`, `3.1.0`, `v0.12.3`), Internet-facing. Products without version data say so ("No version data for Dify…", "…only code commits…"). It saves with the page's save bar: one Save changes saves the watchlist and the other settings, Discard brings both back. A rejected save (a version that doesn't fit the ecosystem, an unknown product) shows its plain message inside the card (`role="alert"`) and the bar keeps "Unsaved changes". A failed save of the other settings (B20) does the same in each card with unsaved edits: "Not saved: … Your changes are still here; Save changes tries again." The edits stay. A change made by Patch (`update_watchlist`) shows in the card at once; unsaved picks stay. At 400px the fieldsets stack in one column. *Checked* by the browser check A15b.1, A15b.8.

- **Start over (B50, #95, 2026-10-19)**: the last card of "Yours", across both columns, every user. It was "Reset demo data" in a red-outlined box, first in Data, then in B48's Demo data card, and it said nothing of the decision history it deleted. The card is the warning: a 2px `--error` edge inside it (`inset` box-shadow, so it keeps its size), text in `--text` and `--muted` (the §5.7 edge rule). A `.meta` line, "Resets everything you set up in Patch to the defaults. It can't be undone. It deletes:", then a list of exactly what (`frontend/src/startOver.ts`, by role): the watchlist and how you run each product; every CVE status, with its whole decision history; the alert rules, the priority policy and the explain level; the alerts log, the New marks and unapproved proposals; for the owner also the channels, the schedule, held and retried alerts, and the Dev page's choices (everyone's chat goes back to the defaults); for a Reviewer their own copy of the Dev settings. Then what stays ("Kept: your display name." and, the owner, the server settings). "Type `reset` to confirm" and **Reset all my data** (`--error-soft` fill with an `--error` edge once enabled). Nothing animates. *Checked* by B50.6 (390px and 1440px, light and dark, the edge, 4.5:1, each role's list).
- **Data card's first line (B50, #95)**: all six sources: "A snapshot of OWASP, MITRE ATLAS, NVD, CISA KEV, EPSS and OSV.dev. As of …" or, live, "Live CVE data from NVD, CISA KEV, EPSS and OSV.dev; OWASP and MITRE ATLAS from the snapshot. As of …" (it named four). *Checked* by `npm test` B50.7.
- **No server names in the words (B50, #95)**: the channels' lines say what to set and where, in words ("Set a topic (a long random name) under Phone push (ntfy), below."), never `notify-send`, `SMTP_HOST`, `ALERT_EMAIL_TO`, `NTFY_TOPIC`, `backend/.env` or `FEEDS=fake`. The README maps each to its setting. Only the owner sees these lines; anyone else's `/settings` holds no channels at all.
- **The owner's server settings (B26, 2026-10-16)**: shown to the owner only; anyone else sees none of them. Each sits in the card it changes, as an ordinary Settings fieldset, saved by the page's save bar: **Data source** on the Data card (Snapshot / Live radios, then the optional NVD API key); **Quiet hours are in** (a time zone select, every IANA zone, "UTC" first) in the Alerts card's Timing; **Alert links**, **Phone push (ntfy)** and **Email (SMTP)** fieldsets on the Delivery card, under the channel list, each folded in its setup block since 2026-10-16 (above). A **secret** is a masked box (`type=password`) that never shows what's saved; the line under it says only "Saved. Type a new one to replace it.", "Not set.", "Saved when you save." or "Removed when you save." (that one with the warn edge), and a saved one has **Remove** (then **Keep** to undo), both link buttons with the secret's name for screen readers. A setting set in the server's environment is disabled with "Set in the server's environment, which wins." under it (B50: no variable name; the README maps each setting to it). The app address shows what tapping an alert does, as a line with a status edge (`--ok` when a phone can open the address, `--warn` when not) and `--text` inside; "Use this page's address" fills it in. The time zone starts as the browser's while nothing is saved (and no quiet hours are saved yet), with "Your browser's time zone. Saved with your quiet hours". A test alert's preview adds what a tap does. Address and secret boxes take the rest of their row, at least 12rem, so on a phone they wrap under their label; no new motion. *Checked* by the browser check B26.9 to B26.13 (light, dark, 400px, keyboard, reduced motion).
- **Telegram (B57, #102, 2026-10-20)**: a fourth channel row after Phone push (ntfy), like the others: tick box, **Telegram** in bold, the "ready" / "not set up" pill, "A message from your own bot in the Telegram app; free. High and urgent ring, the rest arrive silently.", the server's detail line ("To your chat, from your bot." / "Set the bot token and the chat id under Telegram, below.") and **Send test**. Its setup block **Telegram** sits between Phone push (ntfy) and Email (SMTP) and works like the others (folded, its state on the summary, ticking it while not set up opens it). Inside, first the owner's one-time steps as a numbered list (`.setup-steps`, 0.85rem, `--text` on the nested fill, labelled "How to set up Telegram"): @BotFather and `/newbot`, paste the token, press Start in the bot, Find my chat id then Save and Send test. Then **Bot token**, a secret box like ntfy's topic (masked, never sent back, Remove/Keep), with "From @BotFather. Anyone with it controls your bot: keep it secret. Lost or leaked? /token in @BotFather makes a new one." Then **Chat id**, a text box taking the rest of its row (at least 12rem, so it wraps on a phone), and a **Find my chat id** pill button ("Asking Telegram…" while it waits). Under it one line (`aria-live="polite"`): before a search a `.meta` hint ("Your own chat is a number; a group's starts with -. A channel can be @its_name."); after it `--text` with the §5.7 edge (3px): `--ok` "Found your chat with <name>. Its id is filled in: save to use it." (other chats listed by name, kind and id), `--warn` "Your bot has no messages from the last 24 hours. Open it in Telegram, send it any message, then try again.", or `--error` with Telegram's words. Set in the environment: the chat id box disabled, no button, the env note. A test alert's preview says what the button does ("Open in Patch opens Patch at CVE-…" or "The message has no Open in Patch button: …"). The Delivery callout names the bot token next to the ntfy topic. Nothing animates (scene B57.18). Anyone but the owner sees none of it (B48, B50). *Checked* by B57.15 to B57.18 (390px and 1440px, light and dark, 4.5:1 for the steps and the found line, the 3px edge, inside the card, no sideways scroll, by keyboard, hidden for a Viewer).
- **Where live data comes from (B28, 2026-10-16)**: in the owner's Data source fieldset, under the Live radio and before the NVD key, one line (`.feeds-line`, radius 14px, 0.85rem, `--text`, the §5.7 edge rule). Real feeds (`FEEDS=real`, the default): "Live: NVD, CISA KEV, EPSS and OSV.dev" with a 3px `--ok` edge, no fill. Fake feeds: "Live: the made-up test data, not the real feeds" (B50: it named `FEEDS=fake`), bold, on `--warn-soft` with a 3px `--warn` edge, a warning that can't be missed. Shown in both modes, so the owner sees it before switching to Live. Owner only, like the rest of the fieldset. Static text: not focusable, nothing animates. *Checked* by B28.7 (light, dark, 400px and 1400px: the colours, the 3px edge, contrast at least 4.5:1, inside the card, no sideways scroll), the words by `src/feeds.test.ts` (B28.6).

### 5.8 Welcome banner (dashboard)

- Above the dashboard: white-to-soft-purple card (radius 28px). Patch (110px, idle in a variant picked on page load, §8.3) on the left, the head rising over the top edge. Title "Hi there! I'm Patch, your security sidekick." (1.25rem Fredoka, purple), one line of help ("I watch the CVEs on your watchlist and can explain any of them, or how to defend against them. Just ask."; "your LLM stack" until B43, GLOSSARY.md says watchlist), an "Ask Patch" button.
- **On a phone (≤ 640px, B43)**: Patch at 64px beside the title (the head still over the top edge, −1.6rem), the help line and the button under both, left-aligned; the title keeps clear of the ✕. About 200px tall at 390px (was about 330px with the stacked 110px Patch). *Checked* by B43.10 (at most 250px, Patch 64px, head over the edge, title beside him and clear of the ✕).
- A quiet ✕ in the top right (32px round, muted, soft purple on hover). Once closed, it stays closed in that browser, until "Show Patch's welcome on the dashboard" on Settings (§5.7) turns it back on. The ✕ and the switch share one value (`frontend/src/welcome.ts`): closing the banner turns the switch off.

### 5.9 CVEs page and the "Top 5 open CVEs" card (A04b, 2026-10-14)

- **CVEs page**: one card, "CVEs on your watchlist", at the page's full width (no side column). Filters (product, severity, status, "In CISA KEV only"), a "Published since …" chip with a ✕ when a tile set it, the count and sort order, the table, "EPSS by FIRST", paging.
- **Filters in the URL**: `?product=langflow&severity=CRITICAL&status=open&kev=1&since=2026-09-14`. Defaults (all watched, any severity, open) add nothing. A filter change replaces the URL (Back doesn't step through filters); malformed values are ignored. A dashboard link may carry several products (`?product=langflow,ollama`, A15b): the Product select then shows them as one more option, "Langflow + Ollama"; picking another option replaces it. The select itself still picks one product.
- **New (B05, 2026-10-15; until seen since B40, 2026-10-19)**: rows a check found new that the user hasn't seen yet (GLOSSARY.md) get a **"New"** chip after the id (and the KEV chip): `--text` on `--accent-soft` with a 1px `--ok` edge (the §5.7 edge rule; the word says it, so colour is never the only cue), title "New: a check found it, and you haven't opened it yet". A checkbox **"New, not seen yet"** after "In CISA KEV only" filters to them (`new=1` in the URL, by the same rules as the other filters). It shows in live mode only, or when a link set it (so it can be cleared); the snapshot never changes, so nothing is new there. Before the first check nothing is new. Keyboard: Space on the focused box. Stacked cards (phones): the chip stays next to the id. The chat header's chip says "New, not seen yet". No animation of its own. *Checked* by B05.6–B05.10 (light and dark, 400px and 1400px, chip contrast at least 4.5:1, keyboard, the URL and a reload).
- **Mark all as seen (B40, 2026-10-19)**: a plain pill (§5.3) right after the New box, shown with it (live mode, or a link set the filter) while anything is new for you, whatever the other filters; its title says how many ("2 new CVEs you haven't opened"). Pressed, nothing is new any more, the list reloads, the button goes and the focus moves to the New box (never lost to the page). Opening a CVE's page (§5.15) takes that CVE out of New; the page still shows the chip on that visit, since it was new when you opened it. A row on the dashboard or in the list doesn't count as seen (why: DECISIONS.md, B40). Enter or Space on the focused button. On a phone it wraps next to the box. No animation. *Checked* by B40.7–B40.10 (opening a page, Back and a reload; keyboard and focus; no button before a check; light and dark at 390px and 1440px, text contrast at least 4.5:1, at least 24px high, no sideways scroll).
- **Table columns**: CVE (id as a link to its own page, §5.15; KEV chip, possible-match chip, two-line summary), product, severity, published, OWASP, EPSS, status with the row's actions under it. The headings Priority, Due, OWASP, EPSS and Verdict have a tip (§5.18), the others none. The OWASP code's tip names the category and its list; the Possible match chip's tip says the product was matched on the description's text, not on NVD's product id (CPE), and OSV.dev doesn't confirm it (B44). The KEV chip's title says "In CISA KEV: known to be exploited"; the KEV date shows once, in the Due cell (B44, why: DECISIONS.md).
- **Filters on a phone (B44, 2026-10-19)**: on a phone (≤ 800px, the tab-bar layout, §4.2) the filters fold behind a plain pill "Filters (n on)" (n: each filter the URL carries; the defaults carry none) with the More chevron, `aria-expanded`, closed on load. The count line ("490 CVEs · by priority…") stays in view next to it. Open, the controls show as before, under it. Wider, and beside the pinned chat on a desktop, the pill is hidden and the controls sit in the filter row as before (pinning then doesn't change the height above the rows, so the page keeps its place, A07.2). No animation. Before, the open filters took about a third of a 390×844 screen. *Checked* by B44.9.
- **Short rows (B36, 2026-10-18)**: a row shows **one main action** and **More**. The main action is the first of the status's actions (open or accepted: Mark fixed; review due: Accept again; fixed or not affected: Reopen). **More** is a native `<details>`: its summary is a plain pill (§5.3, 0.75rem) with a chevron that turns when open, named "More actions for CVE-…"; opened, the other status actions and "Ask about this" stack under it inside the row (nothing floats, so the table's scroll box never clips it and a phone never shows it off-screen). Enter or Space opens and closes it; Tab then goes on into its buttons. Every action is also on the CVE's page (§5.15). The cells run on fewer lines: the priority chip and its reasons as one text; the verdict chip and its reason on one line, "Fixed in … · Who acts: …" on the next; cell padding 0.35rem 0.4rem, line height 1.35. At 1440×900 a row is about 71px (was 147px): 12.7 rows per 900px, 9 in view on load (was 4). A phone card is at most about 455px at 390×844 (was 591px). Why: DECISIONS.md, 2026-10-18. *Checked* by B36.5 to B36.10.
- **Verdict (A15)**: a Verdict filter (in the URL as `verdict=`) and a Verdict column before status: a chip (Affected: `--error` edge on `--error-soft`; Not affected: `--ok` edge; Unknown: `--border` edge; text `--text`), the reason, "Fixed in …" (each package's fix when OSV lists more than one: "Fixed in langchain 0.2.0, langchain-community 0.2.19", B67), "Who acts: …". On open rows whose verdict is not affected, a "Mark not affected?" button (green edge) replaces the plain "Not affected" action: a suggestion only the user clicks. The pager keeps 96px clear on the right for Patch's button.
- **Watchlist (dashboard, A15b, 2026-10-15)**: editing moved to the Settings card (§5.7). The dashboard's card at the top of the side column (above the tiles on a phone, B43), still titled "Watchlist", is a **product filter**: a fieldset "Show the tiles, charts and Top 5 for" with an "All" pill and one toggle pill per watched product, in watch order. Pills are buttons with `aria-pressed`: picked = `--accent` edge on `--accent-soft` and a ✓ in `--accent` (hidden from screen readers), so the state isn't told by colour alone; 2rem high, a target big enough to tap. Products with open CVEs in CISA KEV get a dot in `--error` after the name, and their accessible name and title say so ("Langflow: open CVEs in CISA KEV"). Picking narrows the tiles, the three charts and the Top 5 card to those products; picking every product is the same as All. Then "Edit watchlist in Settings →".
  - **In the URL only**: `/?product=langflow,ollama`. All adds nothing; nothing is remembered in the browser, so a fresh dashboard shows every watched product. A change replaces the URL. Unknown or unwatched products are ignored and dropped from the URL, so a product removed from the watchlist (on Settings or by Patch) drops out of the filter.
  - **Links carry it**: each tile and "See all CVEs →" adds `product=…`, so the CVEs page shows the tile's number.
  - **One truth**: the watchlist is in the backend's state; Settings and Patch's `update_watchlist` both announce a change, and the dashboard reloads at once.
  - **Patch knows it**: the page context sends `{page: "dashboard", product: "langflow,ollama"}`; the chat header's chip says "on Dashboard · Langflow + Ollama". "What should I fix first?" ranks within those products.
  - **Where it sits (B43, 2026-10-19)**: in the page it comes right after the welcome banner, before the tiles. On a phone (≤ 1000px, one column) it is therefore above the tiles, the pills one row that wraps: you set the filter before you read the numbers (it used to drop under everything). Over 1000px the grid (`grid-template-areas`) puts it at the top of the side column, beside the charts, as before; the main column spans the filter's row and the side cards' row, which is `1fr`, so the side cards start one gap under it (the §5.6.3 rule). Tab order at every width: the banner, the filter, the tiles, the charts, the side cards (why: DECISIONS.md, B43). It fades up with the side cards (0.12s). *Checked* by B43.5 (390px and 1440px, the next Tab after Ask Patch is All).
- **Narrow (phones ≤ 800px, or the chat pinned and the table ≤ 760px)**: each row is a stacked card: radius 18px (`--radius-nested`), `--accent-soft` fill, 0.6rem apart. The CVE id there is `--text`, underlined (B49: `--accent` on that fill is 4.48:1). The id and summary on top, then a grid of labelled cells (product, severity, published, OWASP, EPSS; label 0.7rem muted uppercase), then status and the actions on one wrapping line. The header row hides; each cell names itself. *Checked* at 400px and with the chat pinned at 1400px: no sideways scroll, every action in view.
- **Top 5 open CVEs** (dashboard, 4th card of the main column): the CVEs page's first 5 rows in its order (id linking to its page (§5.15), KEV chip, priority chip, product, severity, "Due …" with the overdue mark, the reasons on their own muted line), then "See all CVEs →" to `/cves`. Both sort by priority (A16). The "No fix yet" chip keeps a 0.4rem gap after "Decide by …" (B43; it touched the date before; *checked* by B43.12).
- **Priority and due date (A16)**: two columns after CVE. **Priority**: a chip with the word (Urgent: `--error` edge on `--error-soft`; High: `--warn` edge on `--warn-soft`; Normal: `--accent` edge on `--accent-soft`; Low: `--border` edge; text `--text`, like the verdict chip), the reasons under it ("in KEV · EPSS 99th percentile"). **Due**: your due date (bold), "Overdue" with the warning icon (icon in `--error`, word in `--text`) on its own line, "by your policy: …" (muted), and the KEV deadline as its own muted fact ("CISA KEV deadline …") only when it's another date than your due date: with the KEV deadline adopted, "by your policy: KEV deadline" already says it (B36). In the list, "by your policy:" is visually hidden (screen readers still read it; the Due heading's title says it), so the line reads "KEV deadline" or "published + 90 days". A **closed CVE** (B33: fixed, not affected, accepted before its review) shows a muted "—" in both cells (`--muted`, with "No priority: closed" and "No due date: closed" for screen readers, the reason on hover), and the KEV deadline stays under the Due dash; closed rows sort after every open one. The count line says "by priority, then due date". The KEV tile's "Overdue since …" is against your due date. Settings has a "Priority and due dates" card: days per level, the KEV-deadline switch, the EPSS threshold.
- **Decisions (A16b, 2026-10-14)**: every status change opens the **decision dialog** (native `<dialog>`, modal): a card on `--surface` (radius `--radius-card`, `--shadow-bubble`) over the page dimmed with `--text` at 45%; title "Accept the risk of CVE-…", "Mark CVE-… not affected", "Mark CVE-… fixed" or "Reopen CVE-…"; named fields; Cancel and a primary submit button on the right; a server error in the dialog (`role="alert"`, `--error` edge on `--error-soft`). Focus goes to the first field, Tab and Shift+Tab wrap inside it, Esc closes it without saving, focus returns to the button that opened it. No animation. At 400px it fits the window.
  - **Accept**: Reason (required), Review date (required, a date input, default the as-of date + 90 days, after the as-of date), Compensating control (optional).
  - **Not affected**: the **justification picker**, a fieldset "Why isn't it affected? (required)" (nested-card fill, radius 18px) with the five VEX justifications as radios, then Note (optional). "Mark not affected?" opens it with "Vulnerable code not present" picked and the verdict's reason as the note; the user confirms.
  - **Fixed, Reopen**: Note (optional), focused.
  - **Row actions**: open → Mark fixed, Not affected (or the suggestion), Accept risk; accepted → Mark fixed, Reopen; review due → Accept again, Mark fixed, Not affected, Reopen; fixed or not affected → Reopen. The first is the row's main action, the rest are under More (B36, above; `frontend/src/cveActions.ts`). Status filter gains "Accepted" (`status=accepted`).
  - **Under the status**: the current decision in 0.75rem (accepted: "Review on …" or "Review was due …", the reason, "Control: …"; not affected: the justification and note; fixed or reopened: the note). Review due adds a **"Review due"** chip next to the status (`--text` on `--warn-soft` with a `--warn` edge).
  - **History**: a `<details>` "History (n)" (accent, bold; named "History of CVE-…: n decisions") under the actions; open, an ordered list, oldest first: date and time in UTC (muted), the status in bold, its facts, "by you, on the CVEs page" or "by you, in the chat" (every record in your history is your own: B44, `decisionWho.ts`; "by unknown" for a status saved before decision records). Stacked cards: full width.
  - **No fix yet**: in the Due cell of an open CVE with no fixed version, "Decide by" (muted, small) above the date, then a **"No fix yet · open N days"** chip (`--text` on `--warn-soft`, `--warn` edge; a rounded box, radius 14px, when it wraps) instead of "Overdue", and "accept, mitigate or replace · by your policy: …". The Top 5 card says "Decide by …" with the same chip; the KEV tile says "No fix yet, decide by …" when its CVE has no fix. Patch's CVE card says "decide by" and shows the chip, and an accepted CVE's reason and review date.

### 5.10 Data freshness and Check now (B02, 2026-10-15)

- The dashboard's side card "Data freshness" (`frontend/src/components/Freshness.tsx`), after Recent alerts (the incidents follow it since B43, §5.17). In the head, a status chip (§5.2): **Live** (`live`: `--text` on `--accent-soft` with a 1px `--accent` edge; `--accent` text was 4.48:1, B49) or **Snapshot** (`mock`: `--text` on `--border`). The sidebar's card says "Live data" or "Snapshot" the same way.
- Under the head, one muted line: "Last checked 2026-10-15 09:00 UTC.", "Not checked yet: the live data is still the snapshot." or, in snapshot mode, "A frozen snapshot, as of 2026-10-13." Times are in UTC, as in the backend's messages and run log, so every place says the same time.
- **Check now** (live mode only; also on Settings' Refresh runs card since B59, §5.12, the same component): a plain pill (§5.3), 2.25rem high. While the check runs it says **"Checking…"** with a **spinner** before the word, is disabled and `aria-busy`, at full strength (not the 50% of a disabled button: the word must stay readable). The spinner is a 0.9rem ring in `--accent-soft` with an `--accent` arc, hidden from screen readers; the word tells the state, so with reduced motion (the ring stands still) nothing is lost.
- Then **one line** in an `<output>` (a status region, so a screen reader hears it), `--text` on a soft fill with a 3px coloured left edge (the §5.7 edge rule), radius 14px:
  - Ran: "Done: 2 new CVEs, 1 updated, 1 added to KEV." (zero counts left out) or "Done: nothing new since the last check." `--ok` edge on `--accent-soft`.
  - Then your alerts from that run, by what happened (B34, 2026-10-18), as a second sentence: "1 alert sent, 275 alerts recorded only (not sent), 2 alerts failed, 3 alerts held for quiet hours." (zeros left out; none, no sentence). "Recorded only" always says "(not sent)", so a dry run never reads as alerts that went out. Any failed: `--warn` edge on `--warn-soft`, so the line asks for a look at Recent alerts.
  - Refused: "Checked less than 5 minutes ago. The next check is allowed at 09:05 UTC." or "A check is running already. …" `--warn` edge on `--warn-soft`.
  - Failed: "The check failed (EPSS: …). The data is unchanged." `--error` edge on `--error-soft`.
  - Partial (B20): "Done in part: 1 updated, 1 added to KEV." `--warn` edge on `--warn-soft`. Never "Done" when a feed failed.
- **Partial or failed banner (B20, 2026-10-15)**: under the last-checked line, while the last run (from the run log, so it survives a reload) was partial or failed. `--text` on `--warn-soft` with a 3px `--warn` edge (partial) or on `--error-soft` with an `--error` edge (failed), radius 14px. A bold line, "3 of 4 sources updated at 09:00 UTC · NVD didn't answer · next try 09:05 UTC" (failed: "No source updated at … · … didn't answer · the data is unchanged · next try …"); a list of each failed feed's reason ("NVD: …", wrapping, never wider than the card); and **Retry**, a plain pill (2rem). Retry runs Check now; inside 5 minutes the server refuses and the line says when. The last-checked line says "Not checked in full yet: some sources updated (below)." when no run has had every feed answer. Nothing in it moves.
- **Made-up data warning (B28, 2026-10-16)**: in live mode on the fake feeds, right under the last-checked line, the Data card's warning line (§5.7): "Live: the made-up test data, not the real feeds", bold, `--text` on `--warn-soft` with a 3px `--warn` edge, radius 14px. Not shown for the real feeds, in snapshot mode, or to anyone but the owner (`data.feeds` is null for them). Nothing in it moves. *Checked* by B28.8 (light, dark, 400px, 1400px), the reduced-motion scene `b28_9_feeds_warning`.
- After a check that ran, the dashboard loads again (the watchlist-changed event), so the tiles, charts, Top 5 and the last-checked line show the new data at once.
- **See the new CVEs (B43, 2026-10-19)**: while a check has found CVEs you haven't seen yet (B40's "New", §5.9), a bold link after the line: "See the 2 new CVEs →" ("See the new CVE →" for one), as the check_updates card has (§6.2). It opens `/cves?status=all&new=1`, with the dashboard's product filter (`product=…`), as the tiles do; `status=all`, so the list shows the same number after you closed one from the list without opening it. The number is the dashboard's `kpis.new_unseen` (new and not seen, any status, within the filter), so it comes back after every check and goes once you've opened them or pressed "Mark all as seen". Not shown when nothing is new (always in snapshot mode). Then "Schedule and refresh runs →" (live), each link on its own line. *Checked* by B43.7 (the link after Check now, the list it opens, gone once seen, the product filter, none in snapshot mode) and B43.13 (contrast, 390px and 1440px, light and dark); the words by `src/freshness.test.ts` (B43.3), the count by `backend/tests/test_new_until_seen.py` (B43.2).
- **Sources and licences (B43)**: the sources list (name, count, licence, retrieved, attribution, and NVD's notice, in both modes) is folded into a native `<details>`, closed, at the end of the card: summary "Sources and licences (7)" (bold, `--text`, the browser's marker as on "Show as table", the accent focus ring), above it a 1px `--border` line. Why: about 700px of licences followed the status, and the card is for the status. Still on the page, one click or Enter away; screen readers and the keyboard get the platform's disclosure. Nothing moves. *Checked* by B43.6 (closed at first, after the status, Enter opens and closes it, focus ring), A05.6, A14.11, A14.14.
- *Checked* (B20) by the browser check B20.11 (light and dark, 400px and 1400px, Retry by keyboard, the banner text's contrast at least 4.5:1, the 3px edge) and the reduced-motion scene `b20_14_partial_and_try_again`; the words by `src/freshness.test.ts` (B20.10).
- *Checked* by the browser check B02.9 and B02.10 against the live pair (light and dark, 400px and 1400px, Enter on the focused button, the line's contrast at least 4.5:1) and the reduced-motion scene `b02_9_check_now`; the words by `npm test` (`src/freshness.test.ts`).

### 5.11 Recent alerts (B04, 2026-10-15)

- The dashboard's side card "Recent alerts" (`frontend/src/components/AlertsLog.tsx`), just above "Data freshness". It lists the last 20 entries of the alerts log, newest first; one check's entries keep the order they were sent, so KEV and new CVEs sit above the overdue reminders. Settings' Delivery card shows the same list's last 3 (B50, #95: it repeated all 20), then "All recent alerts on the dashboard →", a link to `/#recent-alerts`: once the list is in, this card scrolls into view with 1rem above it, and stays there while the rest of the page loads (until you scroll or 3 s pass). *Checked* by B50.5 (390px and 1440px, Enter on the link) and B56 (1440px, the charts drawing after the list is in).
- **Each entry**: the title in bold (`--text`); for one alert it is a link to the CVE's page, `/cves/CVE-…`, the same link the notification opens (§5.15; until B35 `#cve=…` and a banner). Then one muted line: the reason and the time in UTC ("In CISA KEV · 2026-10-15 09:00 UTC"; "Digest · …"; "Test alert · …"). A digest adds its counts as a second muted line, never the ids: "1 in CISA KEV · 2 new · 275 reminders" when it mixes what a check found with reminders (B34: due soon and overdue as one count), or by kind when it holds one sort only ("12 due soon · 263 overdue"). Entries are separated by a 1px `--border` line.
- **Per-channel results**: one small pill per channel, 0.75rem, text `--text`, the tone as a 1px edge (the §5.7 edge rule): sent = `--ok` edge on `--accent-soft`; not set up or failed = `--error` edge on `--error-soft`, with the error as its title; recorded only (dry run, preview) = `--border` edge, no fill. The words say the result ("ntfy: sent", "email: not set up", "ntfy: failed (network down)"), so colour is never the only cue. A retried send (B41, 2026-10-19) says its tries, in the same pill, updated in place: "ntfy: failed (network down), trying again at the next check (1 of 3 tries)" (failed tone), "ntfy: sent (2 tries)" (sent tone), "ntfy: failed (3 tries)" (failed tone, the error as its title), or "ntfy: failed, not tried again: no longer needed" (recorded-only tone: the CVE was closed meanwhile, or the channel unticked). Entries saved before B41 read as before. When ntfy.sh refuses this server's address (B55, 2026-10-19; HTTP 429), the error leads with plain words and then quotes ntfy: "ntfy: failed (ntfy.sh is limiting this server's address: try again later. ntfy said: 42901: limit reached…)"; the same words show on Delivery after a failed test send. Telegram (B57, 2026-10-20) reads the same way: "telegram: sent", "telegram: failed (Telegram is limiting this bot: try again later. Telegram said: 429: Too Many Requests: retry after 7)" or "telegram: failed (Telegram refused the message (HTTP 400). Telegram said: 400: Bad Request: chat not found)"; never the bot token. The words come from the server; the pill itself is unchanged. No channel picked: one pill "No channel picked: recorded only". Another user's alert (B09: only the owner's alerts go to the channels): one pill "In Patch only" (B50; it said "In the app only: alerts go to the owner’s channels", which read as if theirs went to the owner), same muted style.
- Empty: "No alerts yet." plus, live, "A check sends them when something on your watchlist needs you." or, in snapshot mode, "The snapshot never changes, so only test alerts from Settings appear here." For anyone but the owner (B50, #95: they have no test alerts or channels): "A check shows them here when something on your watchlist needs you." / "The snapshot never changes, so no check finds any." Their alert counts after Check now say "3 alerts in Patch", not "recorded only (not sent)" (§5.10). *Checked* by B50.9 and `npm test` B50.9.
- Then "Alert settings →" (bold link, like the watchlist card's), to Settings.
- After Check now the card loads again (the data-changed event), so the new alerts show at once.
- No motion of its own: the card fades in with the other dashboard cards (§7.1), which reduced motion already stops.
- *Checked* by the browser check B04.12 against the live pair (a busy check as one digest; one alert's link opening the banner; light and dark, 400px and 1400px, Enter on Check now and on the Settings link, a result pill's contrast at least 4.5:1, no sideways scroll); the words by `npm test` (`src/alertsLog.test.ts`).
- *Checked* (B34) by the browser check B34.5 (the first check lists no reminder, the dashboard's line and Settings' refresh runs say the same "recorded only (not sent)" count); the line with its alert sentence still passes B02.10 (light and dark, 400px and 1400px, contrast at least 4.5:1, no sideways scroll); the words by `npm test` (`src/freshness.test.ts`, `src/refreshRuns.test.ts`, B34.4); the digest's words by `backend/tests/test_alerts.py` (B34.3).
- *Checked* (B41): the try words by `npm test` (`src/alertsLog.test.ts`, B41.7); the retries by `backend/tests/test_alert_retries.py`. *Unverified* in a browser: the browser check's channels are a dry run, so no send fails there. The pill is the same element with longer words.

### 5.12 Refresh runs and the paused schedule (B19, 2026-10-16)

- **Settings' "Refresh runs" card** (`frontend/src/components/RefreshRuns.tsx`). A "Schedule" fieldset (§5.7) with "Check for new CVEs every" (moved here from Alerts' Timing) and **Pause the schedule**, a checkbox with its meaning under it ("No scheduled check starts. Check now and Patch's check still work."). In snapshot mode it is disabled, with the reason as its description (B50, #95): "Only in live mode: the snapshot never changes, so no check is scheduled to pause." *Checked* by B50.8. Both save with the page's save bar. Under it the schedule line from the server (`.meta`): "Every 6 hours · next scheduled check from 2026-10-15 14:50 UTC.", "… the next scheduled check runs at the next tick.", or, paused, "Schedule paused: no scheduled check starts. Check now and Patch still check." in `--text` on `--warn-soft` with a 3px `--warn` edge (§5.7). Snapshot mode: "Every 6 hours, in live mode. The snapshot never changes."
- **"Last 20 runs"** (`h3`), newest first, one line each, separated by 1px `--border`. Each is a native `<details>`: the summary (keyboard and screen readers as the platform does; a ▸/▾ in `--muted` as the marker) has the **result chip** (OK `--ok` edge on `--accent-soft`; Partial `--warn` on `--warn-soft`; Failed `--error` on `--error-soft`; "Skipped: too soon" `--border` edge, no fill; text always `--text`, 0.75rem bold), the trigger in bold (Check now, Schedule, Patch, Command line), and the start in UTC with the duration ("· 2.4 s"); then one muted line: "2 new · 1 updated · 1 added to KEV · 4 alerts sent" (zeros left out; "Nothing new"; a failed run "Nothing written"; a skip "Next allowed 09:05 UTC · asked 3 times"). The alerts are counted by what happened, in the dashboard line's words (B34, §5.10): "… · 275 alerts recorded only (not sent) · 2 alerts failed · 3 alerts held for quiet hours".
- **Opened**: a nested-fill box (radius 14px) with each feed's step ("NVD: answered", "NVD: didn't answer (…)", bold), the new CVEs as links to their pages (§5.15), an alerts error if any, and "Wrote live version 3 · finished …" (or "Wrote nothing: the data is unchanged"). A skip says why. Long errors wrap; nothing is wider than the card at 400px.
- **Check now (B59, #103, 2026-10-20)**, live mode only: under the schedule line, above "Last 20 runs", so it's found without scrolling the runs. The dashboard's own button and line (§5.10, `components/CheckNow.tsx`): a plain pill, "Checking…" with the spinner (disabled, `aria-busy`, at full strength), then the one line in an `<output>` with its edge (Done, Done in part, refused, failed; the same words). After every press, a run or a refusal, the list loads again: the new run, or the "Skipped: too soon" row, is on top without a reload. Not shown in snapshot mode; the card itself is the owner's (B48). The spinner is the one motion; reduced motion stops it and the word still says the state (scene `b59_5_check_now_on_settings`). *Checked* by B59.2 (Checking…, the line, the new run on top, the refusal's skipped row), B59.3 (none in snapshot mode or for anyone else), B59.4 (Enter on the focused button, the line's contrast at least 4.5:1 and its 3px edge, the button at 4.5:1, no sideways scroll; 390px and 1440px, light and dark); the logic by `npm test` (`src/checkNow.test.ts`, B59.1).
- Empty: "No runs yet. Check now, the schedule or Patch starts one." (live) or "The snapshot never changes, so nothing runs."
- **Dashboard (§5.10)**: while paused, under the last-checked line, "Schedule paused" (bold, `--text` on `--warn-soft`, 3px `--warn` edge) and **Resume**, a plain pill (2rem; "Resuming…", `aria-busy`), which saves the setting; the result line then says "Schedule resumed: a check every 6 hours.". In live mode, "Schedule and refresh runs →" links to `/settings#schedule`, which scrolls the schedule into view.
- **Patch's check_updates card (§6.2)**: one muted line with the same schedule words.
- Nothing else moves: apart from Check now's spinner (above), no animation of its own, so reduced motion changes nothing (scene `b19_9_runs_and_paused`).
- *Checked* by the browser check B19.6–B19.8, B19.10 (light and dark, 400px and 1400px, a run opened by keyboard, Resume by keyboard, chip and paused-line contrast at least 4.5:1, the 3px edge, no sideways scroll); the words by `npm test` (`src/refreshRuns.test.ts`).

### 5.13 Sign-in screen and user menu (B10, 2026-10-16)

Only with sign-in on (`AUTH=on`). Off (locally, the tests) neither exists and nothing of Clerk's loads.

- **Sign-in screen** (`frontend/src/auth/SignInScreen.tsx`, `styles/signin.css`): a signed-out visitor sees only this, never the shell. On the page background and glow (§3.3), one card in the middle: `--surface`, radius `--radius-card`, `--shadow-card`, max 26rem wide, centred text. Inside, top to bottom:
  1. **Patch**, 110px, idle in a variant picked on page load, his head over the card's top edge (−3rem), as on the welcome banner (§8.2).
  2. The **brand** as in the sidebar (§4.1), centred, with its dashed line under it.
  3. **"Sign in to Patch"** (`h1`, 1.5rem Fredoka, `--accent`) and one muted line: "Sign in, or make an account and ask the owner for access." (B38; it said "Patch is invite-only…" before)
  4. **Clerk's form** (`<SignIn>`, hash routing, its sign-up steps for an SSO sign-in inside it under `#/create`, B31): its colours, font and input radius come from our tokens, read from the page so they follow the theme switch (`--accent`, `--on-primary`, `--surface`, `--text`, `--muted`, `--border`, `--error`, `--font-body`, `--radius-input`). Its own card shadow, border and heading are off: our card is the frame. Clerk's footer ("Secured by Clerk", and the development-instance banner) stays: the free plan keeps it.
  5. While Clerk loads, "Loading sign-in…" (a status region). If it can't load (Clerk's loader gives up after 15 s), an error line with a 3px `--error` edge on `--error-soft` (§5.7): "Sign-in didn't load. Check your connection, then reload the page." and **Reload**.
- **The view follows the address Clerk sends to (B31, #78; B38, #81).** No step ever leaves for Clerk's hosted pages. Sign-up is open (B38): Clerk's sign-up steps (`#/create`, inside `<SignIn withSignUp>`) are headed **"Request access to Patch"**, with the line "Make an account first. Then you ask the owner to let you in." The invitation view ("Join Patch") and the not-invited message are gone with the invitations.
- **The access screens (B38, #81)**: what a signed-in person sees until the owner approves them, never the shell. The same frame: one card, Patch idling over its edge, the brand, an `h1` and one muted line, the theme switch. Then, by status (`frontend/src/auth/AccessGate.tsx`, words in `access.ts`):
  - **Ask** ("Ask to join Patch"): a labelled textarea "A note for the owner (optional)" (radius 14px, §5.3), under it a muted counter "N characters left. Only the owner sees it." tied by `aria-describedby`; over 280 it reads "N characters too many" in `--text` on `--error-soft` with a 3px `--error` edge (§5.7), and Send says so in a `role="alert"` line without sending. **Send request** (primary) and **Sign out** (plain pill) in a centred row.
  - **Waiting** ("Your request is waiting for the owner"): their note read back in a nested card (§3.5: nested fill, radius 18px, "Your note" label in `--muted`); **Check again** (primary; "Checking…" and `aria-busy` while it asks; "Still waiting…" in a status line after) and Sign out. Approved: the app appears.
  - **Refused** ("Your request wasn't approved", "The owner didn't approve this account for Patch. Thanks for asking."): Sign out only. No form: a refusal is final until the owner undoes it.
  - Moving to a new step (sent, refused) puts the focus on the heading, so a screen reader says it. While `/access` is asked: "Opening Patch", "Checking…"; if it fails, the error line with **Try again**.
  - **Nothing of the app, ever (B46, #81).** No shell, no navigation, no page names, at any address. A tab that showed the app swaps it for the card the moment any call gets 403 `not_approved` (the owner removed or refused them), and coming back to the tab (focus, or the tab shown again) asks `/access` again, so a waiting screen also moves on by itself. The chat kept for the tab (§11, B49) is cleared then, as on sign-out.
  - **"What is Patch?"** under the actions on every step: a plain link (0.9rem, 700, `--text`, underlined, centred) to `/about`, which for them is the landing page in its front-door frame (§5.16) with **Back to your request** as its next step. *Checked* by the browser check B46.1–B46.3 (the 403 swap, back to the tab, the link and back, any address, 390px dark by keyboard) with `/access` and the 403 answered by the check; the backend's answers for the owner's sequence by B46.1 in `backend/tests/test_access.py`. With real Clerk: *unverified* (the owner's check on #81).
  - With sign-in off there are no requests and the app shows at once.
- The light/dark switch (§9) sits in the top right corner, as in the top bar.
- Motion: the card fades up once (0.45s, §7.1), the access screens' too; Patch idles (§8.3). With reduced motion nothing moves (scenes `b10_15_sign_in_screen`, `b38_26_request_access_sign_up`, `b38_44_request_screen`).
- At 400px the card fills the width less 1rem each side; nothing scrolls sideways.
- **User menu** (`frontend/src/components/UserMenu.tsx`): in the top bar, before the light/dark switch. A 36px round button with the primary gradient and the purple shadow. Anonymous by default (B48, #77): a person icon in `--on-primary`, named "Your account". With a display name from the user's Profile (never Clerk's name or email): `--on-primary` initials (Fredoka 600, first letters of the first two words of the name), named "Your account: <name>". It opens a small card under it, right-aligned: `--surface`, 1px `--border`, radius `--radius-nested`, `--shadow-card`; the name (bold), or "Your account" and, muted at 0.85rem, "No display name. You can add one on Settings, under Profile.", then **Sign out** (a plain pill; "Signing out…" while it runs). It pops in like the bubble (0.16s). Esc or a click outside closes it; Esc puts the focus back on the button. Long names and emails wrap. After sign out, the sign-in screen.
- *Checked* by the browser check B10.12–B10.15 (sign-in off: no menu, no Clerk; the screen with Clerk unreachable: Patch over the edge, 400px and 1400px, light and dark, Reload by keyboard, no API call but `/health`) and B38.25 (the request-access sign-up view at 390px dark and 1440px light, no navigation to `accounts.dev`). The access screens: B38.40–B38.42 (390px and 1440px, light and dark, Send by keyboard, the focus on the new heading, the note's limit), with `/access` answered by the check itself. Clerk's sign-up form and the SSO round trip are *unverified* until the owner's check on #78. The form with real Clerk, and the user menu, are checked only by B10.16, which needs the Clerk test instance (#65): *unverified* until it runs, including whether Clerk's element names for the card and heading (`cardBox`, `card`, `header`) still match.

- **Since B42 (#80) the form has its own address, `/sign-in`** (`/sign-in#/create` for Request access). Every other address shows a signed-out visitor the landing page (§5.16). Clerk's steps (a hash route `#/…` on any path, e.g. the old `/#/create`) and an old invitation link (`?__clerk_ticket=…`) still open this screen. After sign-out Clerk sends to `/`: the landing page.
- **Sign-in keeps where you were going (B60, #107).** A signed-out visitor at an in-app address (an alert's `/cves/CVE-…`, `/settings#requests`) still gets the landing page first (DECISIONS.md, B60: who opens a shared link may not know Patch), and its Sign in and Request access keep that address for the tab (§11). After sign-in, or after sign-up once the owner approves, the app opens there instead of the dashboard, once; Back doesn't step through a dashboard they never asked for. With no such address, the dashboard as before. Nothing on screen changes: no new words, no motion. Only same-origin paths are kept, never a link to another site. *Checked* by the browser check B60.7–B60.9 (390px and 1440px), with "signed in" standing in as a load with sign-in off; Clerk's own redirect to it is checked in Clerk's code only (docs/SOURCE-CHECKS.md, Clerk B60), and on a phone by the owner (#107).

### 5.14 Loading screen (#69, 2026-10-16)

What everyone sees until `/health` answers: it says whether sign-in is on, so neither the app nor the sign-in screen can show before it. Deployed with no warm instance, the first visit is a Cloud Run cold start (its time *unverified*, #45). Without this screen the page stayed blank. Why the choices: DECISIONS.md, 2026-10-16.

- **Where**: `frontend/src/components/LoadingScreen.tsx`, `styles/loading.css`; the wait itself is `frontend/src/healthWait.ts`.
- **Layout**: the sign-in screen's frame (§5.13). On the page background and glow (§3.3), one card in the middle: `--surface`, radius `--radius-card`, `--shadow-card`, max 26rem wide, centred text. Inside, top to bottom:
  1. **Patch**, 110px, idle in a variant picked on page load, his head over the card's top edge (−3rem, §8.2).
  2. The **brand** as in the sidebar (§4.1), with its dashed line under it.
  3. The **status line** (an `<output>`, so a status region; 1.5rem Fredoka 700, `--accent`). Not a heading: the app's `h1` is what the browser checks wait on.
  4. **Starting**: "Waking Patch up…" and one muted line: "The server can take a few seconds to start after a quiet spell."
  5. **Offline**, once a try gets no answer in 15 s: "Patch's server isn't answering yet. Trying again…" (B49; it said "Backend offline — retrying", a developer's word), then an error line with a 3px `--error` edge on `--error-soft` (§5.7) that only says when: "Next try in N s." (counting down; "Asking now…" while a try is on its way) and **Retry** (a plain pill, never disabled). Tries repeat by themselves after 2, 4, 8, 16 s, then every 30 s; the app appears as soon as one answers.
- A `/health` that **fails outright** (refused, an error status) is a miss like a timeout: the offline state at once, the same backoff (B46). Before B46 the app showed, saying "Backend offline"; but without `/health` nobody knows whether sign-in is on, so that showed the app's shell to anyone (#81).
- No theme switch: the screen follows the saved or system theme, set before the first paint (§9).
- Motion: the card fades up (0.45s, §7.1), 0.2s late, so a `/health` that answers at once never flashes it. Patch idles (§8.3). With reduced motion nothing moves (scene `b69_12_loading_screen`).
- At 400px the card fills the width less 1rem each side; nothing scrolls sideways.
- *Checked* by the browser check B69.7 to B69.12 (late, hung past the timeout and failing `/health`; recovers by itself and with Retry; Retry by keyboard; 400px and 1400px, light and dark; Ctrl+K the moment the shell appears after a late `/health`) and the unit tests B69.1 to B69.6 (the timeout and backoff, on a fake clock).

### 5.15 The page for one CVE (B35, 2026-10-18)

Everything Patch knows about one CVE, on its own page: `/cves/CVE-2025-3248` (`frontend/src/pages/CvePage.tsx`, `styles/cvePage.css`; the data from `GET /cves/{id}`). A page, not a side panel (the owner's choice, #85): a link can be shared, Back works, and alerts and the chat link straight to it. Why: DECISIONS.md, 2026-10-18.

- **Where it opens from**: the CVE id in the CVEs list (§5.9) and the dashboard's Top 5, an alert (§5.11, §6.4) and the run history's new CVEs (§5.12), and any CVE id in Patch's answers and tool cards (§6.2). All in the app (`CveLink`); a modified click opens a new tab as usual. The list's id used to open NVD; the page links to it.
- **Top bar**: "Pages / CVEs", the CVE id as the title (with the blinking cursor, §7.1); the sidebar shows CVEs active.
- **Back link** above the cards: "← CVEs on your watchlist" (bold, `--text`, underlined: it sits on the page background, where `--accent` is 4.2:1 in light mode). Opened from the list it steps back in history, so the list comes back in place; opened from elsewhere it opens `/cves`.
- **Head card** (full width): the id (`h2`) with its chips (KEV, New, Possible match, and "Not on your watchlist": `--text` on `--surface` with a `--border` edge); one line with the product (bold), the severity badge and "Published …"; the **full summary** (`--text`, at most 70 characters a line, long words wrap); links **NVD** and **OSV.dev** (new tab).
- **Then a grid of cards**, two columns over 900px, one at 900px and under or with the chat pinned. Each card's facts are label and value pairs (label 0.78rem muted uppercase; at 520px and under the label sits above its value):
  - **Your assessment**: Status (with "Review due" and the current decision, as in the list), Verdict (chip and its facts), and only for an open CVE **Priority** (chip and reasons) and **Due** (the list's due facts, "No fix yet" and the KEV deadline as its own fact when it's another date, B36; "by your policy:" shown). Then the **actions** as pills in a row that wraps: "Mark not affected?" (the suggestion, `--ok` edge), the status actions (Mark fixed, Not affected, Accept risk, Accept again, Reopen, by status as in §5.9) and **Ask Patch**. Each status action opens the decision dialog (§5.9). Off the watchlist: one line saying there's no status, priority or due date, the verdict, Ask Patch and "Watch {product} in Settings →".
  - **Facts**: Severity, EPSS (score · percentile, "EPSS by FIRST, date"), CISA KEV (date listed, the KEV deadline "CISA's date, not your due date", required action, ransomware use), OWASP (the category as a link, then its list: "OWASP Top 10 2025 (web applications)" or "… for LLM Applications 2025"), CWE.
  - **Product and versions**: the product, how you run it (usage, version, internet-facing), and per OSV package a nested-fill box (radius 18px): package (ecosystem), the affected ranges in words ("every version before 1.3.0", "from 0.4.0 up to 0.12.5 (no fix listed)"), and its advisory linked on OSV.dev.
  - **Decision history** (watched only): the records, oldest first, open (not behind "History (n)"): time in UTC, status, facts, who and where. "No decisions yet." when empty.
- **Priority and due date** show for open CVEs only (open, or accepted with its review due; GLOSSARY.md). One function decides it (`cvePage.ts` `showsPriority`): B33 (#83) brings the shared rule.
- **No such CVE**: an unknown or malformed id shows one card "No such CVE": "{id} isn't in Patch's data. Check the id, or find the CVE in the list." and "Back to the CVEs list". The id is shown as text, cut to 40 characters.
- **Patch knows it**: the page context is `{page: "cves", cve: "CVE-…"}`; the chat header's chip says "on CVEs · CVE-…".
- **Motion**: the cards fade up once (§7.1; the head and assessment at 0s, the others 0.12s). The decision dialog doesn't move. With reduced motion nothing moves (scene `b35_17_cve_page`).
- At 400px nothing scrolls sideways; long ids, URLs and words wrap.
- *Checked* by the browser check B35.10 to B35.17 (from the list, the Top 5, an alert's link, an answer and a tool card; Back in place by the browser and by the back link; the actions; unknown and malformed ids; light and dark, 400px and 1400px, the pinned chat, chip and text contrast at least 4.5:1, keyboard) and the unit tests B35.4 to B35.9 (paths, old alert links, the page context, range words, priority only while open, ids in answers).

### 5.16 The landing page (B42, #80, 2026-10-19)

What Patch is, for a visitor who isn't signed in: the deployed app's front door. Before B42 a signed-out visitor saw only the sign-in form and learnt nothing about Patch. Why the choices: DECISIONS.md, 2026-10-19 (B42). Code: `frontend/src/landing/Landing.tsx`, `styles/landing.css`; which screen shows where: `auth/signInView.ts` `frontDoor`.

- **Where it shows.** With sign-in on, signed out: at **every address** but the sign-in form's (`/`, `/cves`, `/nope`: an unknown address too, #96); the address stays as typed. Signed in, or with sign-in off: **About** (`/about`) in the app shell, from the sidebar (§4.1); the app still opens on the dashboard. Signed in but not approved (B46): `/about` from the access card's "What is Patch?" (§5.13), in the front-door frame; its next step **Back to your request** (to `/`, the card), the end card "That's Patch." and "The owner decides who gets in.", no "New here?" line.
- **Drawn once** (#100): the landing page stays one element while Clerk's code loads, so its sections fade up once (`main.tsx` draws it, outside Clerk's chunk; *checked* by B100.4).
- **No API call and no live data.** Fixed text and fixed example screenshots only. The page needs nothing but `/health` (which says sign-in is on), so it shows nobody's watchlist and works before sign-in (*checked* by B42.6).
- **A browser that was signed in last time, or was on the sign-in form** (`signedInHere`, §11) sees "Opening Patch" (the §5.13 frame) while Clerk loads, not the landing page flashing before the app. The sign-in form counts (B51) because Clerk's redirect after signing in loads `/` before Clerk answers (*checked* with Clerk unreachable by B51.3; the real redirect is unverified, #65). If Clerk can't load, the landing page. The key only picks the waiting screen; it lets nobody in.
- **Front door frame**: the page background (§3.3); a slim top bar, max 1120px: the brand (§4.1, no dashed line) on the left, the light/dark switch (36px round, §9) on the right. Then the page, one column, max 1120px, 2.4rem between sections. In the app: the same sections in the main column under the top bar ("Pages / About", title "About").
- **Sections, top to bottom:**
  1. **Hero** (the welcome banner's look, §5.8: radius 28px, white to `--accent-soft`, `--shadow-banner`). Left: a chip "For teams who run LLM software" (`--text` on `--accent-soft`); the heading **"Security flaws in your LLM stack, tracked for you"** (`h1` at the front door, `h2` in the app; Fredoka 700, 1.8–2.6rem by width, `--accent`); **the problem** first, one paragraph in `--muted` (new CVEs every week, reading NVD, KEV and advisories again and again); then **what Patch is** in one paragraph in `--text`; then **the next step**: **Sign in** (primary) and **Request access** (plain pill), both links styled as §5.3 pills (`.pill-link`), and "New here? Request access: make an account, then the owner lets you in." (0.85rem muted). In the app the one button is **Open the dashboard**. Right: **Patch**, 150px, idle in a variant picked on load, his head over the card's top edge (−4.2rem), and under him an **example alert** drawn as a phone notification (surface card, 1px border, 3px `--error` left edge, radius 18px, tilted −2°): "Patch · now", "Added to CISA KEV: CVE-2025-3248", "Your Langflow 1.2.0 is affected. Urgent." (screen readers hear "An example alert on your phone: …"). At ≤ 800px one column, Patch first; at ≤ 520px the example alert hides, so the heading follows Patch.
  2. **Four candy tiles** ("What Patch does", a hidden `h2`): **Watch**, **Judge**, **Alert**, **Ask**, each a name (1.5rem Fredoka) and one line (700, 92% white), with the dashboard tiles' gradients, shadows and contrast (§5.1) and one 16%-white circle. Not links. 4 columns, 2 at ≤ 900px, 1 at ≤ 520px.
  3. **"Patch in 20 seconds"** (B47, #99): the launch video in the screenshots' frame (the same card and three dots), full width of the column, 16:9. A light and a dark file with a poster each, picked by `data-theme` like the screenshots; the switch swaps the file (and starts it over). Native controls, a captions track (no speech: it says what the sound is), **no autoplay**, `preload="none"` (nothing downloads until play), `width`/`height` set. Under it a closed `<details>`, "The video as text" (summary 700 `--text`, 0.9rem), with the six lines as a numbered list; the video's `aria-describedby` points at that list, and its name says it has music.
  4. **"See it working"**: three screenshots, the **dashboard**, the **CVEs page** and **Patch answering** "Am I affected by CVE-2025-3248?" with its source open. Each a `<figure>`: the image in a frame (surface card, radius 26px, `--shadow-card`, a strip with three `--border` dots like a browser window) and a caption (`h3` in `--accent`, 1.25rem bold: large text, so the page background's 4.2:1 passes, B49; one line in `--text`). Over 900px the picture takes 1.7 parts and the caption 1, sides alternating; at ≤ 900px the caption under the picture. Under them: "Screenshots from Patch with example data: …" (0.82rem muted), so nobody reads them as a real team's data or a real model's words.
  5. **The end card** (a §5.2 card, centred): Patch, 96px, **happy** in a variant picked on load, his head over the top edge; "Ready to look at your own stack?" and Sign in / Request access again (in the app: "That's Patch." and Open the dashboard).
  6. **Footer**: the data sources and "A Turing College project", a link to the source on GitHub (new tab; `--text`, underlined, as §5.15's back link, B49), 0.82rem muted, centred.
- **The screenshots follow the theme**: light and dark versions of each; the page shows the pair matching `data-theme` (the system setting first, then the switch, §9), and swaps them when the switch is pressed. WebP, 1280 × 800, 50–90 KB each, `width`/`height` set (no layout jump), `loading="lazy"`, each with an `alt` that says what it shows.
- **Taken by a script**, so they can be taken again after the polish tickets (#93 to #96): `scripts/landing-shots.sh` runs `frontend/e2e/landing_shots.py` on `run.sh`'s throwaway servers (Chromium, 1280 × 800, reduced motion, the welcome banner closed, the example watchlist with Langflow 1.2.0 and LiteLLM 1.80.0 set) and writes `frontend/src/landing/shots/{dashboard,cves,chat}-{light,dark}.webp`. Look at the six, then commit them.
- **Link preview** (B61, #108): a link to `/` or `/about` in a chat app shows a card: the title "Patch, the LLM-security assistant", a two-sentence text from the hero, and a 1200 × 630 PNG: the launch video's last screen (B47, light cut; the owner's choice), redrawn for 1.91:1 rather than cropped, so it stays sharp and Patch stays inside the frame. The app icon and **Patch.** in dark Fredoka (`--text`), "Watch. Judge. Alert. Ask." in `--accent`, the repo address in `--muted`, Patch happy in the bottom right, on `--bg` with the page glows. Light, because cards show on light and dark chat backgrounds alike; big type, because a card is often a few hundred pixels wide. Made by `scripts/link-preview-image.sh` (`frontend/e2e/link_preview_image.py`: About's own tokens, fonts, icon and end-card robot, drawn over the page and screenshotted) into `frontend/public/link-preview/patch.png`. The server adds the tags (DECISIONS.md B61).
- **Keyboard**: the theme switch, Sign in, Request access, the end card's two, then the footer link, in reading order; the focus ring as everywhere (§10). Sign in and Request access are real links (`/sign-in`, `/sign-in#/create`): a plain click opens the sign-in screen in place (a new history entry, so Back returns to the landing page), a modified click a new tab.
- **Motion**: each section fades up once (0.45s, the cards' curve; delays 0, 0.12s, then 0.24s for the rest); a screenshot frame lifts 4px with a deeper shadow on hover (0.2s); Patch idles (hero) or is happy (end card) (§8.3). The video moves only when the visitor plays it. With reduced motion nothing moves (scene `b42_12_landing_page`).
- At 390px and 1440px nothing scrolls sideways (*checked* by B42.9, B42.11).
- *Checked* by the browser check B42.6 to B42.12 (any address, no API call, Sign in and Request access by mouse and keyboard and Back, the screenshots by theme and switch, their size and loading, 390px and 1440px in light and dark, Patch over the hero's edge, text contrast at least 4.5:1 on both ends of the hero's gradient, the waiting screen and Clerk failing, About in the app with sign-in off, the tab bar at 390px, reduced motion) and the unit tests B42.1 to B42.4 (`/about`; which screen at which address; the wait). The video: *checked* by B47.1 to B47.3 (after the tiles, front door and About, no autoplay, nothing downloaded before play, its text version, light and dark files and posters by theme and switch, served with the right type, under 3 MB and 150 KB, 390px and 1440px). *Unverified*: the video playing (Playwright's Chromium has no H.264 decoder; the owner played the dark cut with sound before it was added, 2026-10-19). *Unverified*: the front door against a real Clerk instance (the browser check has none: #65), and how long "Opening Patch" shows there.

### 5.17 Latest AI incidents (MITRE ATLAS) (dashboard; described in B43, 2026-10-19)

- The dashboard's **last** side card, after Recent alerts and Data freshness (it was the second, above them, until B43). Why last: it's background to read, while the cards above it are what you act on (alerts to check, a check to run).
- Title "Latest AI incidents (MITRE ATLAS)". Then one intro line (`.meta`, 0.85rem, `--muted`): "Real attacks on AI systems, as MITRE ATLAS writes them up, newest first. Nothing to act on: they show how the kinds of flaws in your CVEs get used."
- Then the 5 newest ATLAS case studies of type incident (`backend/app/dashboard.py`, from the snapshot): the name as a bold link to ATLAS (new tab, wraps), under it "2026-02-23 · AML.CS0056" (muted, 0.78rem). The same list for every product filter: incidents aren't tied to a product.
- Fades up with the side cards (0.12s, §7.1); nothing else moves. *Checked* by A05.6 (5 items, links, newest first) and B43.11 (the intro, last in the side column), B43.13 (the intro's contrast at least 4.5:1, light and dark, 390px and 1440px).

### 5.18 Tooltips by mouse, keyboard and touch (B44, 2026-10-19)

A native `title` shows on mouse hover only: a keyboard or a phone never sees it. Words that explain something use one component instead (`frontend/src/components/Tip.tsx`, `tips.ts`, `styles/tip.css`).

- **Anchor**: a `<button>` with the button look taken off, so it reads as the words around it: a Tab stop that a tap and a screen reader know. Its tip is its description (`aria-describedby`). A dotted underline (an `<abbr>`'s look) says there's an explanation; only words with one get it. A chip anchor (Possible match) keeps the chip's look, with no underline. The global focus ring shows by keyboard.
- **Opens**: mouse hover (with a 150ms grace, so the pointer can cross onto the bubble); keyboard focus (`:focus-visible` only, so a mouse click doesn't leave it stuck open); a tap (a second tap or a tap elsewhere closes it). **Esc** closes it wherever the focus is, before anything behind it (the chat, a dialog). One tip at a time.
- **Bubble**: the charts' tooltip (§5.4): `--text` fill, `--surface` text, 4px radius, 0.78rem; it wraps at 18rem, since these tips are sentences. Centred above the anchor, 8px clear; below it when there's no room above (a heading at the window's top); never closer than 8px to the window's side. Drawn in `<body>` at a fixed place, so the table's sideways-scroll box never clips it. No motion: nothing for reduced motion to stop.
- **Where**: the CVE list's headings Priority, Due, OWASP, EPSS and Verdict (CVE, Product, Severity, Published and Status say what they are: no tip, no underline); each row's OWASP code ("A05:2025 Injection, from the OWASP Top 10 2025 (web applications)"); the Possible match chip everywhere it shows (list, CVE page, Top 5, Patch's cards); EPSS on the CVE page. Since B49 also the **KEV** chip ("In CISA KEV: known to be exploited"; on the CVE page and the Top 5 with its KEV deadline), the **New** chip and the **Selected** chip ("Patch knows this is the CVE you asked about"), as chip anchors: no mouse-only `title` is left on a chip (*checked* by B49.15). The chips in Patch's cards say what they are and have none.
- *Checked* by B44.6 to B44.8 (mouse, keyboard with Esc, touch with a second tap and a tap elsewhere; inside the window; tip and chip text at least 4.5:1; light and dark, 390px and 1440px, Firefox and Chromium) and the unit tests B44.2 and B44.3 (the bubble's place, the OWASP words).

### 5.19 Page not found (B49, #96, 2026-10-19)

An address the app has no page for (`/nope`, `/cves/CVE-2025-3248/more`), signed in or with sign-in off. It used to show the dashboard under the bad address, so a mistyped or old link looked like it worked. Signed out with sign-in on, the landing page shows instead (§5.16). Why: DECISIONS.md, B49.

- **Where**: `frontend/src/pages/NotFoundPage.tsx`, `styles/notFound.css`; which addresses: `route.ts` `locate`.
- **Top bar**: "Pages / Page not found", the title "Page not found" (with the cursor, §7.1). No sidebar item is active. The chat's chip says "on Page not found"; Patch is told no page.
- **The card**: the welcome banner's look (§5.8): white to `--accent-soft`, radius 28px, `--shadow-banner`; **Patch**, 110px, idle in the variant picked on load, his head over the top edge (−2.4rem); "Patch has no page here" (`h2`, 1.25rem Fredoka 600, `--accent`); "Nothing lives at `/nope`. The link may be old, or mistyped." (`--text`; the address as typed, cut to 60 characters, wraps); **Open the dashboard** (a primary pill link, §5.16 `.pill-link`): a new history entry, so Back returns to the bad address.
- **Phone (≤ 640px)**: as the banner, Patch at 64px beside the title, the line and the link under both, left-aligned.
- **Motion**: the card fades up once (§7.1); Patch idles (§8.3). With reduced motion nothing moves (scene `b49_14_page_not_found`).
- *Checked* by B49.14 (390px and 1440px, light and dark, the address kept, Patch over the edge, text contrast by B49.20's measure, no sideways scroll, the link by mouse and keyboard and Back) and the unit tests B49.6.

### Checklist: components

- [ ] Page not found (B49, §5.19): any address without a page, signed in or sign-in off; the address kept; Patch over the card's edge; Open the dashboard by mouse and keyboard, Back returns; 390px and 1440px, light and dark; the fade up, nothing moves with reduced motion.
- [ ] Landing page (B42, §5.16): signed out at any address but `/sign-in`, no API call but `/health`; the problem first, one line on Patch, the three screenshots in the visitor's theme, Sign in and Request access (Back returns); About in the app (sidebar and tab bar) with sign-in off and signed in; Patch over the hero's edge; 390px and 1440px, light and dark, no sideways scroll, text at 4.5:1; keyboard; the sections' fade up, nothing moves with reduced motion; the screenshots re-taken by `scripts/landing-shots.sh` after a page changes.
- [ ] Dashboard polish (B43, #93): the Watchlist filter above the tiles on a phone and at the top of the side column over 1000px, Tab order banner → filter → tiles; Data freshness folds its sources ("Sources and licences (7)", Enter opens it) and links "See the N new CVEs →" while anything is new; the OWASP chart says it's the web Top 10, codes on the axis and full names in the tooltip, each CVE under every category; "your watchlist" (not "your LLM stack") in the banner and the chat greeting; Patch's button never covers a chart's totals or the end of a page (§6.1); a 64px Patch in the banner on a phone; the ATLAS incidents last, with their intro (§5.17); a gap before "No fix yet" in the Top 5; light and dark, 390px and 1440px; nothing moves with reduced motion (scene `b43_14_dashboard_polish`).

- [ ] The page for one CVE (B35, §5.15): the full summary, product and versions, facts, assessment and actions, history, NVD and OSV links; opened from the list, the Top 5, an alert, the chat; Back returns to the list in place; "No such CVE" for an unknown id; light and dark, 400px and 1400px, pinned chat, keyboard, the cards' fade up, nothing moves with reduced motion.

- [ ] Settings layout (§5.7): Watchlist across the top, two packed columns per part (since B48 and B50: Yours left Profile, Connected accounts, Alerts; right Patch's answers, Priority and due dates; Start over across both; This Patch right Requests, Refresh runs; left Delivery, Data) with no holes; Tab follows that order; one column in the same order at ≤ 900px, no sideways scroll at 400px.
- [ ] Settings in two parts (B48, §5.7): "Yours" for everyone, "This Patch" for the owner only, each heading at 4.5:1 on the page background; Requests at the top of "This Patch"'s right column at 1440px and first on a phone, the `#requests` link lands on it; the columns end near each other with 20 runs and 20 alerts; anyone else sees only "Yours", the in-Patch note (3px edge, 4.5:1) and the schedule line, no channels or quiet hours; the Profile card saves with the bar, a name over 60 characters is refused in the page, Remove my name by keyboard; 390px and 1440px, light and dark; nothing moves with reduced motion (scene `b48_34_settings_in_two_parts`).
- [ ] Settings and Dev polish (B50, #95): no "Live" chip on their cards; on a phone the save bar shows only with something to say and never covers Patch; "Yours" ends with Start over (its 2px `--error` edge, what it deletes and keeps for this role, Reset all my data); Delivery shows 3 alerts and links to the dashboard's card; the Data card names six sources; Pause disabled in snapshot mode with the reason; no server names in the words; anyone but the owner: no channel, no test send, the in-Patch note, "In Patch only", their own empty-card words; Dev: one name, the owner's intro by role, "Model-check report", map labels apart and inside; 390px and 1440px, light and dark, 4.5:1; nothing moves with reduced motion (scene `b50_10_start_over_and_the_phone_save_bar`).
- [ ] Telegram (B57, §5.7): the owner's fourth channel row (tick, pill hugging its text, Send test) and its folded block with the four steps, Bot token (write-only), Chat id and Find my chat id; the found line with its edge (ok, warn, error); 390px and 1440px, light and dark, 4.5:1, no sideways scroll; by keyboard; hidden for anyone else; the token never on the page; nothing moves with reduced motion (scene `b57_18_telegram_setup`).
- [ ] Delivery's setup blocks (§5.7): folded by default, each summary naming the block and its state; channel rows stay visible; Enter and Space open and fold, focus visible; ticking a channel that isn't set up opens its block; a failed save opens its block and focuses the field; edits survive folding; nothing animates; light and dark, 400px and 1400px.

- [ ] Loading screen (#69): shows at once, before `/health` answers, with Patch idling over the card's edge and a status line; offline after 15 s with the countdown and Retry (by keyboard, focus kept); recovers by itself; an outright failure is the offline screen too, never the app (B46); light and dark, 400px and 1400px, nothing moves with reduced motion; Ctrl+K works the moment the app appears.

- [ ] Access (B38): a signed-in person who isn't approved sees only the access card (ask with the note and its counter, waiting with Check again, refused), never the shell; Send by keyboard; the focus on the new heading; Sign out; 390px and 1440px, light and dark; nothing moves with reduced motion. The owner's Requests card: owner only, the note as plain text, status as a word with an edge, every button by keyboard and named with the person; the alert link lands on it. Connected accounts: never unlinks the last way to sign in.

- [ ] Sign-in (B10): signed out, only the sign-in screen (Patch over the card's edge, brand, heading, invite line, Clerk's form in our tokens), loading and failed states, the theme switch; at 400px nothing scrolls sideways; signed in, the user menu with name, email and Sign out, Esc and outside click close it; nothing of Clerk's with sign-in off.

- [ ] Refresh runs (B19): schedule and Pause in one fieldset, saved with the bar; the schedule line from the server; Check now above the runs in live mode (B59), the dashboard's button and line, the list loading again after a run or a refusal; the last 20 runs newest first, the result in words with its edge, trigger, UTC time and duration, counts; each opens by keyboard to each feed's step; skips count up; fits at 400px. The dashboard says "Schedule paused" with Resume.

- [ ] Recent alerts (B04): the last 20, reason and time in UTC, per-channel results in words, one alert links to `#cve=…`, a digest says counts only; a mixed digest counts the reminders as one (B34); a retried send says its tries (B41).
- [ ] Alert counts (B34): the dashboard's line and each refresh run say sent, recorded only (not sent), failed and held in words, zeros left out; "sent" never for a dry run; a failed alert turns the line `--warn`.
- [ ] Tiles: gradients, circles, contrast as in the table; KEV tile wiggles only when KEV > 0.
- [ ] Every chart has a legend (2+ series), hover tooltips, "Show as table", and the grow-in animation; stacked bars grow as one piece.
- [ ] Map colours and dimming as specified, in both modes.
- [ ] Buttons, inputs, checkboxes, radios and sliders are on-brand in both modes and in Firefox and Chrome.
- [ ] Save bar never hidden behind Patch.
- [ ] Patch's colours are the fixed ones in §8.1 (body `#9483FF`, visor `#2A2457`, eyes `#7FF0DD`, light `#FFC94D`, cheeks, extras), the same in both modes; no token changes them.
- [ ] Welcome banner closes and stays closed; Settings' "Show Patch's welcome on the dashboard" shows the current value, brings it back without a reload, stays out of the save bar, and works with storage blocked (for the session).
- [ ] Tiles link to the CVEs page with their filter; the count there matches the tile.
- [ ] Dashboard product filter (A15b): toggle pills with `aria-pressed`, a tick as well as colour, in the URL only, carried by the tile links and "See all CVEs"; the watchlist is edited on Settings, in a card that shares the save bar.
- [ ] CVEs page: full width; filters in the URL survive a reload; stacked cards when narrow; row actions always in view.
- [ ] Tooltips (B44, §5.18): every dotted-underlined word has a tip by mouse, keyboard (focus, Esc closes) and touch (tap, tap again or elsewhere closes); headings with nothing to explain have no underline; the bubble stays inside the window, at least 4.5:1, light and dark, 390px and 1440px; one at a time; no motion.
- [ ] Phone filters (B44, §5.9): on a phone (≤ 800px) the filters fold behind "Filters (n on)" (n counts the filters the URL carries), the count line stays in view; Enter or Space opens it, the controls follow in Tab order; a desktop shows the filters as before; at least 24px high, 4.5:1, light and dark, no sideways scroll at 390px.
- [ ] Short CVE rows (B36): one main action and More per row; More opens in place by Enter or Space, its summary at least 4.5:1; each date once in the Due cell; at least twice the rows of before at 1440×900 (12+ per 900px); one phone card fits 390×844 above the tab bar; light and dark; nothing moves with reduced motion.
- [ ] Dev page layout (§5.6.3, B39): over 900px Model and Index on the left with Index one gap under Model, Agent and search on the right; DOM and Tab order Model, Agent and search, Index; one column in that order at ≤ 900px, no sideways scroll at 400px; light and dark, owner and read-only.
- [ ] Dev page for a Trusted person (B29, B45): the owner's choices as a read-only list with the note line; the playground runs; no save bar, Reset, Find models or check buttons, each check's card says why; text 4.5:1; fits at 400px. A Viewer: no Dev item, `/dev` is one line.
- [ ] Roles (B45, §5.6.4, §5.7): the Requests card's role select per waiting and approved person with its hint, Approve gives the pick, Save role only when changed, the status line; the reviewer's note with its `--accent` edge and Back to the owner's settings (only with a copy, by keyboard); 390px and 1440px, light and dark, 4.5:1; nothing moves with reduced motion.
- [ ] Dev page OpenRouter model (A11.10): a native select with price, score and "(default)" per option; the picked model in full under it; "Other…" opens a focused text field; a saved id not listed shows as Other, unchanged; a loading state; no list = the text field and the reason; never wider than its card at 400px.
- [ ] Data freshness (B02): Live or Snapshot chip; the last-checked line in UTC; Check now only in live mode, "Checking…" with the spinner while it runs (readable, `aria-busy`); one result line in a status region with its edge colour; the NVD notice and attributions in both modes.
- [ ] Partial or failed banner (B20): what updated, what didn't, the next try in UTC; each failed feed's reason; Retry by mouse and keyboard; edge colour by tone; fits at 400px; survives a reload.
- [ ] Closed CVEs (B33): fixed, not affected and accepted (before its review) show "—" for priority and due date, never "Overdue"; the KEV deadline stays; reopening brings the chip and date back; the dash is 4.5:1 in light and dark, and fits at 400px.
- [ ] Decision dialog (A16b): named fields, focus trapped, Esc closes, focus back on the opener, server errors inside it, fits at 400px, nothing moves with reduced motion; the justification picker has all five; accepted rows show reason, review date and control; review due shows its chip; the history opens by keyboard; "No fix yet · open N days" replaces "Overdue" (CVEs page, Top 5, Patch's card).

---

## 6. The chat

![Chat bubble with an answer](img/chat-bubble.png)

### 6.1 Patch's button (closed chat)

- Bottom right of the page area, 1.25rem from the right and bottom. 84 × 66px.
- A **pill** (30px tall, full width, surface fill, 1px border, purple shadow) with **Patch (68px) standing in front of it**, overlapping its top edge, his shadow on the pill. His top is 8px above the button, as it was at 58px, so he covers no more of the page; the extra size goes down onto the pill (changed 2026-10-16: 58px looked a bit small). Patch is in front (z 3), the pill behind (z 2), the unread dot on top (z 4).
- Hover or keyboard focus: the pill's border turns purple.
- Accessible name "Ask Patch". Shows Patch's current mood; **happy when an answer is unread**, with a red unread dot.
- **The space the button takes is kept clear (B43, 2026-10-19)**: it floats over the page, so on a phone it covered the Langflow bar's total on the dashboard and the last row's "More" on the CVEs page. One fix, not one per element: its footprint is a set of values in `styles/shell.css` (`--fab-right`, `--fab-bottom`, `--fab-width`, `--fab-height`, `--fab-reach` for Patch's head 8px above the button) that the button itself and the pages read.
  - **The end of every page**: the main column's bottom padding is `--fab-clearance`, so scrolled to the end, a page's last card or row sits 0.5rem above Patch's head (on a phone this also covers the tab bar's 4.4rem). Every page gets it, so a new page can't forget it.
  - **The end of the charts**: at ≤ 1000px (one column) the dashboard's charts keep `--fab-side` free on their right (the button's width and offset, less the page's and card's padding: about 68px at 390px). That's where the bars' totals sit, so no total is ever under the button, at any scroll. Over 1000px the side column is under it, not the charts.
  - The save bar's 96px (§5.7) and the pager's (§5.9) stay as they were. *Checked* by B43.9 (390px and 900px: every chart value label left of the button; 390px and 1440px: nothing on the dashboard, the CVEs list or a one-product list under the button when scrolled to the end).

### 6.2 Bubble window (open chat)

- Opens above the button: 1.25rem from the right, 3.6rem from the bottom (just above the pill). 400 × 600px max (shrinks to the space). Radius 26px.
- Opens with a **pop** (section 7).
- While it's open, **Patch steps off the button**: the button is just the pill, purple, with a white ✕ ("Close the chat"). Its box shrinks to the pill too, 84 × 30px (B65, #112, 2026-10-20). Why: the 66px box kept its empty top, which lay over the window's bottom-right corner (the button is z 21, the window z 20). Send sits there, so a click on Send's lower half closed the chat; Enter worked. *Checked* by B65.1 (a click at Send's top, middle and bottom lands on Send: 390, 750 and 1400px, bubble and enlarged) and B65.2 (a click on Send's lower edge sends and the chat stays open; Enter still sends).
- **Only the message list scrolls (B65, #112, 2026-10-20).** The window is `overflow: clip`, and the list is positioned. Why: the list's absolute children (the `.visually-hidden` spans) overflowed the window, not the list, so the window had something to scroll. `scrollIntoView` scrolls every scrollable ancestor, and `overflow: hidden` still allows that. So in Firefox, "Show N sources" moved the whole window up: the header left the frame and an empty band opened under the message box, over Send's lower half. *Checked* by B65.3 (390, 750 and 1400px: before and after opening the details, the window has nothing to scroll, its header is at its top, the message box at its bottom, and a click anywhere on Send lands on Send).
- **Header**: Patch (34px, showing the mood), "Patch", a chip "on Dashboard" (the page underneath), New chat, **Make larger**, ✕.
- **Page chip (A18)**: shows the whole page context Patch gets, joined by " · ": "on CVEs · Langflow · High or worse · Unknown · CVE-2025-3248" (product, severity "or worse", a status other than open, verdict, "In KEV", "Since …", the selected CVE). `--text` on `--accent-soft` (`--accent` text is 4.48:1 in light mode); it wraps instead of cutting off. Its title repeats it in a sentence. Nothing in it moves.
- **Selected CVE (A18)**: "Ask about this" on the CVEs page selects that row for this visit: an `--accent` edge on the first cell and a "Selected" chip (`--text` on `--accent-soft`, `--accent` edge) next to the id. Leaving the page clears it.
- **Fix-first card (A18)**: `prioritise`'s tool card. Title "N open · {view} · in the rules' order", then a numbered list in the rules' order (never re-sorted): id, priority chip, severity, KEV, "Review due", "No fix yet · open N days" or the overdue mark; under it the product, the reasons and "due" (or "decide by") date. A status filter that doesn't apply is listed as "Not applied: …".
- **Web research (B08)**: `research_web`'s tool card. Title "Web search: “{query}”" (exactly what was sent); then "N results · via Tavily's MCP server" (or "Tavily's search API (the MCP server didn't answer)"), "· N flagged", "· N searches left today"; then a list: the source number, the title as a link (new tab), and the web facts. The header keeps the tool name, status and time in ms, like every tool card.
- **What's new (B06)**: `check_updates`' tool card. Title "Checked the feeds · 2026-10-15 09:00 UTC" when this call ran a check, "Last check · …" when it was refused (then the refusal line, "Checked less than 5 minutes ago. The next check is allowed at 09:05 UTC.", in `--muted`), "Not checked yet" before any check, and "A frozen snapshot, as of 2026-10-13: nothing to check" in snapshot mode. Then "N new · N updated · N added to KEV · N rescored · N alerts for you"; a failed check says so in the tool-error red, and a partial one (B20) says "Partial: {feed: error}. The rest was written." in `--muted`. Two short lists, at most 10 rows each, headed "New CVEs" and "Alerts for you" ("(first 10 of 278)" when cut): the source number, the id in bold, then chips (product, severity, KEV, the priority chip, nothing for a closed watched CVE (B33), or "Not watched"; for an alert, its reason: "Added to CISA KEV", "New", "Now critical", "Due soon", "Overdue"…, and "held for quiet hours"). The rows wrap at 400px. With new CVEs, a link "See the new CVEs on the CVEs page" (`/cves?new=1`, B05's filter) opens the page in the app. After a check that ran, the dashboard loads again, as after Check now. Nothing moves. Source numbers (here and in the Sources tab) are `--text` on `--accent-soft`: `--accent` on it is 4.48:1 in light mode.
- **Web facts (B08)**, on the card's results and on each web source in the Sources tab: a chip "Web result, unverified" (`--text` on `--surface` with a `--muted` edge: apart from knowledge sources, not a warning), "Flagged: instructions ignored" when the page's text tries to give instructions (`--text` on `--warn-soft` with a `--warn` edge, like "Possible match"), and the site and date ("no date given" when Tavily gives none). A flagged page is shown, never hidden: its snippet stays as data. Under the answer, the flag note (warn): "A web result tries to give instructions. It's shown as data, and Patch ignored it." Nothing in either moves. Long URLs and titles wrap; nothing is wider than the chat at 400px.
- **Dropped page context (A18)**: under an answer, "Page context not used (not a valid value): severity=EXTREME" in `--text` on `--warn-soft` with a `--warn` edge. The app never sends such values; it shows when a request was crafted.
- **Explain-level switch** (A19), a row under the header's buttons: "Explain level" and three pills (radios: Simple, Normal, Deep dive) showing the saved level. Picked pill: `--text` on `--accent-soft` with an `--accent` edge. Another level applies to the next question only ("next question only" note, muted italic), then the switch goes back to the saved level. Each answer shows the level it used as a small chip (`--muted` on `--accent-soft`) before the usage line.
- **Empty chat**: Patch (58px, in front, as on the chat button; idle in a variant picked on page load, §8.3) on the top-left corner of a soft purple speech bubble, in front of it, with only the first line of text beside him: "Hi, I'm Patch! I know the OWASP LLM Top 10, MITRE ATLAS and the CVEs on your watchlist. What shall we look at?" Below: 1–2 suggested questions for the current page, and "More examples" (folded).
- **Messages**: user on the right in `--user`, assistant on the left on the surface. Each answer can open "Show N sources · N tool calls" ("1 source · 1 tool call": one helper says every count, `plural.ts`, B49): tabs (Sources, Tool calls, Query plan) inline under the answer. Citations `[1]` open those details and scroll to the source.
- **A step that didn't finish (B20, 2026-10-15)**: its tool card keeps the `--error` edge; the status says "Didn't finish" (not "Error") and the error line "didn't finish: search_security timed out before it answered." Below it **Try again**, a plain pill (2rem; "Trying again…" with the Check now spinner, readable, `aria-busy`) and "Runs this step only." (muted). Done: the status says "OK on retry", the card turns to the `--ok` edge, and a note in `--text` on `--accent-soft` with a 3px `--ok` edge says the answer above was written without it. A step that can't pass on a retry (a bad argument, an unknown id, the web research limit) says "Error" and has no Try again. The answer text keeps what worked and names the missing step. A failed send puts the message back in the box. *Checked* by the browser check B20.12, B20.13 (light and dark, 400px and 1400px, keyboard, contrast) and the scene `b20_14_partial_and_try_again`.
- **A limit or the spending cap (B11, 2026-10-16)**: a chat limit (429) or the model's spending cap (402) is not a fault, so it gets no red bubble. Instead one quiet line at the end of the conversation, right-aligned: the server's sentence in `--muted`, 0.85rem, no fill, no edge, wrapping ("You've sent 10 messages in the last minute, the most allowed. Try again at 09:01 UTC."). It is an `<output>` (role status), so a screen reader says it politely, not as an alert. Patch stays idle (no shake), the question goes back in the box (B20), and nothing moves. Since B49 the refused question is **only** in the box (no sent bubble as well), and the note shows once: refused again, it is replaced; the next question takes it away. *Checked* by the browser check B11.6 and B49.11 (light and dark, 390/400px and 1400/1440px, 4.5:1 contrast).
- **Under each answer** (A08): the citation check's note, quiet (`--muted`, italic, no fill; unlike the warning-coloured flag note): "No sources cited." when a sourced answer cites none, "Removed citation [9]: no matching source." when the check took one out. Then the usage line: tokens in and out, LLM calls, steps, and the cost in dollars to two significant figures ("$0.00061"; "$0" for local models and FakeLLM). **Only for the owner and Reviewers** (B49, #96 C1: the people who change models; with sign-in off, the one user is the owner). Viewers and Trusted people see the explain-level chip alone. *Checked* by B49.8.
- **Kept for the tab's life (B49, #96 C5)**: the conversation is in sessionStorage (§11), so a reload keeps it and closing the tab clears it. Per user: another signed-in user in the tab never sees it, and signing out clears it. With storage blocked the chat works and forgets on reload. The latest 40 messages; a refusal note isn't kept. A kept answer's proposal card asks the server once for its state (an approved or cancelled change says so). After a reload the focus stays in the message box. *Checked* by B49.4, B49.12; the sign-out clear with real Clerk is *unverified* (#65).

![Enlarged bubble, with the Pin button](img/chat-enlarged.png)

### 6.3 Enlarge and pin

- **Make larger**: 640px wide, full height minus 5rem. Only now does **Pin** appear in the header.
- **Pin**: docks the chat beside the page. Page | 6px divider | chat. Default chat width 440px, min 320px, max 60% of the window. Drag the divider, or focus it and use ← / → (24px steps). The divider turns purple on hover and focus.
- Pinned chat: radius 26px card with a margin; Patch's button hides. Esc does not close it. The header shows **Unpin** (pressed state, purple).
- **Unpin**: floats it back as the enlarged bubble.
- Pinned is remembered; a pinned chat opens pinned after reload. The page underneath is not rebuilt when pinning or unpinning (it keeps its scroll and filters).

![Pinned beside the page](img/chat-pinned.png)

### 6.4 Keyboard and other entry points

- **Ctrl/Cmd+K** opens the chat on any page. **Esc** closes the bubble (not a pinned chat).
- **An alert** opens the CVE's own page (`/cves/CVE-…`, §5.15), with **Ask Patch** there. A link sent before B35 (`#cve=CVE-…` on any path) opens the same page; a malformed one is ignored. The banner with "Explain it" is gone.
- **A CVE id in an answer or on a tool card** (B35) links to its page in the app; the chat stays open. Only well-formed ids become links, never an id already in a link or in code.
- "Ask Patch" in the sidebar and the welcome banner's button open it too.
- "Ask about this" on a CVE row opens the chat over the CVEs page (header chip "on CVEs") and sends "Explain CVE-… and how to defend against it."

### 6.5 Phones

- The chat is a full-screen sheet (bubble or pinned). No pin button and no Make larger: the sheet is already full screen. Patch's button sits above the bottom tab bar.

### 6.6 A change Patch proposes (B21, 2026-10-15)

- When you ask Patch to watch or unwatch a product, change a CVE's status or a product's details, it **proposes** the change. The card sits **under the answer** (not folded into the details), so the next step is in view (`frontend/src/chat/ProposalCard.tsx`, `styles/proposals.css`).
- The card: `--nested-fill`, radius 18px, a 3px left edge (`--accent` while proposed, `--ok` when done, `--muted` when cancelled or expired). A state chip in words, `--text` on `--accent-soft` ("Proposed", "Done"; "Cancelled" and "Expired" on `--border`), then "Patch proposes a change" (muted). The title says what: "Mark CVE-2024-8309 fixed", "Add vLLM to your watchlist". Then "Why: …" when the model gave a reason.
- **Before → after** on one line that wraps: the before in `--muted`, an arrow hidden from screen readers, the after in bold. Screen readers hear "Before: Open After: Fixed". A status change's after is short (B49, #96 C3): "Accepted, review 2026-11-17", "Not affected, vulnerable code not present"; the reason or note, then "Control: …", each on its own line under it (`--text`, wraps). *Checked* by B49.3, B49.10.
- Under it, while proposed: "Nothing has changed yet. Approve it by 21:40 UTC, or ask Patch again later." (the 1-hour expiry, in UTC as elsewhere).
- Buttons (§5.3 pills): **Approve** (primary), **Edit** (only for a status or product details; a watch has nothing to correct), **Cancel**. While a request runs, all three are off and Approve says "Approving…" with `aria-busy`: a double click sends one request (and the backend returns the first result anyway).
- **Edit** opens the form inside the card: for a status, a Status select and the CVE decision dialog's own fields (`DecisionFields`: justification radios, note, reason, review date, compensating control, with the same limits); for product details, usage, version, internet-facing. Focus goes to the first field; Save changes or Back return focus to Approve.
- After the action, one line in an `<output>` (the §5.10 line rule: `--text` on a soft fill, the tone as the edge): "Done: Marked CVE-2024-8309 as fixed. See CVE-2024-8309 on the CVEs page" (`--ok` edge; the link opens `/cves?product=…&status=<the new status>` in the app (B33: closed CVEs sort last, so "all" could put it pages away), the chat stays open; a watchlist change links to Settings), "Cancelled: nothing was changed." or "Expired: …" (`--warn` edge). A refused approve (stale, expired) shows the backend's sentence as an alert (`--error` edge).
- No animation: nothing moves, with or without reduced motion. Light and dark come from the tokens.
- In the Tool calls tab, the update_watchlist card says "Proposed: {title}" and the before → after.
- **A proposed decision** (B22, from the research workflow's `propose_decision`) is the same card, plus "It rests on:" between the before → after and the buttons: one line per cited source, its number (`.source-n`), its title as a link (new tab), and a chip in words: "Knowledge base" (`--surface`, `--border` edge) or "Web result, unverified" (the web sources' chip, §6.2 web research). The flagged page is never listed: it can't be cited. In the CVEs page history, the record adds "Sources: [1] …; [3] … (web result, unverified)". *Checked* by B22.9 (light and dark, 400px and 1400px, chip contrast at least 4.5:1, the links before the buttons in Tab order) and the reduced-motion scene `b22_9_proposed_decision`.
- **A warning by the control** (B73, #134): when the proposal has a compensating control and your watchlist marks the product internet-facing, a line right under "Control: …": "Your watchlist marks LangChain internet-facing. Check this control matches." (the product's display name; the words come from the backend's `warnings`). The §5.10 line rule as the expired line: `--text` on `--warn-soft` with a 3px `--warn` edge (`--warn` text on `--warn-soft` is under 4.5:1 for small text). Screen readers hear "Warning: " first, since the edge is colour only. It asks you to check; Approve stays on. An edit that takes the control out, or a change in Settings, removes it next time the card loads. No motion. *Checked* by B73.4 (light and dark, 390px and 1400px, contrast at least 4.5:1, no sideways scroll) and the reduced-motion scene `b73_4_proposal_warning`.
- *Checked* by the browser check B21.9 (light and dark, 400px and 1400px, keyboard, the chip's and the line's contrast at least 4.5:1) and the reduced-motion scene `b21_9_proposal_card`.

### 6.7 Buttons on tool cards (B24, 2026-10-16)

- Tool cards end with the next step as buttons (`frontend/src/chat/CardActions.tsx`, `styles/cardActions.css`). Plain pills (§5.3, 2rem tall, 0.82rem) in a row that wraps. Each sends a structured action to `POST /chat/action`, never free text.
- **Which card has which**: the fix-first card: "Open in CVEs page" (a link under the list, the card's filters, open CVEs, in the app), and per row **Ask about this** and **Mark accepted…** (open rows only). The lookup and am-I-affected cards: **Watch this product** (a product not watched), **Set my version…**, **Mark not affected…** (open or accepted CVEs). A product's am-I-affected card: Set my version…. The search card (new: its sources, number, title, kind, severity, KEV): **Show only CVEs** and **Only critical**, with "Searches again with that filter." (muted).
- Screen readers hear what each button acts on: "Mark not affected… CVE-2024-8309", "Set my version… LangChain", "Ask about this: CVE-2025-3248".
- **A change** only proposes (§6.6). "Watch this product" makes its proposal card at once; a "…" button opens a small form under the row first (`aria-expanded`; the version, or the decision dialog's `DecisionFields`), on `--surface`, with **Propose** (primary) and **Back**. Focus goes to the form's first field; Back returns it to the button; a new proposal card shows under the row, with focus on its Approve. "It's already so" is a line in an `<output>`: `--text` on `--accent-soft` with an `--accent` edge.
- **A refine** acts at once: the search runs again with the filter, and its result is a new message at the end of the chat: the chips of what was applied ("Only CVEs", "Only critical"; `--text` on `--accent-soft` with an `--accent` edge), "Searched again with this filter: N sources. Patch didn't write a new answer: ask him to explain these." (muted), then the search card, open, with the refines not applied yet. Focus moves to the chips. The answer above is unchanged.
- **Ask about this** asks "Explain CVE-… and how to defend against it." at the saved level, with the CVE in the page context (A18), as on the CVEs page.
- No animation: nothing moves, with or without reduced motion (the refine button's spinner is the Check now one, still with reduced motion). Light and dark come from the tokens.
- *Checked* by the browser check B24.7 to B24.10 (light and dark, 400px and 1400px, keyboard, the buttons' and the chips' contrast at least 4.5:1, no sideways scroll) and the reduced-motion scene `b24_11_card_actions`.

### Checklist: chat

- [ ] Patch on the pill, in front, with shadow; mood and unread dot as specified.
- [ ] Open: pop animation, Patch steps off, pill turns purple with ✕, window sits just above the pill.
- [ ] Header, greeting, suggestions, inline details as specified.
- [ ] Pin only on the enlarged bubble; divider by mouse and keyboard; Esc rules; remembered; page not rebuilt.
- [ ] Ctrl/Cmd+K, Esc, "Ask about this".
- [ ] A step that didn't finish (B20): "Didn't finish" on its card, Try again for that step only, "OK on retry" and the note; the answer names the missing step; a failed send keeps the message in the box.
- [ ] A limit or the spending cap (B11, B49): a quiet muted line with the retry time, no red bubble, Patch idle, the question only in the box (no sent bubble), the note once, 4.5:1 in light and dark, no sideways scroll at 400px.
- [ ] The usage line only for the owner and Reviewers; counts in the singular for one (B49).
- [ ] The conversation kept for the tab's life, per user; cleared on sign-out; works with storage blocked (B49, §11).
- [ ] Phone: full-screen sheet, no pin, no Make larger.
- [ ] A proposed change (§6.6): card under the answer, before → after, Approve/Edit/Cancel by keyboard, nothing changes until Approve, one request per double click.
- [ ] A control on an internet-facing product (B73, §6.6): the warning line under "Control: …", "Warning: " for screen readers, in light and dark at 4.5:1, at 390px with no sideways scroll; gone when the control or internet-facing is (check B73.4).
- [ ] Web research (B08): the research card (query, results, time) and the web facts on each web source ("Web result, unverified", site, date, "Flagged" on an injection page), in light and dark at 4.5:1, at 400px with no sideways scroll, links by keyboard, still with reduced motion (checks B08.10 to B08.13).
- [ ] What's new (B06): the check_updates card (when, counts, new CVEs and alerts with source numbers, the CVEs link), the refused and snapshot titles, the dashboard loading again after a check, in light and dark at 4.5:1, at 400px with no sideways scroll, the link by keyboard (checks B06.5, B06.6). The card has no motion of its own.
- [ ] Buttons on tool cards (B24, §6.7): a change makes a proposal card and changes nothing until Approve; a refine adds a new message with its chips; each button named with what it acts on; forms open and close by keyboard with focus kept; in light and dark at 4.5:1, at 400px with no sideways scroll, still with reduced motion (checks B24.7 to B24.11).
- [ ] A proposed decision (B22, §6.6): "It rests on:" with each cited source and its chip ("Knowledge base", "Web result, unverified"), in light and dark at 4.5:1, at 400px inside the chat, links then buttons by keyboard, still with reduced motion (check B22.9).

---

## 7. Motion

All motion is part of the spec. **It stops with `prefers-reduced-motion: reduce`**: one global rule turns off every animation and transition (*checked* by the browser check A02.10: no running animations, cursor still, sidebar jumps to the rail). With normal motion, A02.9 checks that the cursor blinks and the sidebar width passes through in-between values.

### 7.1 Page motion

| What | Animation | Duration, easing | Delay | Repeats |
|---|---|---|---|---|
| Stat tiles, dashboard cards | fade up: from `opacity 0`, `translateY(6px)` | 0.45s, `cubic-bezier(0.2, 0.8, 0.2, 1)` | tiles 0 / 0.05 / 0.1 / 0.15s; main column 2nd card 0.12s, 3rd and 4th (Top 5 open CVEs) 0.24s; side column and the Watchlist filter (B43: before the tiles in the page) 0.12s | once, on load |
| CVEs page card | the same fade up | 0.45s, same curve | 0s | once, on load (not on a filter change) |
| Horizontal bars | grow from `scaleX(0)`, origin = the chart's axis (`--x0`) | 0.9s, same curve | 0.2s | once |
| Columns | grow from `scaleY(0)`, origin = bottom of each bar | 0.9s, same curve | 0.2s | once |
| Page title cursor | an "_" after the title, blinks | 1.1s, `steps(1)` | — | forever |
| KEV tile | wiggle: rotate −1.2° (91%), +1.2° (94%), −0.6° (97%), still otherwise | 4s, ease-in-out | — | forever |
| Bubble window | pop: from `opacity 0`, `translateY(8px) scale(0.98)` | 0.16s, ease | — | on open |
| Sign-in card and the access screens' card (§5.13) | the cards' fade up | 0.45s, the cards' curve | 0s | once, on load |
| Loading card (§5.14) | the cards' fade up | 0.45s, the cards' curve | 0.2s | once, on load |
| Landing page sections (§5.16) | the cards' fade up | 0.45s, the cards' curve | hero 0s, tiles 0.12s, the rest 0.24s | once, on load |
| Landing page screenshot frame (§5.16) | lifts 4px, deeper shadow | 0.2s, ease | — | on hover |
| Page not found card (§5.19) | the cards' fade up | 0.45s, the cards' curve | 0s | once, on load |
| CVE page cards (§5.15) | the cards' fade up | 0.45s, the cards' curve | head and assessment 0s; Facts, versions, history 0.12s | once, on load |
| User menu card (§5.13) | the bubble's pop | 0.16s, ease | — | on open |
| Sidebar collapse | width 250 ↔ 78px; chevron rotates 180° | 0.2s, ease | — | on toggle |
| Pin icon | rotates from 35° to 0° when pinned | 0.15s, ease | — | on toggle |
| Patch's pill | background and border colour | 0.15s | — | on hover / open |
| Check now spinner (§5.10, §5.12) | rotate 360° | 1s, linear | — | while a check runs |

![The dashboard mid-animation: bars still growing](img/motion-midway.png)

### 7.2 Patch's motion

See section 8.3.

### Checklist: motion

- [ ] Every row of 7.1 and 8.3 is implemented with these timings.
- [ ] Charts animate on first load of the page, not on hover or resize.
- [ ] Stacked bars grow as one piece (no gaps opening between segments).
- [ ] With reduced motion: nothing moves (tiles, cards, bars, cursor, KEV wiggle, bubble pop, Patch, sidebar width, pin icon). Fixed in the real build (12.1). Checked by one shared check, `frontend/e2e/reduced_motion.py`: a ticket that adds motion adds a `@scene` in its own test file (review, 2026-10-15; scenes per file since the spec B retro, 2026-10-16).

---

## 8. Patch

![Patch's four moods, four animations each (still poses)](img/patch-moods-light.png)

### 8.1 Drawing

The **squircle robot** from the design canvas "Robot Style Explorations" (2026-10-14, A06b). The canvas's four artboards are saved in [patch/](./patch/) (reference only), so the design doesn't depend on a private link. `viewBox="0 0 160 170"`, height = width × 170 / 160. Parts, back to front:

| Part | Shape | Colour |
|---|---|---|
| Shadow | ellipse, ry 5, under the body (cy 148–160, rx 42–50 by variant) | `#2A2457`, 12% (14% where it animates) |
| Antenna | line (80,42)→(80,22), 5px, round cap; light: circle r 7 at (80, 19) | stem `#9483FF`; light `#FFC94D` (heart eyes `#FF6F91`, alert `#FF6B8E`, siren `#FF4D6D`) |
| Body | 112 × 106 rounded rect, **rx 44**, at (24, 40) | `#9483FF` |
| Highlight | ellipse 11 × 6 at (50, 60), rotated −32° | white, 35% |
| Visor | 72 × 40 rounded rect, rx 20, at (44, 68) | `#2A2457` |
| Eyes | by variant: ovals 6 × 7 at (67/93, 88); scanning dots; three typing dots; arcs (happy); hearts; wide circles r 9 with a highlight or a pupil (alert) | `#7FF0DD` |
| Cheeks | ellipses at (44/116, 122) on some variants | `#FFB3CF` (idle), `#FF9EC0` (happy) |
| Mouth | by variant: small smile, flat line, wavy "hmm", dot, open smile, grin, "o" | `#2A2457` |
| Extras (outside the body) | thought dots, radar pings, sparkles, music notes, floating hearts, alarm lines, the siren beam and halo, the "!" badge | `#B4A9FF`, `#FFC94D`, `#9483FF`, `#FF9EC0`, `#FF6F91`, `#FF6B8E`, `#FF4D6D` |

- **Fixed colours**: all of the above are the same in light and dark mode, and are the only literal colours outside the tokens besides those in §3.1 and §5.1 (see the token checklist). The purple body stands out on both page backgrounds and surfaces (*checked*, img/patch-moods-dark.png).
- Patch is decorative (`aria-hidden`); the button or text next to him carries the meaning.
- He uses no gradients or other ids, so several Patches on one page can't clash (the browser check asserts ids stay unique).
- Each `svg.robot` says what it shows: `data-mood` and `data-variant`.

### 8.2 Where he appears, and how he overlaps

He always **overlaps what he sits on**, so he looks like he's in the scene, not pasted on.

| Place | Size | Overlap | Shows |
|---|---|---|---|
| Chat button | 68px | stands **in front** of the pill, overlapping its top edge, shadow on the pill; top 8px above the button (changed 2026-10-16: was 58px) | his mood |
| Chat header | 34px | sits in the title row | his mood (the same animation as the button) |
| Empty-chat greeting | 58px | **in front of** the speech bubble, over its top-left corner; floats so only the first line of text sits beside him, the rest runs under him (changed 2026-10-15: at 92px behind the bubble, the squircle was half hidden) | idle, picked on page load |
| Welcome banner | 110px | head rises **over the banner's top edge** (−2.4rem) | idle, picked on page load |
| Sidebar snapshot card | 64px | head pokes **over the card's top edge** (−2.6rem) | idle, picked on page load |
| Landing page hero (§5.16) | 150px | head rises **over the hero's top edge** (−4.2rem), the example alert under him | idle, picked on page load |
| Landing page end card (§5.16) | 96px | head **over the card's top edge** (−2.8rem) | happy, picked on page load |

- Thought dots, sparkles, notes, hearts, the "!" badge and the siren beam reach outside the 160 × 170 box (the spin jump rises 30 units, the beam 33 above the light). No container around Patch cuts him off, and his extras never cover the unread dot or the header's buttons; the open pill's ✕ never meets him (he steps off). *Checked* for all 16 variants through their whole animation at 400px and 1400px, in both themes, Firefox and Chromium (A06b.6).

### 8.3 Moods

| Mood | When | Option A | Option B | Option C | Option D |
|---|---|---|---|---|---|
| **Idle** | otherwise | **Float**: hovers up 7px (2.6s); shadow shrinks to 80% (2.6s); antenna sways ±10° (1.8s); blink (4s) | **Breathe**: sits, squishes to 103.5% × 96.5% (3.2s); light glows 35–100% (3.2s); slow blink (6s); cheeks | **Look around**: eyes glance −7px then +7px while the body leans ±3° (5s); blink (4s) | **Little hop**: rests, then squash, hop up 16px, land (3s, last 30%); shadow shrinks with it; blink; cheeks |
| **Thinking** | an answer is on its way | **Tilt & scan**: tilted −7°, eyes scan ±3px (1.6s); three thought dots and the light pulse 25–100% (1.2s, delays 0 / 0.2 / 0.4s); flat mouth | **Typing dots**: the eyes become three dots that rise 5px in turn (1.2s, delays 0 / 0.15 / 0.3s); floats 5px (2.6s) | **Ponder**: rocks ±6° (3s); eyes up; light pulses; wavy "hmm" mouth | **Radar**: two rings ping out from the light to 3.4× (1.8s, 0.9s apart); blink; dot mouth |
| **Happy** | for **3 seconds** after an answer arrives; on the chat button while an answer is unread | **Bounce**: squash and stretch, up 8px (1s); antenna wiggles (0.45s); two sparkles pulse; arc eyes, open smile | **Spin jump**: squash, leap 30px with a full turn, land (2.2s); shadow shrinks; arc eyes | **Dance**: sways ±6px and ±10° (0.9s); antenna wiggles; ♪ ♫ rise and fade (1.8s, 0.9s apart); grin | **Heart eyes**: heart eyes beat to 125% then 115% (1.2s); two hearts rise (1.8s); floats 6px; pink light |
| **Alert** | the last message is an error | **Shake**: stretched tall, trembles ±3px (0.5s); alarm lines; wide eyes, "o" mouth | **Startle jump**: squash, jolt up 24px, land (2.4s); pinprick pupils | **Siren**: the light flashes red/yellow (0.6s), a three-beam light turns (1.2s), the halo pulses (0.6s); wide eyes | **Pop-up "!"**: a red "!" badge pops in and out (2.6s) as he freezes tall and his eyes widen to 110% |

All animations repeat forever, with the canvas's keyframes and easings (`styles/robot.css`).

- **The random rule**: each time Patch **enters** a mood he gets one of its four at random. While he stays in it he keeps it, so a re-render never makes him flicker. The pick lives in the one mood source, `usePatch` (the chat button and the header read it, so they always agree). Its random source is injectable: tests pick a known variant.
- **Places without a mood** (the greeting, the banner, the snapshot card) show idle, in one variant picked at random on page load.
- **Reduced motion**: nothing moves. Each variant shows its still pose (the canvas drawing), which keeps its face: arc eyes or heart eyes for happy, wide eyes and the "!" badge or the beam for alert, the typing dots for thinking. Animated shadows and the halo rest at their first keyframe's opacity (*checked*, the shared reduced-motion scene a06b_7).

![Patch's four moods in dark mode](img/patch-moods-dark.png)

### Checklist: Patch

- [ ] Drawing matches 8.1 and the artboards in [patch/](./patch/); ids unique per instance; `aria-hidden`.
- [ ] Every placement in 8.2 with its size and overlap; extras never cut off and never on the unread dot or the header's buttons.
- [ ] All four moods with their triggers; all 16 variants with the canvas keyframes; a new pick only on entering a mood; header and button always agree.
- [ ] Reduced motion stops all of Patch's movement and keeps each variant's face.
- [ ] The same drawing in light and dark mode.

---

## 9. Light and dark

- A sun/moon button in the top bar switches between them.
- Start: `?theme=light|dark` in the URL wins, then the saved choice, then the system setting.
- The choice sets `data-theme` on `<html>`; dark tokens hang off that.
- Everything has a dark value: tokens, chart colours, map dimming, the page glow. The candy tiles and Patch stay the same in both.

![Phone, dark mode](img/phone-dark.png)

### Checklist: theme

- [ ] Toggle switches instantly, is remembered, and overrides the system.
- [ ] Every page checked in both modes (dashboard, settings, dev, chat open, chat pinned).

---

## 10. Accessibility

- **Contrast**: section 3.1 and 5.1 values (*checked*). Open issues in 12.1.
- **Colour is never alone**: map shapes, chart legends, "Show as table" under every chart and the map, KEV has a label and an icon, the unread dot sits on a named button.
- **Keyboard**: everything reachable; visible focus (purple ring on sliders and the divider, purple border on Patch's pill); Ctrl/Cmd+K and Esc; divider moves with arrow keys. Each chart is **one Tab stop**: Tab lands on its bar last focused (the first at the start), arrow keys, Home and End move between its bars with their tooltips, and the next Tab leaves the chart (a roving tabindex; review, 2026-10-15).
- **Screen readers**: collapsed sidebar keeps its labels (visually hidden); Patch is `aria-hidden`; buttons have names ("Ask Patch", "Close the chat", "Make larger", "Pin: dock the chat beside the page", "Unpin: float the chat over the page", "Switch to dark mode", "Close Patch's welcome", "Collapse the sidebar").
- **Reduced motion**: section 7.

---

## 11. Remembered state and URL parameters

| Key (localStorage) | Meaning |
|---|---|
| `theme` | `light` or `dark` |
| `pinned` | `1` when the chat is pinned |
| `splitWidth` | pinned chat width in px |
| `sidenavCollapsed` | `1` when the sidebar is a rail |
| `helloHidden` | `1` when the welcome banner was closed or switched off on Settings; `0` (or absent) shows it |
| `signedInHere` | `1` when Clerk last said this browser was signed in, `0` when signed out (B42); `pending` once the sign-in form shows, and while Clerk says signed out there (B51). `1` and `pending` pick "Opening Patch" over the landing page while Clerk loads (§5.16); read once as the page loads. An abandoned sign-in costs the next visit a short wait |

| `chat` (sessionStorage, B49) | the conversation for this tab: the user's id and the latest 40 messages. A reload keeps it, closing the tab clears it; another user reads nothing; signing out clears it (§6.2) |
| `signInTarget` (sessionStorage, B60) | the in-app address (path, query, hash) a signed-out visitor opened, kept by the landing page; Clerk's form goes there after sign-in or sign-up, and the app's first page follows it once, then removes it. Landing on `/` removes it. Only a same-origin path (one leading `/`) is written or read: anything else is ignored (§5.13) |

- All reads and writes are wrapped so a blocked storage (private windows) never breaks the app. The welcome choice also keeps its last value in memory, so with storage blocked the Settings switch still holds until a reload.
- URL: `?theme=light|dark`. Old links: `?layout=split` pins the chat; other `?layout=` and all `?design=` values are ignored.
- Paths: `/`, `/cves`, `/cves/CVE-…` (one CVE's page, B35), `/settings`, `/dev` (A04b), `/about` (the landing page in the app, B42), `/sign-in` (the sign-in form with sign-in on, B42; signed in, the dashboard). Any other path: Page not found (§5.19, B49). The CVEs page's filters: `product`, `severity`, `status`, `kev=1`, `since=YYYY-MM-DD`, `new=1` (§5.9). The dashboard's product filter: `/?product=langflow,ollama` (A15b; URL only, never in localStorage). Alerts link to `/cves/CVE-…` (B35); an older `#cve=CVE-…` on any path opens that page. The CVEs list's page of rows and scroll live in its history entry (B35), never in localStorage.

---

## 12. Known gaps

### 12.1 Faults found 2026-10-13 (fixed in the real build 2026-10-14, A02)

- **Muted text on the page background is 3.9:1** (light mode), under 4.5:1. Affects the "Watching … · data as of …" line and the breadcrumb. **Fixed:** `--muted` is `#605d8c`: 4.9:1 on the page background, 5.2:1 on `--accent-soft`.
- **Primary button text** is 3.7:1 against the light end of the gradient (`#8b6cff`), 6.2:1 at the dark end. **Fixed:** the gradient starts at `#7454f7`: 4.8:1 and 6.2:1.
- **Two transitions ignore reduced motion**: the sidebar width (0.2s) and the pin icon rotation (0.15s). **Fixed:** the reduced-motion rule covers all transitions, so the pin icon (built with the chat) is covered too.

### 12.2 Unverified

- The prototype's browser checks ran in Firefox only. The real build's run in **Firefox and Chromium** (`frontend/e2e/run.sh`). Safari not checked.
- Offline font fallback not looked at.
- Uses modern CSS (`:has()`, `color-mix()`): fine in current browsers, not in old ones.

---

## 13. How this was checked

- `proto/frontend/e2e/check_ui.py` (Playwright, Firefox): 35 checks, all passing on 2026-10-13. Covers the dashboard, settings, dev panel, chat (bubble, enlarge, pin, unpin, keyboard), light and dark, phone width, sidebar collapse, the welcome banner, Patch as the button.
- Chart colours: the dataviz skill's validator (commands in 3.2).
- Contrast: measured with the WCAG formula (values in 3.1 and 5.1).
- The real build's browser check (`frontend/e2e/test_shell.py`, Firefox and Chromium) covers tokens, contrast, the shell, both themes, 400px and 1400px, and motion with and without reduced motion.
- `frontend/e2e/test_chat.py` (A06, A06b) covers Patch (the squircle drawing, unique ids, all 16 variants with the canvas keyframes and faces, the random pick only on entering a mood, his motion envelope against every place's clipping and nearby controls, placements and overlaps, the four moods and their triggers, the unread dot), the bubble window (position above the pill, pop, header, greeting, suggestions), inline details and citations, the flag notice, keyboard, both themes at 400px and 1400px, and that nothing in the chat moves with reduced motion. The open pill uses the primary gradient, not `--accent`: white on dark-mode `--accent` would be 2.6:1. The prototype's check did **not** check animations or reduced motion. Worth adding in the real build: one test that the bars and Patch animate, one that nothing animates with reduced motion.
- `frontend/e2e/test_cves_page.py` (A04b) covers the CVEs page: navigation and paths, the table at full width (moved A04.7 and A04.11 checks), filters in the URL and reload, the tile links (count matches the tile), the "Top 5 open CVEs" card, the alert link on `/cves`, stacked cards at 400px, row actions in view with the chat pinned at 1400px, fade-up delays, reduced motion, light and dark.
- `frontend/e2e/test_priority.py` (A16) covers priority and due dates: the Priority and Due columns and their order, the KEV deadline as its own fact, internet-facing and the verdict moving a CVE, the Top 5 and the KEV tile, the policy card (save, out-of-order days, threshold), the `lookup_cve` card, chip contrast for all four levels in light and dark at 400px and 1400px (pinned too), reduced motion and the keyboard.

# Patch: the design reference

The four artboards of the design canvas **"Robot Style Explorations"** (claude.ai, 2026-10-14): the squircle robot with four animation options per mood. Copied here on 2026-10-15 (A06b, #29) so the design no longer depends on a private link.

- `AnimIdle.dc.html`, `AnimThinking.dc.html`, `AnimHappy.dc.html`, `AnimAlert.dc.html`: one artboard per mood, four SVGs each (`viewBox="0 0 160 170"`) and their keyframes.
- `canvas.json`: the canvas layout (board titles and positions).

**Reference only.** These files are not part of the app and don't open properly on their own: they load a `support.js` and a Google Fonts stylesheet that aren't in the repo. Read the SVG and `<style>` blocks inside them. The built Patch is `frontend/src/components/Robot.tsx` and `frontend/src/styles/robot.css`; DESIGN.md §8 describes him.

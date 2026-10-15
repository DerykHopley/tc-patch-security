# Coding standards for review

Judgement calls a reviewer checks by reading. Anything a tool can check goes into lint or a test instead (oxlint in `frontend/.oxlintrc.json`, pytest, the browser check), not here. Words follow [GLOSSARY.md](./GLOSSARY.md); decisions and their reasons are in [DECISIONS.md](./DECISIONS.md).

## UI

- **The DESIGN.md checklist applies to every UI change.** Each area of [docs/design/DESIGN.md](./docs/design/DESIGN.md) ends with a checklist (tokens, layout, components, chat, motion, Patch, theme). A UI change is done when its checklists pass, animations included, in light and dark, on a phone, with reduced motion, by keyboard. The browser check grows with each UI ticket. Reduced motion has one shared check (`frontend/e2e/test_reduced_motion.py`): add a scene to it, not a test of your own.
- **Tokens, never hard-coded colours.** Components use the CSS custom properties from DESIGN.md §3. The only literal colours allowed are the fixed ones DESIGN.md lists: the primary gradient and the purple shadow (§3.1), the stat-tile gradients and shadows (§5.1), and Patch's drawing (§8.1). Why: one place to change a colour, and dark mode can't miss a component.

## Safety

- **Untrusted text always goes through the guard.** Retrieved knowledge, tool output and (later) web pages are data, never instructions: they reach the model only wrapped by the guard, and user messages are checked by it (flagged, never blocked). New text sources, new tools and new prompt parts included. Why: an instruction hidden in a CVE description must not steer Patch.
- **Rules decide, the LLM explains.** Verdict, priority, due dates and the order of "what to fix first" come from pure functions with table tests. Patch only explains their output; it never re-ranks, changes a CVE status, or invents a verdict. Why: the same input must give the same answer, and the owner can audit the rules.

## Tests

- Tests check behaviour through a public seam (the HTTP API, a pure function, the browser), as in spec A's testing decisions.
- Each test names the check id it covers: `A<ticket>.<n>`, e.g. `test_a01_2_default_watchlist_without_file`. Ids are per ticket so parallel work never reuses one.
- Browser checks wait on the real condition (`expect()`, or `settled()` / `eventually()` in `frontend/e2e/test_shell.py`), never a fixed time: a fixed wait passes locally and fails on CI's slower runner. `check_waits.py` fails CI on a fixed wait without `# allowed: <reason>` on its line, and `E2E_LATENCY_MS=300 frontend/e2e/run.sh` shows races before CI does.
- No test calls the network or needs a key. The browser check runs only against its own servers on two free ports (`frontend/e2e/run.sh`), never the app on 8000/5173.

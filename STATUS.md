# Status and handoff

Where the project stands, how to run it, and what's open. Written 2026-10-13 at the end of a long session, so a fresh session can pick up from here. Read CLAUDE.md first, then this.

## In one paragraph

`proto/` is a working LLM-security RAG assistant on a frozen snapshot of public data (OWASP LLM Top 10, OWASP Top 10 2025, MITRE ATLAS 5.6.0, 929 NVD CVEs for 12 LLM products, 9 CISA KEV entries). It has a chat with query translation, self-query filters and 4 tools; a CVE dashboard for a watchlist; a settings page for alerts; a dev panel for models, search tuning, an embedding map and a model check; a bubble chat that can be pinned beside the page when enlarged, and the Playful design with Patch the robot as the assistant and a light/dark toggle. Answers come from a scripted FakeLLM by default; local models and OpenRouter are wired in but have never answered for real.

## How to run it

```bash
cd proto/backend && uv run uvicorn app.main:app --reload --port 8000   # FakeLLM, state in data/state.json
cd proto/frontend && npm run dev                                       # http://localhost:5173
```

- At the end of the session both were running in the background (port 8000 with `--reload`, port 5173). If they aren't, start them as above.
- Your watchlist, CVE statuses, settings and alert log are in `proto/backend/data/state.json` (git-ignored). Delete it, or use Settings → Reset demo data, to go back to the defaults.
- Model check runs are saved in `proto/backend/data/evals/`.

## How to test it

- Backend: `cd proto/backend && uv run pytest` → **135 passed** (2026-10-13). No key, no network.
- UI: `proto/frontend/e2e/check_ui.py` (Playwright, Firefox) → **35 of 35 passed** (2026-10-13). It marks CVEs fixed and changes settings, so **never run it against your real state**. Use a second pair of servers:

```bash
cd proto/backend && STATE_PATH=/tmp/ui-state.json .venv/bin/uvicorn app.main:app --port 8001
cd proto/frontend && VITE_API_URL=http://localhost:8001 node_modules/.bin/vite . --port 5174
UI_URL=http://localhost:5174 uv run --with playwright python e2e/check_ui.py      # ONLY=layouts or ONLY=designs for just those
```

- Type check and lint: `cd proto/frontend && npx tsc -b && npx oxlint src`.

## What's built (all 2026-10-13)

| Part | Where | Notes |
| --- | --- | --- |
| Snapshot data | `proto/backend/scripts/build_fixtures.py` → `fixtures/` | Rebuild from `feasibility/data/` (`feasibility/fetch.py` downloads fresh data) |
| RAG pipeline | `app/rag/` | Section-aware chunking (1,680 chunks), hash embedder (mock) with a shared-word gate, filters before scoring, multi-query + RRF, 2 chunks per document |
| Chat tools | `app/tools/` | `search_security`, `lookup_cve`, `explain_weakness`, `update_watchlist` |
| Guard | `app/guard.py` | Flags injection phrasing instead of blocking (in this domain it's a normal topic); escapes, never strips, tool output |
| Dashboard | `app/dashboard.py`, `Dashboard.tsx` | 4 tiles, 3 SVG charts, CVE table with actions, watchlist editor |
| Settings page | `Settings.tsx` | Alert rules (saved for the future worker), delivery channels with real test sends, reset |
| Notifications | `app/notify.py` | Desktop (`notify-send`, sent and arrived once), email (SMTP), ntfy; config and secrets in `.env` |
| Dev panel | `DevPanel.tsx` | Provider and model, search sliders, index facts, search playground, embedding map (PCA), model check |
| Local models | `app/llm/openai_compat.py`, `router.py` | Any OpenAI-compatible server on localhost (Ollama, LM Studio, llama.cpp); switch at runtime |
| Model check | `app/evals.py`, `ModelCheck.tsx` | 11 questions, exact checks (tools, filters, key fact, citations, flag, no exploit code); FakeLLM baseline 11/11, 37/37 |
| Chat layout | `App.tsx`, `ChatSurface.tsx` | The bubble only: Patch's button opens it; enlarged, Pin docks it beside the page. Tabs, drawer, split and side panel removed (2026-10-13). |
| Design | `designs.css`, `index.html`, `Icons.tsx`, `Robot.tsx` | Playful (decided 2026-10-13; Classic, Glass and Clean removed, Neon HUD's motion kept). Patch (`Robot.tsx`, `useMood.ts`) is the chat button. Light/dark toggle (`?theme=dark`). Bottom tab bar on phones. |
| Process map | `docs/process-map.html` | A standalone page: open it in a browser. Also published privately at https://claude.ai/artifact/3umq2VmcfLxNfG2LD6ZjVm. To republish: strip the outer `<!doctype>`/`<html>`/`<head>`/`<body>` tags into a copy (the publisher adds its own) and publish that copy to the URL |

The details are in `proto/SPEC.md` (every check by ID), `proto/PLAN.md` (layout and seams), and the two READMEs.

## Waiting on the user

1. **A real local model run.** Ollama is installed but has no usable models; LM Studio has Qwen3-Coder-30B-A3B, Qwen3.6-27B and embeddinggemma-300m downloaded, but its CLI (`lms`) can't find the app to start the server. GPU: Radeon RX 7900. Options offered:
   - (recommended) the user starts LM Studio's server (Developer tab) with Qwen3-Coder-30B-A3B, then Dev → Model → Local → LM Studio → Find models → Save → Run model check;
   - import the GGUF into Ollama (copies ~18 GB);
   - pull a small Ollama model (~5 GB download).
2. **Layout: decided (2026-10-13).** The bubble, with Pin on the enlarged bubble to dock it beside the page. The side panel was removed.
3. **Design: decided (2026-10-13).** Playful, with Patch. Full spec to build from: [docs/design/DESIGN.md](./docs/design/DESIGN.md). The others were removed; their story is in [docs/design-examples/](./docs/design-examples/README.md). Screenshots and the reasoning for the review: [docs/design-examples/](./docs/design-examples/README.md).

## Next steps, roughly in order

- **Next session:** grill the plan with the docs, deep-dive, then write the build spec. The prompts to paste are in [docs/NEXT-SESSION-PROMPTS.md](./docs/NEXT-SESSION-PROMPTS.md); DECISIONS.md has what's decided and open.
- **The shortlist** (process map, Flow 5): am I affected? (OSV.dev), explain levels, priority by rules (KEV, EPSS, policy), live refresh + `check_updates`, web research (Tavily) through the guard. Verify OSV, EPSS and Tavily first.

- Run the model check on a real local model; compare with the FakeLLM baseline. Expect trouble with self-query filters and tool choice.
- Real embeddings: embeddinggemma-300m is already in LM Studio. Then hybrid search (BM25 + vectors) for CVE ids and product names, a course "hard" option.
- Page-aware chat: pass the dashboard's filters or the selected CVE to the chat, so "what should I fix first?" means the current view.
- The refresh worker from ALERTS-PLAN.md (steps 1–3, 5–7). The notifiers are done.
- Offered, not built: a CVE scatter on the dashboard (published date × CVSS, colour by product, ring for KEV), a knowledge-graph view, a products × OWASP heatmap.
- From the first run's review, still open: check citations after the answer; source numbers restart each request.
- 174 of the 184 CVEs whose product came from description text are unchecked.

## Course brief coverage (REQUIREMENTS.md)

- Core: RAG, query translation (multi-query + RRF), structured retrieval (self-query), 4 tools, domain security, error handling, validation, a UI with sources, tool results and progress. All there, on FakeLLM.
- Optional, done or nearly: source citations, conversation history, RAG visualisation (playground + embedding map), prompt-injection protection (medium), token usage display (medium), tool-result visualisation (medium), multi-model support (medium, untested for real), logging of alerts, an evaluation (hard, own exact-check model check instead of RAGAS).
- Not yet: export, auth, rate limiting, hybrid search, automated KB updates (the worker), MCP.
- The brief suggests LangChain + OpenRouter + Streamlit/Next.js; the user confirmed these are optional (2026-10-12). The prototype uses FastAPI + React and the `openai` SDK.

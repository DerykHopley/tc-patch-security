# Factory plan: a research prototype

> **History.** This experiment finished on 2026-10-12. Don't log new work with `factory/log_stage.py`. The current state is in [STATUS.md](./STATUS.md); decisions in [DECISIONS.md](./DECISIONS.md).

A quick experiment: build a very small version of the chatbot with an agentic "software factory" workflow, and measure what the factory costs.

Written 2026-10-12.

## What this answers

- **Main question:** can short, staged agent sessions build a working prototype that meets the brief, and what does that cost in tokens, money, energy and my time?
- **Not answered here:** how good the RAG is. Most of it runs on mocks. The real chatbot comes later and can reuse the code that holds up.

## Decisions

- Backend: **Python**, FastAPI.
- Frontend: **React + TypeScript** (Vite). Not Streamlit. TypeScript is practice; keep the UI small.
- LLM: one `LLM` interface with two versions. `FakeLLM` (default) returns canned answers: free and the same every run. `OpenRouterLLM` sits behind a flag for one manual check at the end.
- Retrieval: real but tiny. About 20 fixture articles with metadata (source, date, topic). Embeddings from a fake hash embedder by default, with plain numpy cosine similarity. No vector database.
- Time box: **4 sessions of 30–45 minutes.** When the time is up, stop and log the stage, even if it's unfinished. An unfinished stage is a finding.

## The stages

Each stage is a **fresh Claude Code session**, so its tokens are counted on their own. Stages hand over files, not chat history.

| # | Session | Input → output | Done when |
| --- | --- | --- | --- |
| 0 | Planning (this one) | brief → this file, `factory/` | Done |
| 1 | Spec + plan | REQUIREMENTS.md, this file → `proto/SPEC.md` with acceptance checks, `proto/PLAN.md` with modules and mock seams | I've approved both |
| 2 | Build backend | SPEC, PLAN → `proto/backend/`: retrieval, query translation, 3 tools, `/chat` API, tests | `pytest` passes |
| 3 | Build frontend | SPEC, the API → `proto/frontend/`: chat, sources, tool results, a progress indicator | It runs against the backend |
| 4 | Review + report | everything → review findings and fixes, `factory/report.html`, a findings section | Report written |

## Scope of the prototype (one item per requirement)

- **RAG:** chunk the fixture articles, embed them, search by similarity. Show the sources in the UI.
- **Query translation:** multi-query with reciprocal rank fusion (RRF). With `FakeLLM` the rewrites are fixed per question.
- **Structured retrieval:** self-query. Turn the question into metadata filters (date, source, topic) plus a semantic query.
- **3 tools, all mocked:**
  - `compare_model_prices`: reads a fixture JSON shaped like OpenRouter's models API.
  - `summarise_url`: reads fixture pages, not the web.
  - `add_to_inbox`: appends to a local JSON file.
- **Validation and security:** length limits on input, a URL allowlist, and an obvious prompt-injection check. Return errors as clear messages.
- **UI:** chat, a sources panel, tool-call cards, a spinner.
- **Optional extra if there's time:** show token usage per answer, using the real token counts from the LLM.

## How to run each stage

Start a fresh session in this folder and paste the stage prompt.

**Stage 1:**
> Read FACTORY-PLAN.md and REQUIREMENTS.md. Write proto/SPEC.md (acceptance checks for each scope item) and proto/PLAN.md (modules, interfaces, mock seams, test plan). Grill me briefly on anything unclear first. Time box 30–45 min.

**Stage 2:**
> Read FACTORY-PLAN.md, proto/SPEC.md and proto/PLAN.md. Build proto/backend test-first. Use uv. Stop when pytest passes or the time box ends.

**Stage 3:**
> Read FACTORY-PLAN.md, proto/SPEC.md and the backend API. Build proto/frontend in React + TypeScript with Vite. Check it runs against the backend.

**Stage 4:**
> Review proto/ against proto/SPEC.md. Fix what's quick, list the rest. Then run factory/report.py and add a "Findings" section to FACTORY-PLAN.md.

**At the end of every stage**, log it from inside that session:

```bash
python3 factory/log_stage.py <stage> --tests pass --step-ins 2 --notes "one line"
python3 factory/report.py   # rebuilds factory/report.html
```

- `--step-ins` is my count of the times I had to correct or unblock the agent. The report also counts the prompts I typed, automatically.
- Re-run `log_stage.py` in the same session to update an entry.

## What the report shows

`factory/report.html`, one row per stage:

- Wall-clock and active minutes. Active time leaves out gaps over 5 minutes.
- Tokens by type: input, output, cache read, cache write. Subagent transcripts are included.
- Cost: API-equivalent, from Anthropic list prices (cached 2026-10-06). Cache writes cost 1.25× input (5 min TTL) or 2× (1 h TTL).
- Wh: reuses `~/.claude/statusline-energy.py`, so it matches the status line. Unverified estimate, order of magnitude only.
- Prompts, step-ins, test result, notes.

## Separate test: superpowers

A completely separate test, run on its own and compared afterwards: build the prototype with [obra/superpowers](https://github.com/obra/superpowers) instead of the staged sessions. Both log to the same report, so the costs sit side by side.

What superpowers is (from its README, checked 2026-10-12):

- A plugin of skills that trigger automatically and are "mandatory workflows, not suggestions".
- Its chain: brainstorming (a design doc) → using-git-worktrees → writing-plans (tasks of 2–5 minutes) → subagent-driven-development (a fresh subagent per task, a review after each) or executing-plans (inline, one review at the end: the README calls it "cheapest") → test-driven-development → finishing-a-development-branch.
- It says it can work on its own "for a couple hours at a time". No figures on token cost.

Set-up, so the two arms don't contaminate each other:

- A **separate folder**, `../sprint2-superpowers/`. It has its own transcripts, and superpowers' always-on skills can't change the staged sessions.
- `git init` there: the worktree step needs a repo.
- Superpowers is enabled **only in that folder**, at project scope. The mattpocock skills are switched off there, because they overlap (tdd, code-review).
- Telemetry off: `SUPERPOWERS_DISABLE_TELEMETRY=1` in that folder's settings.
- The **same input**, so the comparison is fair: a `BRIEF.md` with the "Decisions" and "Scope of the prototype" sections of this file. REQUIREMENTS.md is copied in only locally (course material, never published).
- Use **subagent-driven-development**: it's the most factory-like path. executing-plans could be a third arm later.
- The **same time box**: 3 hours of active time in total. Stop when it runs out.

How to run it (folder set up 2026-10-12, first commit `aa70cb5`):

- `.claude/settings.json` there lists the superpowers marketplace and turns the plugin on, and turns the mattpocock skills off. Claude Code should offer to install superpowers when you trust the folder. Unverified until the first run.
- If it doesn't offer, install it by hand. These are the README's commands; choose project scope if asked:

```bash
cd ../sprint2-superpowers && claude
/plugin marketplace add obra/superpowers-marketplace
/plugin install superpowers@superpowers-marketplace
```

- Before you start, check that `/plugin` lists superpowers as on and mattpocock-skills as off.
- Then paste:

> Read BRIEF.md and build the prototype it describes, in proto/. Use subagent-driven development.

At the end of each session, run this from that folder:

```bash
python3 ../sprint2-project/factory/log_stage.py build --workflow superpowers --tests pass --step-ins 1 --notes "..."
```

What to compare:

- Total cost, Wh and active minutes, without the planning stage.
- Step-ins and prompts: how much of me each arm needed.
- Did the tests pass, and does the scope list hold up? Check each scope item, for both arms.
- Superpowers is one long session, so its row doesn't break down by stage. The number of subagents and the plan's task list stand in for that.

## Things to watch

- Cache reads dominate the token count but are cheap. Compare output tokens between stages.
- Planning so far (checked 2026-10-12): ~$1 and ~45 Wh, mostly cache reads and writes.
- Start sequential. Try parallel subagents or a Workflow in one stage only, and only if a stage needs it, to compare the cost.
- Don't let mocks hide problems: list what the mocks hide in the findings.

## Findings

Written 2026-10-12, stage 4. Figures from `factory/report.html` (staged arm only; the superpowers arm hasn't run yet).

### The factory

- **Every stage finished in one pass, with 0 step-ins.** Checked: `stages.json`.
- **Much faster than the time box.** Planned 4 × 30–45 min. Actual active time: spec 3, backend 12, frontend 9, review 2 min (as the report counts it). Planning took 19.
- **Cost: about $7.30 API-equivalent and ~400 Wh for the whole run**, planning included. The Wh figure is an unverified estimate.
- **Backend was the most expensive stage** ($2.37, 60k output tokens). Planning came second ($1.87).
- **Cache reads are ~95% of all tokens** (8.5M of ~9M), as expected. Output tokens are the better measure of work.
- **Acceptance-check IDs paid off.** SPEC.md gave each check an ID (R1, V5 …) and the tests use them in their names. That made the review quick: read SPEC, grep tests, read code.

### What the review found

104 green tests, and still 3 real bugs. All were in security and error paths, where the spec was met to the letter but an edge case slipped through. A review stage earns its place.

Fixed in stage 4, each with a failing test first (107 tests now pass):

- **Tool output could close its own delimiter.** A page containing `<<<END_TOOL_OUTPUT>>>` ended the "untrusted data" block early, so the text after it looked like instructions. Fix: break up `<<<` and `>>>` inside tool output. (V5)
- **An LLM failure inside `search_news` was hidden.** The search tool calls the LLM to rewrite the query. If that call failed, the user got a tool error, not HTTP 502. Fix: `run_tool` re-raises `LLMError`. (V6)
- **Injections in the history weren't checked.** The client sends the history, so a hand-made request could put "ignore previous instructions" in an old user turn. Fix: check user turns in the history too. Assistant turns are skipped, since they may quote such text. (V2)
- **Frontend `.gitignore` didn't ignore `.env`.** Only `*.local` was ignored. No secret in it today, but added. (L3)

Listed, not fixed (for the real build):

1. **The LLM sees only 300-character snippets.** Chunks are up to 600, but the search tool passes `snippet` (`text[:300]`). A real LLM would answer from half the evidence. Pass the full chunk text to the LLM; keep the snippet for the UI.
2. **Citations aren't checked.** R6 holds only because `FakeLLM` writes the citations. A real LLM could cite `[7]` with 5 sources. Add a check after the answer.
3. **Source numbers restart at `[1]` each request**, but the history keeps old answers with old numbers. A real LLM may mix them up. Strip citations from history, or number sources across the chat.
4. **`response_format: json_object` isn't supported by every OpenRouter model.** Unverified which ones. The query rewrite would then fail with a 502. Fall back to parsing plain JSON.
5. **CORS allows only port 5173.** If Vite moves to 5174 because 5173 is busy, the UI shows "backend offline". Make the allowed origins a setting.
6. **The inbox write isn't atomic or locked.** Two requests at once could lose an item. Fine for one user.
7. **`add_to_inbox` stores any string as a URL.** Nothing displays it yet. Validate it once the inbox has a UI.
8. **The UI checks aren't repeatable.** Stage 3 ran Playwright by hand, but no script was kept. Save it as a test.
9. **`OpenRouterLLM` has never run.** The manual check (L2) is still open. It is the biggest unknown: see below.

### What the mocks hide

From SPEC.md, with what stage 4 could check:

- Hash embeddings only match words. Unchecked against real embeddings; the earlier experiments are the better guide.
- Scripted rewrites, filters and tool choice. Unchecked. Needs the OpenRouter run.
- The injection check is a regex list. Checked: it stops the listed phrases only. The delimiter bug above shows the delimiting needs tests too.
- Token usage is estimated. With `FakeLLM`, Q1 reports ~1,800 input tokens over 3 LLM calls. Real counts unchecked.
- No latency. Unchecked. Expect seconds per call with a real model.
- Fixture pages and prices. No network errors, timeouts or HTML parsing. Unchecked.

### Next

- Run the superpowers arm and compare.
- Do the OpenRouter check (L2) and log it as its own row.
- Possibly for ai-digest's `ideas.md`: the delimiter bug (tool output must not be able to close its own block), and passing full chunks, not snippets, to the LLM.

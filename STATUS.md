# Status and handoff

Where the project stands, how to run and test it, and what's open. Rewritten 2026-10-15 at the end of spec A, so a fresh session or a reviewer can pick up from here. The README says what Patch does and how to set it up; this file is for working on it.

## In one paragraph

Spec A, the real build, is done on the `spec-a` branch and waiting for review in [PR #24](https://github.com/DerykHopley/tc-patch-security/pull/24) (target date 2026-10-26). The app is in `backend/` (FastAPI) and `frontend/` (React, TypeScript). It runs on a frozen snapshot of public data (as of 2026-10-13). It has a chat with hybrid search, query translation, structured retrieval and six tools; a dashboard, a CVEs page with verdicts, priorities and decision records; Settings with the watchlist, policy and alert channels; and a Dev page with a model switch, a search playground, an embedding map and the model check. Real models answered on 2026-10-15: 11 chat models and 4 embedders, in the [model-check report](https://derykhopley.github.io/tc-patch-security/). Spec B (live refresh, alerts, web research, Cloud Run, Clerk) is planned as [#31](https://github.com/DerykHopley/tc-patch-security/issues/31), from the merge of spec A to 2026-11-02. `proto/` is the frozen prototype.

## How to run it

The full setup, with OpenRouter or local models: [README.md](./README.md#run-it). In short:

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000   # FakeLLM, hash embedder: no key
cd frontend && npm install && npm run dev                                    # http://localhost:5173
```

- With a real model: `backend/.env` (copied from `.env.example`, git-ignored) and `uv run --env-file .env ...`.
- **Defaults** (decided 2026-10-15, from the report): chat `anthropic/claude-haiku-5.5` on OpenRouter (the `OPENROUTER_MODEL` default); embedder `mxbai-embed-large` on Ollama (the Ollama default), off-topic threshold 0.58. FakeLLM and the hash embedder stay the no-setup defaults (`LLM_PROVIDER=fake`, `EMBEDDER=hash`), so tests and CI need no key and no service.
- A real embedder needs its index built once: `uv run --env-file .env python -m app.rag.build_index`. Give each embedder its own `INDEX_PATH`; the app refuses to start on an index built with another embedder.
- Your watchlist, statuses, decision history and settings: `backend/data/state.json` (git-ignored). Settings → Reset demo data goes back to the defaults.
- Model-check and retrieval runs: `backend/data/evals/` (not in git). The published report shows the runs named in `docs/report-src/runs.json` ([how to rebuild it](./docs/report-src/README.md)).
- The owner's own app runs on 8000/5173. Anything that changes data (the browser check, screenshots) runs on its own servers: `frontend/e2e/run.sh` picks two free ports and a throwaway state file.

## How to test it

No key, no network. Each command prints its own counts (passed, skipped), so this table keeps only what each check proves: a copied count goes stale with the next test, and every branch that edits it conflicts with the others (spec B retro, finding 3).

| Check | Command | What it proves |
|---|---|---|
| Backend | `cd backend && uv run pytest` | the API, the rules, the tools, the state store, the model check's scoring |
| Types, lint, unit tests | `cd frontend && npx tsc -b && npm run lint && npm test` | type check, oxlint, the frontend unit tests |
| Fixed waits | `python3 frontend/e2e/check_waits.py` | no fixed wait in the browser check without `# allowed: <reason>` |
| Browser check | `frontend/e2e/run.sh` (Firefox and Chromium) | the pages in light and dark, phone and desktop, by keyboard, with reduced motion; also the tooling tests (the fixed-wait check, the pre-commit hook, `scripts/ff-merge.sh`) |
| Slow mode | `E2E_LATENCY_MS=300 frontend/e2e/run.sh` | the same check with every API answer late: finds timing races before CI does |
| Built frontend | `E2E_BUILT=1 frontend/e2e/run.sh` | the same check against `vite build`, served by each backend as the container serves it (what CI runs) |
| Container image (B12) | `frontend/e2e/container.sh` (needs Docker) | image builds; /health, embedder check, no `.env` or secret, the Cloud Storage client present, a short browser check in Chromium |
| Report builds | `cd backend && uv run python -m app.evals fake-report --out /tmp/r.html` | FakeLLM and fake embedders; CI uploads it |

- CI ([.github/workflows/ci.yml](./.github/workflows/ci.yml)) runs all of these once per push to `main` or `spec-*`, and on pull requests from other branches. A docs-only push skips the browser check. The browser check runs as two jobs side by side, one per browser, so it takes half as long, against the built frontend (`E2E_BUILT=1`, #72): per job, Chromium 12:27 → about 8:40, Firefox 20:11 → about 16:50 (CI runs before and after; DECISIONS.md, 2026-10-16).
- The pre-commit hook (`.githooks/pre-commit`, on with `git config core.hooksPath .githooks`) runs two of CI's checks before each commit: no staged conflict markers, and the fixed-wait check.
- Merging a ticket branch into `spec-b`: `scripts/ff-merge.sh <branch>` (`--dry-run` first shows the plan). See [docs/agents/issue-tracker.md](./docs/agents/issue-tracker.md).
- Review rules that lint can't check: [CODING_STANDARDS.md](./CODING_STANDARDS.md). Each test names its check id (`A<ticket>.<n>`).

## What's built

Spec A's tickets ([#2](https://github.com/DerykHopley/tc-patch-security/issues/2)) and what was added along the way. The tickets close when PR #24 merges.

| Part | Where | Ticket |
|---|---|---|
| Walking skeleton, CI, snapshot, state file | `backend/app/main.py`, `state.py`, `backend/fixtures/` | A01 #3 |
| Design tokens and app shell (Playful, light and dark) | `frontend/src/styles/tokens.css`, `App.tsx` | A02 #4, gate A03 #5 |
| Dashboard: tiles, charts, Top 5, side panels, product filter | `frontend/src/pages/Dashboard.tsx`, `backend/app/dashboard.py` | A04 #6, A05 #7, A15b #30 |
| CVEs page: the table at full width, filters in the URL | `frontend/src/pages/CvesPage.tsx`, `cveView.ts`, `backend/app/cve_filters.py` | A04b #26 |
| Chat: bubble, enlarge, pin, keyboard, phone; Patch with moods | `frontend/src/chat/` | A06 #8, A07 #9 |
| Patch redrawn as the squircle robot, a random animation per mood | `frontend/src/components/Robot.tsx`, `patchPose.ts`, `docs/design/patch/` | A06b #29 |
| Real model through LangChain's `ChatOpenAI`; citation check | `backend/app/llm/`, `citations.py`, `agent.py` | A08 #10 |
| Chroma and real embeddings (OpenRouter, Ollama) | `backend/app/rag/vector.py`, `embed.py`, `build_index.py` | A09 #11 |
| Hybrid search: our own BM25 + RRF | `backend/app/rag/keyword.py`, `fusion.py`, `pipeline.py` | A10 #12 |
| Dev page: model switch, sliders, playground, embedding map | `frontend/src/pages/DevPage.tsx`, `backend/app/dev.py` | A11 #13 |
| Model check, retrieval check, HTML report | `backend/app/evals/`, `frontend/src/dev/` | A12 #14 |
| Settings: watchlist, alert rules, channels, policy, explain level | `frontend/src/pages/SettingsPage.tsx`, `backend/app/app_settings.py`, `notify.py` | A13 #15, A15b #30 |
| Snapshot additions: OSV versions, EPSS, product-match check, licences | `backend/scripts/snapshot_additions.py` | A14 #16 |
| Shared build code for the snapshot and the live refresh | `backend/app/cve_build.py` | B01 #32 |
| Live mode and Check now on the fake feeds; the refresh CLI (`uv run python -m app.refresh`) | `backend/app/refresh.py`, `live_data.py`, `feeds.py`, `frontend/src/components/Freshness.tsx` | B02 #35 |
| Real feeds (NVD, KEV, EPSS, OSV over HTTP, `FEEDS=real`) and the hourly schedule (`--schedule`, systemd user timer); the real run is a human step (#40) | `backend/app/feeds.py` `HttpFeeds`, `refresh.py` `run_scheduled`, `deploy/systemd/` | B03 #36 |
| Alerts after a live refresh: diff, rules, once per CVE and reason, digest, quiet hours, per-channel log, the dashboard's Recent alerts | `backend/app/alerts.py`, `frontend/src/components/AlertsLog.tsx` | B04 #37 |
| New since last check on the CVEs page: the "New" chip and `new=1` filter, `/cves?new=1`, kept per user | `backend/app/alerts.py`, `state.py`, `frontend/src/pages/CvesPage.tsx` | B05 #38 |
| Patch as an MCP server (stdio, four read-only tools); the real-client demo is a human step | `backend/app/mcp_server.py`, `docs/mcp-demo.md` | B23 #61 |
| Per-user state: a state store (local JSON files, in memory, Cloud Storage against a fake), the user from an auth dependency, alerts per user and only the owner's (`OWNER`) on the channels | `backend/app/store.py`, `users.py`, `auth.py` | B09 #41 |
| Clerk sign-in, built against faked tokens (no Clerk account yet): `AUTH=on` makes every route but `/health` need a session token checked with the JWT key (no network) and `azp`; the sign-in screen and user menu; decision records name the user. Creating the instance and keys is a human step (#65); the signed-in browser check runs only with its keys | `backend/app/auth.py`, `frontend/src/auth/`, `components/UserMenu.tsx`, `frontend/e2e/test_sign_in.py` | B10 #42 |
| Sign-in setup: SSO providers next to email and password, still invite-only; every Clerk step on Patch's page (never Clerk's hosted page), an invitation link opens "Join Patch", a sign-up without an invitation gets Patch's own "not invited" message; with `AUTH=on` the owner adopts the default user's state once. The real SSO round trip is the owner's check on #78 | `frontend/src/auth/signInView.ts`, `ClerkApp.tsx`, `backend/app/users.py` `adopt_default` | B31 #78 |
| The loading screen until `/health` answers (Patch, "Waking Patch up…"); after 15 s without an answer "Backend offline — retrying", with Retry and retries backing off from 2 s to every 30 s; an outright failure still shows the app saying "Backend offline" | `frontend/src/healthWait.ts`, `components/LoadingScreen.tsx`, `frontend/e2e/test_loading_screen.py` | #69 |
| Partial success and retry: each feed is a step, a partial refresh is written and shown with Retry; a failed tool step is marked, with Try again; a failed send or save keeps your work; failure switches (`FAKE_FEEDS_FAIL`, `FAIL_TOOLS`) | `backend/app/refresh.py`, `tools/registry.py`, `frontend/src/components/Freshness.tsx`, `chat/ToolCallCard.tsx`, `docs/failure-demo.md` | B20 #57 |
| Rate limits: chat messages per user per minute and per day (`CHAT_PER_MINUTE`, `CHAT_PER_DAY`), one 429 form with a retry time (a refused Check now too), OpenRouter's 402 as a plain 402, both shown as a quiet note in the chat | `backend/app/rate_limits.py`, `main.py`, `frontend/src/chat/useChat.ts` | B11 #43 |
| Cloud Run deploy setup: users' state and the live data in Cloud Storage (`STORE=gcs`, `GCS_BUCKET`), the scheduled refresh route for Cloud Scheduler (`POST /api/refresh/scheduled`, `SCHEDULER_SECRET` header, no user needed), the cold-start catch-up from the bucket, and the written procedure. Nothing run on Google Cloud yet: the deploy is a human step (#45) | `DEPLOY.md`, `deploy/cloudrun/`, `backend/app/store.py` `open_bucket`, `main.py`, `refresh.py` `scheduled_tick` | B13 #44 |
| Review fixes on spec B (check ids `BR.n`): Try again counts against the chat limit and runs only offered tools; web links http(s) only; the schedule and the demo switches are the owner's (others see the schedule read-only); a user who signed in gets alerts before saving anything; `AUTH=on` needs `OWNER`; one `CveId`, one proposal action map | `backend/tests/test_review_fixes.py`, `frontend/src/toolCalls.ts`, DECISIONS.md (BR rows) | #31 |
| The Dev page is the owner's: only the owner saves its choices, runs the playground and the checks, or finds local models (403 `not_owner`); anyone else sees the choices read-only, the reads stay open. `DEV_PANEL=false` is no longer needed for safety | `backend/app/dev.py`, `frontend/src/pages/DevPage.tsx` | B29 #76 |
| Pause the schedule and the run history: Pause on Settings (the dashboard says "Schedule paused", with Resume), the "Refresh runs" card (last 20 runs and skipped runs, each opening to its feeds), `GET /refresh/runs`, `check_updates` says whether the schedule is on | `backend/app/refresh.py` `run_scheduled`, `history`, `schedule_status`; `frontend/src/components/RefreshRuns.tsx` | B19 #59 |
| Settings instead of `.env` where safe: live or snapshot (switched with no restart), the NVD key, the quiet hours' time zone, the alert link address and the channels' details, owner only; secrets write-only; the environment wins. A phone alert or email links back only when a phone can open the address | `backend/app/server_settings.py`, `deps.py` `_apply`, `notify.py` `tap_link`, `frontend/src/components/ServerFields.tsx`, `serverSettings.ts` | B26 #70 |
| Live mode reads the real feeds by default (`FEEDS=real`; tests, `run.sh` and `container.sh` say `fake`, a conftest guard fails any test that would reach the real services); the owner's Data card says which feeds ("Live: NVD, CISA KEV, EPSS and OSV.dev", or a warning for the made-up test data, also on the freshness card); a live folder written by the other kind is refused (one with no record is accepted); a scheduled tick in snapshot mode is a skip (exit 0) | `backend/app/config.py`, `live_data.py` `check_feeds`, `refresh.py` `main`, `backend/tests/conftest.py` `no_real_feeds`, `frontend/src/freshness.ts` `feedsLine` | B28 #74 |
| Changes Patch proposes: a preview card, approve, edit, cancel; idempotent, 1-hour expiry, stale check | `backend/app/proposals.py`, `frontend/src/chat/ProposalCard.tsx` | B21 #58 |
| Buttons on tool cards: Open in CVEs page, Ask about this, Mark accepted…, Watch this product, Set my version…, Mark not affected… (each a proposal), Show only CVEs and Only critical on a new search card (a refine, shown as a new message with chips); `POST /chat/action` | `backend/app/card_actions.py`, `frontend/src/chat/CardActions.tsx`, `cardActions.ts` | B24 #63 |
| A page for one CVE, `/cves/CVE-…`: the full summary, product and versions, facts, your assessment with the actions, the decision history, NVD and OSV links; the CVE id links to it from the list, the Top 5, alerts, refresh runs and the chat; alerts open it (old `#cve=` links too, the banner is gone); Back returns to the list in place; "No such CVE" for an unknown id | `frontend/src/pages/CvePage.tsx`, `components/CveActions.tsx`, `backend/app/watched.py` `page` | B35 #85 |
| Shorter CVE rows: one main action and "More" (a disclosure with the rest) per row, each date once in the Due cell, cells on fewer lines; 4 → 9 rows in view at 1440×900 | `frontend/src/cveActions.ts`, `due.ts`, `pages/CvesPage.tsx` `RowActions`, `styles/cves.css` | B36 #86 |
| Web research that ends in a proposed decision: `propose_decision` cites its sources (web ones unverified), FakeLLM workflows (`steps`), model-check question Q-research on saved web results; the real-run demo is a human step | `backend/app/tools/decision.py`, `docs/mcp-demo.md` | B22 #62 |
| Model-check questions for the new tools: `Q-updates` (`check_updates`), `Q-web` (`research_web`, cites a web result), the injection page checked in `Q-web` and `Q-research` (flagged, warned, not followed, prompt kept); a run never refreshes; the real-model run is a human step (#47, [steps](./docs/report-src/README.md#the-new-questions-on-a-real-model-b16-47)) | `backend/app/evals/checks.py`, `fixtures/fake_script.json` | B15 #46 |
| Am I affected? Usage, version, verdict, `check_affected` | `backend/app/verdict.py`, `tools/affected.py` | A15 #17 |
| Priority by rules, policy, due dates | `backend/app/priority.py` | A16 #18, gate A17 #19 |
| Accepted status, decision records, "no fix yet" | `backend/app/status.py`, `frontend/src/components/Decision.tsx` | A16b #27 |
| What should I fix first? Page-aware chat, `prioritise` | `backend/app/page_context.py`, `tools/prioritise.py`, `frontend/src/pageContext.ts` | A18 #20 |
| Explain levels: simple, normal, deep dive | `backend/app/chat_turn.py`, `evals/readability.py`, `frontend/src/chat/LevelSwitch.tsx` | A19 #21 |
| Real model runs, report on GitHub Pages | `docs/report/`, `docs/report-src/` | A20 #22 |
| Guardrails: CI once per commit, slow mode, fixed-wait check, `report --runs`, `run.sh` on free ports | `.github/workflows/ci.yml`, `frontend/e2e/` | #56 |
| Spec B retro fixes (check ids `R.n`): the pre-commit hook, `DECISIONS.md merge=union`, reduced-motion scenes per test file (`@scene`), the merge script | `.githooks/pre-commit`, `.gitattributes`, `frontend/e2e/reduced_motion.py`, `scripts/ff-merge.sh` | [retro](https://derykhopley.github.io/tc-patch-security/retro.html) |
| Six architecture deepenings (watched-CVE assessment, page context, chat turn, state read model, CVE view, tool result shapes) | see the [architecture review](https://derykhopley.github.io/tc-patch-security/architecture-review.html) | DECISIONS.md, 2026-10-15 rows |
| README, STATUS, CLAUDE.md cut to pointers | this file, README.md, CLAUDE.md | A21 #23 |

## Real model runs (A20, 2026-10-15)

- 11 chat models on the same 14 questions (54 checks): 6 on OpenRouter, 5 local on Ollama 0.40.4 on an RX 7900 XTX (24 GB, ROCm). 4 embedders, one index each.
- Best answers: Claude Haiku 5.5 (51 of 54 checks, about $0.0015 per question). Best value: GPT-6 Luna. Best local: qwen3.8:27b. Best embedder: mxbai-embed-large. All checked in the runs; the reasons are in DECISIONS.md (2026-10-15 rows) and the report's Findings.
- Spend for all runs: about $0.40 of the key's $5 cap. *Unverified* against the OpenRouter bill.
- Not run: `openai/gpt-oss-120b` (not on the OpenRouter workspace's allow-list), `mistralai/mistral-small-2603` (same).
- Three bugs on our side were found by the first runs and fixed (citation rule for every tool, Unicode hyphens in CVE ids, curly apostrophes). The rest of the shared failures are follow-ups below.

## Real live run (B07, 2026-10-16)

The owner's app on `spec-b`, live mode with the real feeds (`FEEDS=real`), no NVD key, the systemd user timer installed. Checked in the timer's journal and the run's JSON.

| | |
|---|---|
| Run | scheduled tick, 14:02:15 to 14:05:31 UTC: **3 min 16 s**, 3.2 s CPU, 198 MB peak |
| Feeds | NVD, CISA KEV, OSV.dev and EPSS all answered (`status: ok`), NVD from the snapshot date (2026-10-13) |
| Found | 2 new CVEs (CVE-2026-110719 on Ollama, Medium; CVE-2025-63390, not watched), 1 updated, 0 added to KEV, 0 rescored |
| Alerts | none: the new watched CVE is below the minimum severity (High), and this week's overdue digest had already been sent |
| Next tick | 14:10 UTC skipped as not due (every 6 h), exit 0 |

- NVD accepted the `...000Z` dates without a key (B03's open point). The `apiKey` header is still unverified.
- Found on the way: live mode defaulted to the **fake** feeds, so the first "live" run alerted made-up CVEs (#74 makes the real feeds the default). Snapshot-mode ticks showed as failed services (also #74).
- Still open, not blocking: a real alert from a real run on the owner's phone, with its delay and screenshots (#75). The next weekly overdue digest (week 2026-W43) or a new watched CVE will send one.

## What's open

Follow-ups from spec A, not scheduled yet (`needs-triage`):

- From the model check: [#50](https://github.com/DerykHopley/tc-patch-security/issues/50) `explain_weakness` gives numbered sources; [#51](https://github.com/DerykHopley/tc-patch-security/issues/51) one search for all three explain levels; [#52](https://github.com/DerykHopley/tc-patch-security/issues/52) cite `prioritise`'s sources by rule; [#53](https://github.com/DerykHopley/tc-patch-security/issues/53) drop keyword hits when the vector search finds nothing on-topic; [#54](https://github.com/DerykHopley/tc-patch-security/issues/54) relax three checks that fail good answers; [#55](https://github.com/DerykHopley/tc-patch-security/issues/55) models and embedders to try later.
- Dashboard: [#25](https://github.com/DerykHopley/tc-patch-security/issues/25) the OWASP chart says it's the web list and counts every category; [#28](https://github.com/DerykHopley/tc-patch-security/issues/28) warn when a product leaves CVEs unfixed.
- Ideas: [#49](https://github.com/DerykHopley/tc-patch-security/issues/49) find installed LLM software and offer to add it.
- Known limits: 14 questions can't reliably separate the top models (*unverified*: more questions would); the off-topic gate (#53) is checked on the hash embedder only until the real-embedder re-run below; the snapshot doesn't move, so "overdue" counts against 2026-10-13.

## Waiting on the owner

1. Review and merge [PR #24](https://github.com/DerykHopley/tc-patch-security/pull/24) (spec A into `main`). The PR closes the spec A tickets.
2. Triage the follow-ups above and B25 ([#64](https://github.com/DerykHopley/tc-patch-security/issues/64)).
3. Re-run the retrieval check on the real embedders for the off-topic gate (#53; needs OpenRouter and Ollama). In `backend/`, per embedder whose index you have: `EMBEDDER=openrouter INDEX_PATH=data/index-openrouter uv run --env-file .env python -m app.evals retrieval`, and `EMBEDDER=ollama EMBED_MODEL=<model> INDEX_PATH=<its index folder> uv run --env-file .env python -m app.evals retrieval`. Hit rate and MRR should match the A20 runs; the "Off-topic gate" line should say 0 on-topic questions gated and, ideally, 15 of 15 off-topic.
4. Create the Clerk instance ([#65](https://github.com/DerykHopley/tc-patch-security/issues/65)), then deploy to Cloud Run by [DEPLOY.md](./DEPLOY.md) ([#45](https://github.com/DerykHopley/tc-patch-security/issues/45)).

## What spec B adds

[Spec B (#31)](https://github.com/DerykHopley/tc-patch-security/issues/31): the buffer week, from the merge of spec A to 2026-11-02. Every part is a stretch course task, so any one can slip; spec A already meets the minimum.

- **Live refresh:** shared build code for the snapshot and the live data (B01 #32), live mode and "Check now" (B02 #35), real feeds from NVD, KEV, EPSS and OSV on a schedule (B03 #36), one logged real run (B07 #40, human), pause and run history (B19 #59).
- **Alerts:** rules, de-duplication, digests, delivery and an alerts panel (B04 #37); "new since last check" on the CVEs page (B05 #38); `check_updates` in the chat (B06 #39).
- **Web research** through Tavily's remote MCP server (B08 #33), ending in a proposed decision you approve (B22 #62).
- **Deployment and users:** per-user state (B09 #41), Clerk sign-in (B10 #42), rate limits (B11 #43), a container image (B12 #34), Cloud Run (B13 #44, B14 #45 human), an outside user tries it (B18 #60).
- **Chat:** model-check questions for the new tools (B15 #46) and a real-model run of them (B16 #47, human); partial success and retry (B20 #57); proposed changes you preview and approve (B21 #58); Patch as an MCP server (B23 #61); next-step buttons on tool cards (B24 #63).
- **Docs:** README and STATUS for spec B (B17 #48).
- **Experiment:** grade the text-matched CVEs with Jev (B25 #64, needs triage). Background: [docs/research/openrouter-alphadecisions.md](./docs/research/openrouter-alphadecisions.md).

## The prototype (`proto/`)

- Frozen on 2026-10-13. It was the reference the real build was checked against: same snapshot, FakeLLM, the first dashboard, settings, dev panel and model check.
- Not run in CI and not changed any more. Its spec and layout: [proto/SPEC.md](./proto/SPEC.md) (check ids, frozen as history), [proto/PLAN.md](./proto/PLAN.md).
- To run it anyway: `cd proto/backend && uv run uvicorn app.main:app --port 8000` and `cd proto/frontend && npm run dev`. It uses the same ports as the real build: stop one first.

## Related projects

- ai-digest (`../../ai-digest/`), the owner's own AI-news project, shares techniques with this one. Linking back is optional; the course project comes first. What maps where, and the earlier experiments in `../../tc-ai-experiments/` with their lessons: [AI-DIGEST-OVERLAP.md](./AI-DIGEST-OVERLAP.md).

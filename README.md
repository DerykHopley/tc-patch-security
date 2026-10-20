# Patch: an LLM-security assistant

A security assistant for people who build LLM apps. Ask Patch about a risk, an attack or a CVE, and get an answer that cites its sources. A dashboard tracks the CVEs in the LLM products you use, says which ones affect your versions, and ranks what to fix first by rules you set.

Built for the Turing College sprint 2 project: a RAG assistant that rewrites questions before searching, turns them into checked filters, calls tools, and runs in the browser.

![The dashboard, filtered to Langflow and Open WebUI](docs/media/dashboard-light.png)

> **Status (2026-10-20): spec B is built** on the `spec-b` branch and waits to merge into `main` in [PR #66](https://github.com/DerykHopley/tc-patch-security/pull/66). Spec A is merged ([PR #24](https://github.com/DerykHopley/tc-patch-security/pull/24)). Patch now runs on live data, sends alerts, researches the web, signs people in, and is deployed: **https://patch-976248543439.europe-west1.run.app** ([try it live](#try-it-live)). Details: [STATUS.md](./STATUS.md).

## Try it live

Patch runs on Google Cloud Run at **https://patch-976248543439.europe-west1.run.app**. Anyone can make an account; the owner approves each one before it can use the app (why: [DECISIONS.md](./DECISIONS.md), B38).

1. Open the address. The first visit after a quiet spell can take a minute or two: the server sleeps when nobody uses it, and the page says "Waking Patch up…" while it starts (one cold start took about 90 s on 2026-10-20, *checked* in the logs; [DEPLOY.md](./DEPLOY.md#8-the-hourly-schedule)).
2. Press **Request access** and make an account: email and password, or Google or Discord.
3. Press **Send request**. Add a short note if you like (who you are, e.g. "Turing College reviewer"; at most 280 characters).
4. Wait for the owner. They get one alert per request and approve it on Settings → Requests, by hand, so it can take a while. Patch sends no email: load the page again later.
5. Once approved you get your own copy of the default watchlist, the dashboard, the CVEs and the chat. Nothing you do changes anyone else's view.

- **What runs there** (*checked* 2026-10-20 on `/api/health`): live data, Claude Haiku 5.5 through OpenRouter, sign-in on. The data refreshes once a day at 08:00 Berlin time; anyone can also press **Check now** on the dashboard.
- **Limits per person:** 10 chat messages a minute and 200 a day; web research 30 searches a day for everyone together. These are the defaults in [backend/.env.example](./backend/.env.example); the live values aren't shown anywhere (*unverified*).
- **A link from an alert** (`/cves/CVE-…`) still opens the landing page first when you're signed out; after sign-in it lands on that CVE, not the dashboard (B60, [#107](https://github.com/DerykHopley/tc-patch-security/issues/107)).
- **Roles:** everyone starts as a Viewer (no Dev page). The owner can make you Trusted or Reviewer to see the Dev page ([Sign-in](#sign-in-clerk)).

## What it does

### The assistant (spec A)

- **Chat with Patch.** Retrieval over the knowledge base with query translation (multi-query rewrites, merged by reciprocal rank fusion) and structured retrieval (the model writes metadata filters; the server checks them against fixed lists). Search is hybrid: vectors plus our own BM25 keyword search. Answers cite numbered sources; a citation with no matching source is removed and listed.
- **Six tools:** `search_security`, `lookup_cve` (with KEV, verdict and priority), `explain_weakness` (CWE → OWASP category, ATLAS technique → mitigations), `check_affected` (am I affected, for your version), `prioritise` (what to fix first, from the rules) and `update_watchlist` (which only proposes: you approve, edit or cancel the change in a card). Every call shows as a card under the answer.
- **Am I affected?** You give each watched product a version and how you run it. OSV's affected and fixed versions give a verdict per CVE: affected, not affected or unknown, with the reason.
- **Priority by rules.** KEV, EPSS, severity, the verdict and an internet-facing switch give each open CVE a priority (urgent, high, normal, low) and a due date from your policy. Rules decide; Patch only explains them.
- **Dashboard and CVEs page.** Tiles, charts and the top 5 open CVEs, filtered by product. The CVEs page lists every CVE on your watchlist with filters in the URL. Each status change (fixed, not affected, accepted) goes through a dialog and into a history; not affected needs a justification, accepted a reason and a review date.
- **Explain levels:** simple, normal or deep dive, set in Settings or per question.
- **Page-aware chat:** "What should I fix first?" means the view you're looking at.
- **Token usage and cost** under every answer: tokens in and out, LLM calls, steps, and dollars (from OpenRouter's reported cost).
- **Dev page:** switch the model at runtime (FakeLLM, OpenRouter, or a local OpenAI-compatible server such as Ollama), tune search, watch each retrieval step in a playground, see the index on an embedding map, and run the model check.
### What spec B added

[Spec B (#31)](https://github.com/DerykHopley/tc-patch-security/issues/31) took Patch off the frozen snapshot and onto a public address. Each part, with its ticket ids; the full list is in [STATUS.md](./STATUS.md#whats-built).

- **Live data and Check now** (B02, B03, B28, B59). Live mode pulls what changed from NVD, CISA KEV, EPSS and OSV.dev and makes the new CVEs searchable straight away. It runs on a schedule (a systemd timer locally, Cloud Scheduler on the live app), from **Check now**, or when you ask Patch "anything new since Monday?" (`check_updates`). Check now is on the dashboard's Data freshness card, for everyone, and on Settings → Refresh runs, for the owner, above the run history ([#103](https://github.com/DerykHopley/tc-patch-security/issues/103)). How: [Live data](#live-data-from-the-real-feeds-on-a-schedule).
- **Alerts** (B04, B34, B41, B55, B57). After each refresh, by your rules: a watched CVE added to KEV, a new CVE at your minimum severity, a rescore to critical, a due date in 3 days, an overdue reminder once a week. Once per CVE and reason, many at once as one digest, held in quiet hours, a failed send tried again. Channels: desktop, email, ntfy and Telegram ([#102](https://github.com/DerykHopley/tc-patch-security/issues/102)). Everyone sees Recent alerts and the "New" chip in Patch; only the owner's alerts go to the channels. How: [Alerts](#alerts).
- **Web research** (B08, B22, B63, B64). Patch's `research_web` tool asks Tavily's hosted MCP server. Web results are cited as "Web result, unverified", passed to the model as untrusted data, and a page that tries to give instructions is flagged and ignored. Exploit sites are dropped. A research question can end in a decision Patch proposes and you approve. How: [Web research](#web-research-tavily).
- **Changes you approve** (B21, B24). Patch never changes your data by itself: it proposes, and a card shows the change with Approve, Edit and Cancel. Buttons on tool cards do the next step (Open in CVEs page, Watch this product, Set my version…).
- **A page per CVE** (B35): `/cves/CVE-…`, with the summary, your assessment, the actions and the decision history.
- **Sign-in and your own data** (B09, B10, B38, B45, B48, B60). Clerk sign-in. Open sign-up, each account approved by the owner, with roles. Each person has their own watchlist, statuses, decisions and settings. Patch stores no names or emails. How: [Sign-in](#sign-in-clerk).
- **Rate limits** (B11): chat messages per person per minute and per day, a daily web-research cap, one refresh at a time, and a plain note with a retry time.
- **Deployed** (B12, B13, B14): one container on Google Cloud Run in Belgium, state in Cloud Storage, keys in Secret Manager, at no cost so far. How: [On Google Cloud Run](#on-google-cloud-run).
- **Patch as an MCP server** (B23): four read-only tools for Claude Code or Claude Desktop. [Try it in 5 minutes](#try-it-in-5-minutes).
- **A landing page** (B42, [#80](https://github.com/DerykHopley/tc-patch-security/issues/80)). A visitor who isn't signed in first sees what Patch is, the problem it solves and three screenshots in their theme, then **Sign in** or **Request access**. Inside the app it is the **About** page (`/about`). It has a 20-second launch video, light or dark to match (B47, [#99](https://github.com/DerykHopley/tc-patch-security/issues/99); [how it was built](#how-the-launch-video-was-built)). Its screenshots are taken from the app on example data by `scripts/landing-shots.sh` ([how](./docs/design/DESIGN.md#516-the-landing-page-b42-80-2026-10-19)).
- **Link previews** (B61, [#108](https://github.com/DerykHopley/tc-patch-security/issues/108)). A link to `/` or `/about` pasted into a chat app shows a card with Patch's name, a line about it and an image. The server adds the tags only when `APP_URL` is a public https address (*checked* 2026-10-20: the live app's `/` carries them). How the card looks in Telegram and other apps is *unverified*; send the link to @WebpageBot first if Telegram cached an old preview.

### Screenshots

| The chat, pinned beside a CVE's page | Settings: your watchlist |
|---|---|
| ![Patch answering "Am I affected by CVE-2025-3248?" beside the CVE's page, with the check_affected tool card open](docs/media/chat-light.png) | ![The watchlist card in Settings: products, usage, version, internet-facing](docs/media/settings-light.png) |
| **The CVEs page** | **Dark mode** |
| ![The CVEs page with verdicts, priorities and due dates](docs/media/cves-light.png) | ![The dashboard in dark mode](docs/media/dashboard-dark.png) |

Spec B:

| Web research, with a flagged page | Check now and the alert channels on Settings |
|---|---|
| ![Patch's research_web tool card: three web results, each marked "Web result, unverified", one flagged "instructions ignored"](docs/media/web-research-light.png) | ![Settings: the Delivery card with desktop, email, ntfy and Telegram, and the Refresh runs card with Check now and its result](docs/media/check-now-settings-light.png) |
| **The dashboard after Check now** | **The landing page, as About** |
| ![The dashboard in live mode: Recent alerts lists three alerts, Data freshness shows Check now and "See the 2 new CVEs"](docs/media/check-now-dashboard-light.png) | ![The About page: "Security flaws in your LLM stack, tracked for you", the four tiles and the launch video](docs/media/landing-light.png) |

The "Open CVEs by product and severity" chart opening:

![The chart's bars growing in, one product at a time](docs/media/open-cves-chart.gif)

- Taken 2026-10-20 in Chromium, 1440 × 900, on the browser check's throwaway servers: FakeLLM, the example watchlist (Langflow 1.2.0, internet-facing; LiteLLM 1.80.0), sign-in off. The chart animation is from 2026-10-15.
- FakeLLM is a scripted stand-in, so the chat shows the app working, not a real model's wording. The web results come from a fake Tavily with canned pages, one of them an injection attempt.
- Check now ran on the made-up test feeds, so the dashboard warns "Live: the made-up test data, not the real feeds". On the real feeds that line names NVD, CISA KEV, EPSS and OSV.dev.

## What was proven: the model check

The [model-check report](https://derykhopley.github.io/tc-patch-security/) (on GitHub Pages) compares every model on the same scripted questions, with exact checks and no LLM judge. Run on 2026-10-15. All checked in the runs unless marked.

- **11 chat models:** 6 on OpenRouter, 5 local through Ollama 0.40.4 on an RX 7900 XTX. Each answered the same 14 questions (54 checks).
- **Best answers:** `anthropic/claude-haiku-5.5`, 12 of 14 questions, 51 of 54 checks, about 10 s and $0.0015 per question. It's the default OpenRouter model.
- **Best value:** `openai/gpt-6-luna`, one question behind at about a third of the cost.
- **Best local:** `qwen3.8:27b`, 11 of 14, 50 of 54 checks, free but about 25 s per answer.
- **4 embedders:** `mxbai-embed-large` (Ollama) is the default for real embeddings: hybrid hit rate at 5 of 0.82 and MRR 0.69, and the widest gap between on-topic and off-topic scores. Off-topic threshold 0.58.
- **Hybrid search beats vector search alone** for every embedder: hit rate at 5 up by 0.26 to 0.33.
- **Every model** got the rules' top 3 for "what should I fix first?", the right verdict for "am I affected?", flagged the injection question and wrote no exploit code.
- Most remaining failures are shared by nearly every model, so they point at our checks and tools. They're follow-up issues [#50](https://github.com/DerykHopley/tc-patch-security/issues/50)–[#54](https://github.com/DerykHopley/tc-patch-security/issues/54).
- Total spend for all runs: about $0.40. *Unverified:* summed from the run files, not checked against the OpenRouter bill.

The no-setup defaults stay FakeLLM and the hash embedder, so the app and every test run with no key and no service.

## Course tasks this build meets

The brief is course material and isn't in this repo. In our own words, the optional tasks each spec took on, and where to check each one.

### Spec A

| Task | What we built | Evidence |
|---|---|---|
| **Hybrid search** (hard) | Our own BM25 keyword search over the same chunks, with the same filters as the vector search, merged with Chroma's results by reciprocal rank fusion. The tokeniser keeps ids like `CVE-2024-8309` and `AML.T0051.001` whole, so exact ids and product names are found. | `backend/app/rag/keyword.py`, `fusion.py`, `pipeline.py`; tests `backend/tests/test_keyword.py`, `test_fusion.py`; the Dev page's playground shows the BM25 and vector lists before fusion; [report: Embedders side by side](https://derykhopley.github.io/tc-patch-security/#embedders) (hybrid against vector only, per embedder) |
| **Evaluation on real models** (hard) | A model check: scripted questions with exact checks (right tools, filters, key fact, real citations, flags, no exploit code, the rules' verdict and top 3, readability by level). A retrieval check: hit rate at 5 and MRR per embedder. A self-contained HTML report, built from saved runs and published. | `backend/app/evals/` (`model_check.py`, `checks.py`, `retrieval.py`, `report.py`); `docs/report-src/` (the runs shown, the findings); tests `backend/tests/test_model_check.py`, `test_report.py`, `test_retrieval_check.py`; [the published report](https://derykhopley.github.io/tc-patch-security/), section [Findings](https://derykhopley.github.io/tc-patch-security/#findings) |
| **Multi-model support** (medium) | One `LLM` seam with three providers: FakeLLM, OpenRouter, and any OpenAI-compatible server on this machine (Ollama, LM Studio, llama.cpp), through LangChain's `ChatOpenAI`. Switch at runtime on the Dev page. Three embedders the same way: hash, OpenRouter, Ollama. | `backend/app/llm/` (`providers.py`, `openai_compat.py`, `fake.py`), `backend/app/rag/embed.py`, `frontend/src/pages/DevPage.tsx`; tests `backend/tests/test_llm_openai.py`, `test_dev.py`, `frontend/e2e/test_dev.py`; [report: Models side by side](https://derykhopley.github.io/tc-patch-security/#models) (11 models) |
| **Prompt-injection protection** (medium) | Layers, not a blocklist. Injection phrasing in the user's message is flagged and logged, never blocked (asking about attacks is the point here). Retrieved text and tool output reach the model wrapped and escaped as data. The model's search filters and the page context are checked against fixed lists; anything else is dropped and listed. Tools are narrow, and status changes need the user's yes. | `backend/app/guard.py`, `page_context.py`, `chat_turn.py`; [CODING_STANDARDS.md](./CODING_STANDARDS.md) (Safety); tests `backend/tests/test_guard.py`, `test_chat_turn.py`, `frontend/e2e/test_chat.py` (the flag notice); report: every model flagged the injection question and wrote no exploit ([Pass or fail](https://derykhopley.github.io/tc-patch-security/#grid), Q6 and Q8) |
| **Token usage and cost** (medium) | Every answer shows tokens in and out, LLM calls, steps and the cost in dollars, summed over all the answer's model calls. The cost is OpenRouter's own `usage.cost`; local models and FakeLLM cost $0. The model check adds cost and time per question and per run. | `backend/app/llm/openai_compat.py`, `backend/app/tools/registry.py` (summing), `frontend/src/chat/Conversation.tsx` (the usage line); tests `backend/tests/test_llm_openai.py`, `test_citations.py`, `frontend/e2e/test_citations.py`; the usage line in [the chat screenshot](docs/media/chat-light.png); [report: At a glance](https://derykhopley.github.io/tc-patch-security/#glance) (quality against cost and time) |
| **Tool-result visualisation** (medium) | Each tool call is a card under the answer: the tool, its arguments, time, and the result drawn for its kind (a CVE card with severity, priority, verdict and EPSS; an OWASP or ATLAS card; a watchlist change), plus the raw result. Errors show in red. Each tool declares its result shape; the frontend's types are generated from it. | `frontend/src/chat/ToolCallCard.tsx`, `frontend/src/toolResults.ts` (generated), `backend/app/tools/registry.py`; tests `backend/tests/test_tool_results.py`, `frontend/e2e/test_chat.py` (A06.6); [the chat screenshot](docs/media/chat-light.png) |

The core of the brief is covered too: RAG over a domain knowledge base, query translation, structured retrieval, six tools, input validation and error handling, and a web UI with sources, tool calls and progress.

### Spec B

The stretch tasks [spec B (#31)](https://github.com/DerykHopley/tc-patch-security/issues/31) took on. Each was a stretch, so any could slip; none did.

| Task | What we built | Evidence |
|---|---|---|
| **Live updates to the knowledge base** (medium) | Live mode: a refresh pulls what changed from NVD, CISA KEV, EPSS and OSV.dev, builds the CVEs with the same code as the snapshot, and embeds the changed ones, so Patch can answer about a CVE published this morning. A failed fetch leaves the last good data. Started by Check now, the schedule, or Patch's `check_updates`. | `backend/app/refresh.py`, `feeds.py`, `live_data.py`, `cve_build.py`, `deps.py` `load_index`; tests `backend/tests/test_refresh.py`, `test_feeds.py`, `test_check_updates.py`, `frontend/e2e/test_live.py`, `test_check_now_settings.py`; [STATUS: the real live run](./STATUS.md#the-real-live-run-b07-2026-10-16) |
| **Knowledge base updated on its own** (hard) | The refresh runs on a schedule with nobody pressing anything: a systemd user timer locally, a Cloud Scheduler job on the live app (daily). Settings sets how often (1 to 24 hours) or pauses it. After each run, alerts by your rules. | `deploy/systemd/`, `refresh.py` `run_scheduled`, `scheduled_tick`, `main.py` (`POST /refresh/scheduled`); [DEPLOY.md step 8](./DEPLOY.md#8-the-hourly-schedule); tests `test_refresh.py`, `test_deploy.py`, `test_pause_history.py`, `test_alerts.py`; [STATUS: the live app](./STATUS.md#the-live-app); a real alert on the owner's phone ([screenshot](docs/media/live-run/phone-overdue-digest.png)) |
| **Tools from a public remote MCP server** (medium) | `research_web` calls Tavily's hosted MCP server through LangChain's MCP adapter, with the key in a header and Tavily's plain API as the fallback. Its results go through the same guard as every tool's output. | `backend/app/web_research.py`; tests `backend/tests/test_research_web.py` (against `fake_tavily.py`), `frontend/e2e/test_research_web.py`; [docs/mcp-demo.md, Record 3](./docs/mcp-demo.md#record-3-the-research-workflow-b22) (a real run on 2026-10-20); [report: spec B's run](https://derykhopley.github.io/tc-patch-security/#findings) (Q-web, Q-research) |
| **Our tools as an MCP server** (hard) | `python -m app.mcp_server`: four of Patch's tools, read-only, over stdio, for Claude Code or Claude Desktop. It reads nobody's watchlist. | `backend/app/mcp_server.py`; tests `backend/tests/test_mcp_server.py`; [docs/mcp-demo.md, Transcript 2](./docs/mcp-demo.md#transcript-2-a-real-client) (Claude Code, 2026-10-20); [Try it in 5 minutes](#try-it-in-5-minutes) |
| **Sign-in and personal data** (medium) | Clerk sign-in; open sign-up, each account approved by the owner, with roles. Each person has their own watchlist, statuses, decision records, settings, explain level and alerts, kept per user in Cloud Storage. Patch stores only the Clerk user id. | `backend/app/auth.py`, `access.py`, `store.py`, `users.py`, `profile.py`; `frontend/src/auth/`; tests `backend/tests/test_auth.py`, `test_access.py`, `test_roles.py`, `test_per_user.py`, `frontend/e2e/test_access_gate.py`, `test_roles.py`; [the live app](#try-it-live) |
| **Rate limits and key handling** (medium) | Chat messages per person per minute and per day, with one 429 form and a retry time; a daily web-research cap; one refresh at a time, at most one every 5 minutes; OpenRouter's spending cap as a plain 402. Keys live only in `backend/.env` or Secret Manager; secrets saved on Settings are write-only and never logged; the scheduled route needs its own secret. | `backend/app/rate_limits.py`, `web_research.py`, `server_settings.py`, `notify.py`; tests `backend/tests/test_rate_limits.py`, `test_settings_over_env.py`, `test_telegram.py` (the token never leaves), `frontend/e2e/test_rate_limits.py`; [DEPLOY.md step 4](./DEPLOY.md#4-the-secrets) |

Not claimed: logging and monitoring. The server logs its own lines (B54) and Settings shows the refresh runs and the alerts log, but there is no monitoring beyond Cloud Run's own.

## Run it

Needs Python 3.12+ with [uv](https://docs.astral.sh/uv/), and Node.js with npm. All commands start in the repo root.

To work on the code, turn on the pre-commit hook once per clone: `git config core.hooksPath .githooks`. It refuses a commit with staged conflict markers or a browser-check wait without a reason, in under a second. CI runs the same checks, so the hook only finds them sooner.

### With no key (FakeLLM)

FakeLLM is a scripted stand-in model, and the hash embedder matches words. No key, no network, no GPU.

```bash
cd backend && uv sync && uv run uvicorn app.main:app --reload --port 8000   # state in backend/data/state.json
cd frontend && npm install && npm run dev                                    # http://localhost:5173
```

### With OpenRouter, no GPU

A real chat model and real embeddings, both through OpenRouter. Set a spending cap on the key in OpenRouter's settings.

1. Copy the settings file. `.env` is git-ignored; never commit it.

   ```bash
   cd backend && cp .env.example .env
   ```

2. In `backend/.env`, set:

   ```bash
   LLM_PROVIDER=openrouter
   OPENROUTER_API_KEY=sk-or-...          # your key
   EMBEDDER=openrouter                   # openai/text-embedding-3-small
   INDEX_PATH=data/index-openrouter      # its own index folder, so the free hash index can stay
   ```

   The chat model defaults to `anthropic/claude-haiku-5.5`; change it with `OPENROUTER_MODEL`.

3. Build the search index once. It embeds 1,680 chunks: a paid call, well under a cent.

   ```bash
   uv sync && uv run --env-file .env python -m app.rag.build_index
   ```

4. Start the backend with the settings file, and the frontend as above.

   ```bash
   uv run --env-file .env uvicorn app.main:app --reload --port 8000
   ```

- A missing key, or an index built with another embedder, stops the start-up with a plain message saying what to do.
- Every setting is listed and explained in [backend/.env.example](./backend/.env.example).

### Which settings live where

Since B26 ([#70](https://github.com/DerykHopley/tc-patch-security/issues/70)), what can change while the app runs is set on **Settings**, by the owner; the rest stays in `backend/.env`.

- **On Settings (the owner only):** live or snapshot data and the NVD key (Data card); the quiet hours' time zone (Alerts card); the app address for alert links, the ntfy server, topic and token, the Telegram bot token and chat id, and the email (SMTP) details (Delivery card). They apply when you save, with no restart, and the refresh command line uses them too.
- **Secrets on Settings are write-only:** the boxes are masked, the app never sends a saved one back (it says only "Saved" or "Not set"), and **Remove** deletes it. They are kept in the owner's state: `backend/data/state.json` locally (git-ignored), the private bucket when deployed. Start over (the reset on Settings) keeps them.
- **`.env` still wins:** a setting set in `backend/.env` is used, and Settings shows it read-only as "set in the server's environment". To manage one on Settings, delete its line from `.env` and restart once.
- **Stays in `.env` only:** what the app needs before it can read Settings, or what could lock you out if set wrong from a page: `AUTH`, the Clerk keys, `AUTH_ALLOWED_ORIGINS`, `OWNER`, `STORE`/`GCS_BUCKET`, `CORS_ORIGINS`, the paths (`LIVE_PATH`, `INDEX_PATH`, `STATE_PATH`), `SCHEDULER_SECRET`, the model and embedder settings, and the test switches (`FEEDS=fake`, `NOTIFY_DRY_RUN`).
- **The settings behind Settings' words** (B50: the pages say them in words, the names are here):
  - "Set in the server's environment, which wins" under a field: that field's variable is set in `backend/.env` (for example `DATA_MODE`, `ALERT_TZ`, `APP_URL`, `NTFY_TOPIC`, `NVD_API_KEY`). The full list with each one's meaning is [backend/.env.example](./backend/.env.example).
  - **Desktop notification** needs `notify-send` (Linux, from libnotify) or `osascript` (macOS) on the computer running the backend. Settings says "can't show desktop notifications" without one.
  - **Email (SMTP)** needs the mail server and the address to send to: on Settings, or `SMTP_HOST` and `ALERT_EMAIL_TO` (plus `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `ALERT_EMAIL_FROM`, `SMTP_STARTTLS`) in `.env`.
  - **Phone push (ntfy)** needs a topic: on Settings, or `NTFY_TOPIC` (and `NTFY_URL`, `NTFY_TOKEN`) in `.env`.
  - **Telegram** needs the bot token and the chat id: on Settings, or `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `.env` ([Alerts](#alerts)).
  - "Live: the made-up test data, not the real feeds": the backend runs with `FEEDS=fake`. Remove it (the default is `FEEDS=real`) and restart.
  - The Dev page: `DEV_PANEL=false` turns it off for everyone (on by default); with sign-in on, the role you give each person decides who else sees it.
- **Tapping a phone alert:** while the app address is `localhost` (or `127.*`, `::1`, `0.0.0.0`), a phone can't open it, so alerts carry no link and a tap opens the message in the ntfy app (a Telegram message has no Open in Patch button). Set a LAN, Tailscale or Cloud Run address and a tap opens Patch at the CVE. A test alert from Settings says which happens.

### Alerts

The owner's alerts go to the channels ticked on Settings → Delivery: the desktop, email, ntfy and Telegram. Everyone else's stay in Patch. No alert ever holds the CVE description (untrusted text, and it shows on a lock screen).

- **ntfy** works well from your own computer. From Cloud Run it fails by the afternoon: ntfy.sh counts its daily quota per IP address, and Cloud Run's addresses are shared ([source checks](./docs/SOURCE-CHECKS.md#ntfysh-from-cloud-run-101-2026-10-19)).
- **Telegram** (B57, [#102](https://github.com/DerykHopley/tc-patch-security/issues/102)) is limited per bot, not per address, and free. Use it for the live app. High and urgent alerts ring; low and normal arrive silently. A tap on **Open in Patch** opens the CVE.

**Set up Telegram once** (the same steps are on the Settings card; checked against Telegram's docs, not yet against a real bot):

1. In Telegram, open **@BotFather**, send `/newbot`, and pick a name and a username (it must end in `bot`). BotFather replies with the bot's **token**, like `110201543:AAH…`. Anyone with it controls your bot: keep it secret. `/token` in BotFather makes a new one if it leaks.
2. Open your new bot in Telegram (BotFather links it) and press **Start**, or send it any message. That message is how Patch finds your chat (and, *unverified*, a bot may not write to someone who never started it).
3. On Patch, Settings → Delivery → **Telegram**: paste the token under Bot token, then press **Find my chat id**. Patch asks Telegram for the bot's recent messages and fills in your chat's id. Telegram keeps those messages 24 hours, so do step 2 within a day.
   By hand instead: open `https://api.telegram.org/bot<TOKEN>/getUpdates` in a browser and read `message.chat.id` (it puts the token in your browser history).
4. Save, tick Telegram, and press **Send test**. The message arrives in your chat.

Locally the token and chat id can also go in `backend/.env` (`TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`); there they win over Settings. On Cloud Run the token is a secret (`telegram-bot-token`) and the chat id a plain setting: `scripts/update-deploy.sh` adds both ([DEPLOY.md](./DEPLOY.md)).

### Web research (Tavily)

Patch's `research_web` tool searches the web through Tavily's hosted MCP server (B08, [#33](https://github.com/DerykHopley/tc-patch-security/issues/33)). It's off until you give it a key. Why it's built this way: [DECISIONS.md](./DECISIONS.md) (the B08, B63 and B64 rows).

- **Turn it on:** a free key from tavily.com, as `TAVILY_API_KEY=tvly-…` in `backend/.env`, then start with `--env-file .env`. Without the key Patch isn't offered the tool. Deployed, the key is the `tavily-api-key` secret ([DEPLOY.md step 4](./DEPLOY.md#4-the-secrets)).
- **Try it:** ask "Who's talking about CVE-2025-3248 on the web?". The answer's Tool calls tab shows the `research_web` card: the query, each result marked "Web result, unverified", and "via Tavily's MCP server" (or "via Tavily's search API" when the MCP server didn't answer).
- **Cost:** Tavily's free plan gives 1,000 credits a month; a basic search costs 1 (*checked*, [docs/SOURCE-CHECKS.md](./docs/SOURCE-CHECKS.md#tavily)). Patch caps it at 30 searches a day for everyone together and 30 per person (`WEB_RESEARCH_DAILY_CAP`, `WEB_RESEARCH_USER_DAILY_CAP`), so the credits last the month.
- **What Tavily sees:** only the search query Patch writes, never your watchlist or the page you're on. The key goes in a header, never in the URL, and is never logged.
- **Safety:** web pages are untrusted text. They reach the model wrapped as data; a page that tries to give instructions is flagged ("Flagged: instructions ignored") and not followed. Patch asks for 8 results, drops 9 known exploit and proof-of-concept sites itself, and keeps at most 5.
- **Two fixes from the real demo on 2026-10-20** ([docs/mcp-demo.md, Record 3](./docs/mcp-demo.md#record-3-the-research-workflow-b22)):
  - B63: Tavily's MCP server now answers in JSON. Patch read that as 0 results, silently, so every web search came back empty, on the live app too. It reads both layouts now, and a reply it can't read falls back to the plain API.
  - B64: sending the exploit sites as Tavily's `exclude_domains` made it return unrelated Microsoft pages, every try. Patch now drops those sites itself, which it already did as a second check.
- **Tavily's terms** allow use "for internal business purposes" only, and no automated decisions without human oversight ([docs/SOURCE-CHECKS.md](./docs/SOURCE-CHECKS.md#tavily)). Patch fits the second: a research answer can only propose a decision, and you approve it. A course project with a few approved users is, we think, inside the first (*unverified*: not asked of Tavily).

### Sign-in (Clerk)

Off locally and in the tests (`AUTH=off`): one default user, no sign-in, no requests; the landing page is only the About page. On (`AUTH=on`, the Clerk keys in `backend/.env`: [#65](https://github.com/DerykHopley/tc-patch-security/issues/65)), a signed-out visitor first sees the landing page at any address (the form is at `/sign-in`), anyone can make an account (email and password, or an SSO provider such as Google or Discord), and **the owner approves each new account in Patch** before it can use the app (B38, [#81](https://github.com/DerykHopley/tc-patch-security/issues/81)). Every sign-in and sign-up step stays on Patch's page, never Clerk's hosted pages. Why, and what's checked: [DECISIONS.md](./DECISIONS.md) (B31, B38), [docs/SOURCE-CHECKS.md](./docs/SOURCE-CHECKS.md) (Clerk, B31 and B38).

- **Deep links survive sign-in** (B60, [#107](https://github.com/DerykHopley/tc-patch-security/issues/107)). A signed-out visitor who opens an in-app address, such as an alert's `/cves/CVE-…`, still sees the landing page, then the form. After signing in (or signing up and being approved) they land on that address once, not on the dashboard. Only paths on Patch's own site are kept, so the link can't send anyone elsewhere. *Unverified:* the round trip on the real Clerk instance and on a phone (checked in Clerk's code and the browser check only).
- **A new account asks.** After signing up, a person sees only "Ask to join Patch", with an optional note for you (at most 280 characters). Then "Your request is waiting for the owner". The API refuses them everything else (403) until you approve.
- **You get one alert per request** on the channels you ticked on Settings (e.g. ntfy or Telegram): "New access request", "From <name>" (the name Clerk has for them, asked with `CLERK_SECRET_KEY`; without the key, their user id), and "(with a note)" if there is one. The note's text never goes in the alert: a stranger's words stay off your lock screen. Tapping it opens Settings at the Requests card (when the app address is reachable from your phone).
- **The Requests card on Settings** (only you see it): everyone who asked, with Approve, Refuse, Undo refusal and Remove. A refusal is final until you undo it: that person can't ask again, so you get at most one alert per account. Remove forgets the request and its note; they can ask again. Approved people get the app the next time they load Patch; Patch sends them no email.
- **Roles** (B45, [#90](https://github.com/DerykHopley/tc-patch-security/issues/90)): next to Approve you pick a role, and you can change it later with Save role. **Viewer** (the default, and for everyone approved before roles): the dashboard, the CVEs, the chat and their own watchlist, no Dev page. **Trusted**: also the Dev page read-only and the search playground. **Reviewer**: also changes the Dev settings, but only their own copy (their chat and playground use it; everyone else keeps yours), with "Back to the owner's settings" to drop it. Only you run the model check and see the Requests card and the server settings. You are `OWNER` in `.env`, never a stored role, so nobody can lock you out or make themselves owner from inside the app. A change applies on the person's next page load, no sign-out needed. Why: [DECISIONS.md](./DECISIONS.md) (B45).
- **What Patch stores:** each person's Clerk user id, their status and role, when and by whom it changed, and the note. No names or emails: the card asks Clerk for those when it opens, with the Clerk secret key (`CLERK_SECRET_KEY` in `backend/.env`, optional; without it the card shows user ids). The key stays on the server.
- **People already using Patch** (signed in before, or with saved settings) were approved once, on the first start with this version: they were invited under the old invite-only setup.
- **Settings in two parts** (B48, [#97](https://github.com/DerykHopley/tc-patch-security/issues/97)). **Yours**, for everyone (you too): Profile, Connected accounts, the watchlist, alerts, Patch's answers, priority and due dates, and Start over (it deletes your own data, decision history included, and says so; B50). **This Patch**, yours only: Requests (first), Refresh runs, Delivery and Data, with the server settings. Everyone else's alerts show in Patch only (Recent alerts, the New badge): no channels, no quiet hours, and one line with your schedule.
- **Anonymous by default** (B48, #77). Patch reads only the user id from Clerk's session token, never a name or email, so you don't need any custom session claims. Anyone can give Patch a display name on Settings → Profile (optional): only their user menu shows it; nobody else sees it. Decision records always say "you" (B50; records made between B48 and B50 keep the name they hold). Start over keeps it.
- **Connected accounts on Settings** (everyone signed in, under Profile): link Google or Discord to the account you're in, so signing in with them lands in the same account even when their email differs. You can unlink one, never the last way to sign in.
- **Your state comes along.** On the first start with sign-in on, the owner (`OWNER`) gets a copy of what you set up with sign-in off (live mode, Settings, the watchlist, alerts), if the owner has nothing saved yet. It never runs again and never overwrites; the default user's state stays as it was.

**The owner's Clerk dashboard steps** (https://dashboard.clerk.com, the Patch application; menu names *unverified* where marked):

1. **SSO connections** (under User & authentication; *unverified*): add the providers you want (the free plan allows 3), e.g. Google and Discord. On a development instance Clerk offers its own shared credentials for them (*unverified* for each provider).
2. **Restrictions → Access mode: Open** (the dashboard's name, *checked* by the owner 2026-10-20; it was Restricted for invitations). Leave the allowlist off.
3. **Protect → Protections → "Challenge suspicious sign-ups": Enabled.** Clerk's bot protection, on every plan, the free one too; on by default for new applications. Patch's sign-up form shows its challenge when Clerk asks for one. If the row says "Setup required", follow it.
4. **Optional: the secret key** (API keys) as `CLERK_SECRET_KEY` in `backend/.env`, for names and emails on the Requests card.
5. **Your own SSO login:** sign in as you, then Settings → Connected accounts → Link Discord (or Google). Afterwards signing in with Discord lands in your own account, as `OWNER`. If Discord was already used to make a separate Clerk account, delete that account in the dashboard's Users page first (*unverified* what Clerk says otherwise).

### Optional: local models through Ollama

Free, and nothing leaves the machine. Needs a GPU for useful speed. The report's local runs used Ollama 0.40.4 on an RX 7900 XTX (24 GB).

```bash
ollama pull qwen3.8:27b         # the best local chat model in the report; gpt-oss:20b is faster
ollama pull mxbai-embed-large   # the default embedder for real embeddings
```

In `backend/.env`: `LLM_PROVIDER=local`, `LOCAL_LLM_MODEL=qwen3.8:27b`, `EMBEDDER=ollama`, `INDEX_PATH=data/index-ollama`. Then build the index and start as above. The local URL must be on this machine (`LOCAL_LLM_URL`, default Ollama's `http://localhost:11434/v1`). You can also switch models at runtime on the Dev page.

### Live data from the real feeds, on a schedule

By default the app runs on the frozen snapshot. Live mode refreshes the CVE data from NVD, the CISA KEV catalogue, EPSS and OSV.dev (spec B, [#36](https://github.com/DerykHopley/tc-patch-security/issues/36)). No key is needed. Switch it on in Settings, Data card (Live, then Save changes). The real feeds are the default (`FEEDS=real`, B28): the Data card says "Live: NVD, CISA KEV, EPSS and OSV.dev". `FEEDS=fake` is for tests and demos only (made-up CVEs, made-up alerts); with it the Data card and the dashboard's freshness card warn "Live: the made-up test data, not the real feeds".

- The optional NVD key (50 requests per 30 s instead of 5; only matters after a long gap) is on the same card. `DATA_MODE=live` and `NVD_API_KEY` in `.env` still work, and win.

- **Check now** runs a refresh. It is in two places: the dashboard's Data freshness card, for everyone, and Settings → Refresh runs, for the owner, above the list of runs (B59). So does the command line: `cd backend && uv run --env-file .env python -m app.refresh`.
- **The schedule:** an hourly systemd user timer runs `python -m app.refresh --schedule`. That run skips (and fetches nothing) until the Settings schedule (every 1, 3, 6, 12 or 24 hours) has passed since the last check, so Settings controls the schedule without touching the timer. Install it from the repo root:

  ```bash
  deploy/systemd/install.sh                          # writes the two units to ~/.config/systemd/user/, reloads systemd
  systemctl --user enable --now patch-refresh.timer  # start the hourly timer
  systemctl --user list-timers patch-refresh.timer   # when it fires next
  journalctl --user -u patch-refresh.service -n 30   # what the last run did
  ```

  The units are in [deploy/systemd/](./deploy/systemd/). For the timer to run while you're logged out: `loginctl enable-linger`.
- A failed fetch (a service down, a timeout, a rate limit) stops the run before anything is written: the data and the last-checked time stay as they were, and the next run covers the gap. The error is in the run log (`GET /refresh`) and the journal.
- The first live start copies the snapshot; the first refresh then fetches everything NVD changed since 2026-10-13, in windows of at most 120 days.
- **One kind of data per live folder.** Each refresh records which feeds wrote the live data. A start, the CLI or the Settings switch on a folder the other kind wrote stops with a message naming the folder: move it aside (e.g. `mv data/live data/live-fake`) or set `LIVE_PATH` to a fresh folder, and the next start copies the snapshot in. A folder from before B28 has no record: it is accepted, and its next refresh records the kind.
- In snapshot mode a scheduled tick skips ("skipped: the data is the frozen snapshot", exit 0), so the timer's unit doesn't show as failed. `python -m app.refresh` by hand still exits 2.

### In a container

One image runs the whole app on one port: the API (under `/api`) and the built frontend, with the search index built in. Needs Docker. Build the index first, then the image, from the repo root:

```bash
(cd backend && EMBEDDER=hash INDEX_PATH=data/index-image uv run python -m app.rag.build_index)   # free, no key
docker build -t patch .
docker run --rm -p 8080:8080 patch                       # http://localhost:8080, FakeLLM
docker run --rm -p 8080:8080 --env-file backend/.env patch   # with your settings (keys stay outside the image)
```

- No key or `.env` is in the image; settings come from environment variables at `docker run`.
- The image records the embedder its index was built with. For a real embedder, build its index into `backend/data/index-image` with that `EMBEDDER`, then pass it to the build: `docker build --build-arg EMBEDDER=ollama -t patch .`. Run the image with another embedder and it stops at start-up with the index-mismatch error. *Unverified:* only the hash index has been run in the image so far.
- Your state lives inside the container and goes when it's removed. Keep it with a volume: `-v patch-data:/app/backend/data`.
- In `--env-file backend/.env`, leave out `INDEX_PATH`, `STATE_PATH` and `FRONTEND_DIR`: the image sets them. A local URL such as Ollama's `localhost` means the container itself, not your machine.

### On Google Cloud Run

One container on Cloud Run, users' state and the live data in Cloud Storage, keys in Secret Manager, a Cloud Scheduler job, Clerk sign-in, at no cost at this use (B13, [#44](https://github.com/DerykHopley/tc-patch-security/issues/44)). The live app at https://patch-976248543439.europe-west1.run.app was deployed this way on 2026-10-19 (B14, [#45](https://github.com/DerykHopley/tc-patch-security/issues/45)): [STATUS.md](./STATUS.md#the-live-app).

- **First deploy:** `scripts/deploy-wizard.sh`, from the repo root. It walks through every step one at a time: it explains each, shows the command and asks before running it, skips what already exists, and never writes a secret to a file. The same steps by hand, copy-pasteable, with the costs against the free tiers: [DEPLOY.md](./DEPLOY.md).
- **Update after a change:** `scripts/update-deploy.sh`. It suggests the next version tag, rebuilds the search index only when needed, builds, pushes, deploys and checks it answers. It also offers the Telegram secret ([Alerts](#alerts)).
- **What you need:** a Google Cloud account with billing, the `gcloud` CLI, Docker, an OpenRouter key with a spending cap, the Clerk keys ([Sign-in](#sign-in-clerk)). Optional: a Tavily key, a Telegram bot.
- **Checked on the first deploy** (2026-10-19): the wizard's steps ran; three fixes went into the wizard and DEPLOY.md on the way (the billing account id, the budget in the account's currency, an empty time zone). The region is `europe-west1` (Belgium), not DEPLOY.md's example `us-central1`: why in [DEPLOY.md](./DEPLOY.md#what-runs-where).
- **Link previews** need `APP_URL` set to the public https address in `deploy/cloudrun/env.yaml` (the wizard fills it in). The image is made by `scripts/link-preview-image.sh` on throwaway servers.
- *Unverified:* the cost over a full week (expected $0; the owner checks around 2026-10-26, #45).

### As an MCP server for other assistants

Patch's knowledge can be used from another assistant, such as Claude Desktop or Claude Code, over MCP (B23, [#61](https://github.com/DerykHopley/tc-patch-security/issues/61)). The client starts the server itself, over stdio:

```bash
cd backend && uv run python -m app.mcp_server   # what the client runs; it waits for MCP messages on stdin
```

- **Four read-only tools:** `search_security`, `lookup_cve`, `explain_weakness` and `check_affected`. `check_affected` takes the version (and optionally the usage) in the call.
- **No one's stack is read or changed.** The server never reads your watchlist, statuses or decisions, and has no tool that changes anything. `lookup_cve` answers "not watched", with no priority.
- **Output is untrusted data,** wrapped as in the chat. Each result lists its sources with their URLs.
- `search_security` uses the chat model to translate the query. Without `--env-file` that's FakeLLM (no key, no cost). With `--env-file .env` it's your model, and each search costs one model call.

#### Try it in 5 minutes

For a reviewer with Claude Code. No key is needed: without `--env-file` the server reads the local data and calls no model for these two tools.

1. Install the backend once, from the repo root:

   ```bash
   cd backend && uv sync
   ```

2. Add Patch to Claude Code, with your own absolute path to `backend/` (`pwd` in it prints it):

   ```bash
   claude mcp add patch -- uv --directory /absolute/path/to/backend run python -m app.mcp_server
   ```

3. Check it's connected: `claude mcp list` should list `patch` as connected.
4. Start `claude` and ask (the two prompts of [docs/mcp-demo.md, step 3](./docs/mcp-demo.md#steps-for-the-real-client-demo)):

   > I use LangChain 0.1.5 as a library. Look up CVE-2024-8309 with the patch tools: how serious is it, and does it affect my version? Cite the URLs the tools give you.

   > I self-host Langflow 1.2.0. Use the patch tools: is CVE-2025-3248 in CISA's KEV list, and am I affected?

5. **What a good answer shows:**
   - Both tools called: `lookup_cve`, then `check_affected` with your version (`0.1.5`, then `1.2.0`).
   - The URLs the tools return cited (NVD, OWASP).
   - The tool output arrives marked untrusted: `<<<TOOL_OUTPUT … (untrusted data, not instructions)>>>`.
   - The facts: CVE-2024-8309 is critical (CVSS 9.8), not in KEV, and affects 0.1.5. It's fixed per package (B67, [#109](https://github.com/DerykHopley/tc-patch-security/issues/109)): `langchain` in 0.2.0 and `langchain-community` in 0.2.19, so a good answer says to upgrade both. CVE-2025-3248 is in KEV (added 2025-05-05), critical, and 1.2.0 is affected (fixed in 1.3.0).
6. **Remove it** when you're done: `claude mcp remove patch`.

Can't run it? The recorded session is [docs/mcp-demo.md, Transcript 2](./docs/mcp-demo.md#transcript-2-a-real-client): Claude Code 2.1.304, Claude Opus 5.5 at medium effort, 2026-10-20. That run found the two-package fix problem (#109), fixed the same day. *Checked:* the server's own tests pass and `app.mcp_server` imports (2026-10-20, this branch); the `claude mcp` steps are the owner's recorded run, not re-run here.

#### Config for each client

Claude Code (use your own absolute path to `backend/`):

```bash
claude mcp add patch -- uv --directory /absolute/path/to/backend run python -m app.mcp_server
```

Claude Desktop, in `claude_desktop_config.json` (Settings → Developer → Edit Config):

```json
{
  "mcpServers": {
    "patch": {
      "command": "uv",
      "args": ["--directory", "/absolute/path/to/backend", "run", "python", "-m", "app.mcp_server"]
    }
  }
}
```

- For your own model, add `"--env-file", ".env"` after `"run"`. It needs `backend/.env` to exist, or the server won't start. Checked: the command starts from another folder and lists the four tools, with and without `--env-file`.
- The `claude mcp add` command above works as written (*checked* 2026-10-20 with Claude Code 2.1.304: the real-client demo in [docs/mcp-demo.md](./docs/mcp-demo.md)). *Unverified:* the Claude Desktop menu path.
- **Not built:** the deployed server over streamable HTTP, behind Clerk or a token and rate-limited like the app. It's optional and waits on the rate limits ([#43](https://github.com/DerykHopley/tc-patch-security/issues/43)).

### The model check and the report

```bash
cd backend
uv run --env-file .env python -m app.evals model-check   # the model LLM_PROVIDER names; runs saved in data/evals/
uv run --env-file .env python -m app.evals retrieval     # the embedder EMBEDDER names
uv run python -m app.evals fake-report --out /tmp/report.html   # FakeLLM and fake embedders: no key, no network
uv run python -m app.evals --help
```

How the published report is rebuilt: [docs/report-src/README.md](./docs/report-src/README.md).

## Test it

The same checks CI runs ([.github/workflows/ci.yml](./.github/workflows/ci.yml)). No key, no network.

```bash
cd backend && uv run pytest                            # backend tests (prints its own count)
cd frontend && npx tsc -b && npm run lint && npm test  # types, lint (oxlint), unit tests (node --test)
python3 frontend/e2e/check_waits.py                    # no fixed wait in the browser check without a reason
frontend/e2e/run.sh                                    # browser check (Playwright), Firefox and Chromium
frontend/e2e/container.sh                              # builds the image and smoke-tests it (needs Docker)
```

- `frontend/e2e/run.sh` starts its own backend (FakeLLM, a throwaway state file and index) and frontend on two free ports, so it never touches an app on 8000/5173. Extra arguments go to pytest: `run.sh -k a02` still runs both browsers.
- Slow mode: `E2E_LATENCY_MS=300 frontend/e2e/run.sh` delays every API response, to find timing races before CI's slower runner does.
- `frontend/e2e/container.sh` builds the hash index and the image, starts it on a free port with FakeLLM, checks `/health`, the embedder check and that no `.env` got in, then runs a short browser check in Chromium (the dashboard loads, the chat answers). It removes its container and image afterwards.
- First time: `uv run --project frontend/e2e playwright install firefox chromium`.
- Review rules that lint can't check: [CODING_STANDARDS.md](./CODING_STANDARDS.md).

## Stack

- **Backend:** Python, FastAPI, Pydantic, Chroma (in-process, no server), LangChain only at the model seam (`langchain-openai`'s `ChatOpenAI`, [ADR 0001](./docs/adr/0001-thin-langchain.md)), `packaging` and `semver` for version checks.
- **Frontend:** React, TypeScript, Vite, plain SVG charts. Playwright for the browser check.
- **RAG, our own code:** section-aware chunking, BM25, reciprocal rank fusion, filter checks, the agent loop and the citation check. Why not LangChain's retrievers: `SelfQueryRetriever` would pass the model's filters to the store unchecked, and keeping each step our own keeps it explainable and testable.
- **Models:** OpenRouter, or a local OpenAI-compatible server; FakeLLM for tests.
- **Spec B's services:** Clerk for sign-in; Tavily's hosted MCP server for web research (through `langchain-mcp-adapters`); the MCP Python SDK for Patch's own server; Google Cloud Run, Cloud Storage, Secret Manager and Cloud Scheduler for the live app; ntfy, Telegram and SMTP for alerts.
- Why each choice: [DECISIONS.md](./DECISIONS.md).

## Knowledge base

All public and openly licensed, frozen as a snapshot on 2026-10-13. The counts are from `backend/fixtures/manifest.json`.

| Source | What it gives | Downloaded from | Licence | Count |
|---|---|---|---|---|
| OWASP Top 10 for LLM Applications 2025 | The 10 LLM risks and how to prevent them | [GitHub: OWASP/www-project-top-10-for-large-language-model-applications](https://github.com/OWASP/www-project-top-10-for-large-language-model-applications) | CC BY-SA 4.0 | 10 pages |
| OWASP Top 10 2025 (web) | The 10 web risks, and the CWE → category map that links CVEs to OWASP | [GitHub: OWASP/Top10](https://github.com/OWASP/Top10) | CC BY-SA 4.0 | 10 pages, 249 CWEs |
| MITRE ATLAS 5.6.0 | AI attack techniques, mitigations, case studies | [GitHub: mitre-atlas/atlas-data](https://github.com/mitre-atlas/atlas-data) | Apache 2.0 | 262 entries |
| NVD CVE API 2.0 | CVEs for the 12 tracked LLM products | [nvd.nist.gov](https://nvd.nist.gov/developers/vulnerabilities) | Public (US government) | 929 CVEs |
| CISA KEV 2026.10.08 | Which of those CVEs are known to be exploited, and CISA's deadline | [cisa.gov](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) | CC0 1.0 | 9 matches |
| OSV.dev | Affected and fixed versions, from GitHub Advisory Database records | [osv.dev](https://osv.dev) | CC-BY 4.0 | 514 records |
| EPSS | The chance each CVE is exploited in the next 30 days | [first.org/epss](https://www.first.org/epss) | Attribution requested by FIRST | 929 scores |

- **Attributions:** OWASP Top 10 for LLM Applications 2025 and OWASP Top 10:2025, by the OWASP Foundation. MITRE ATLAS, by The MITRE Corporation. CVE records from the National Vulnerability Database (NIST). CISA Known Exploited Vulnerabilities Catalog; no endorsement by CISA implied. Affected and fixed versions from OSV.dev, taken from GitHub Advisory Database records (CC-BY 4.0). EPSS by FIRST.
- **NVD notice:** This product uses the NVD API but is not endorsed or certified by the NVD.
- The dashboard's "Data freshness" card shows the same sources, licences and notices.
- **The 12 tracked products:** Langflow, Open WebUI, Flowise, vLLM, LangChain, Dify, Gradio, Ollama, llama.cpp, LiteLLM, AnythingLLM, LlamaIndex.
- **Text-matched CVEs:** 184 CVEs got their product from description text, not NVD's product data. OSV confirms 36; the other 148 are labelled "possible match".
- 1,680 chunks in the search index. How the sources link and why this domain: [FEASIBILITY.md](./FEASIBILITY.md).

### How the data gets in

- `feasibility/fetch.py` downloaded the raw NVD, KEV, OWASP and ATLAS files; they're kept in `backend/snapshot_raw/`.
- `backend/scripts/build_fixtures.py` builds the frozen snapshot in `backend/fixtures/` from them, offline. With `--fetch` it first re-downloads OSV and EPSS.
- `backend/fixtures/manifest.json` records each source with its URL, licence, attribution, retrieval date and count.
- **To refresh the data:** run `python3 -I feasibility/fetch.py`, copy the new files into `backend/snapshot_raw/`, change `AS_OF` in `build_fixtures.py`, then `cd backend && uv run python -m scripts.build_fixtures --fetch` and rebuild the index. *Unverified:* not re-run since 2026-10-14. Live mode keeps the CVE data current without it (spec B, [#32](https://github.com/DerykHopley/tc-patch-security/issues/32), [#36](https://github.com/DerykHopley/tc-patch-security/issues/36)).
- **In snapshot mode (the default) the app makes no live calls to these sources.** In live mode with `FEEDS=real`, the refresh calls NVD, KEV, EPSS and OSV.dev at fixed URLs; ATLAS and the OWASP pages stay snapshot data. Answers link back to the original pages: GitHub for OWASP, atlas.mitre.org, nvd.nist.gov and cwe.mitre.org.

### Other data the app uses (not knowledge sources)

- **Your local state:** the watchlist, product versions, CVE statuses and their history, settings, the alert log. One JSON file, `backend/data/state.json` (git-ignored).
- **Embeddings:** the hash embedder runs locally and is free (the default). Real embeddings come from OpenRouter's API (`text-embedding-3-small`) or a local Ollama model (`mxbai-embed-large`). The index is stored locally in `backend/data/`.
- **Optional outside services:** OpenRouter or a local model server for the chat; Tavily for web research (only the search query is sent); Clerk for sign-in (Patch keeps only the user id); ntfy, Telegram, email (SMTP) or the desktop for alerts. Model keys live in `backend/.env` only; the alert channels' secrets in `backend/.env` or, saved on Settings, in the owner's state (never sent back to the browser).

## Documents

Read in this order:

1. [STATUS.md](./STATUS.md): what's built, how to run and test it, the live app, what's open.
2. [DECISIONS.md](./DECISIONS.md): every decision, why, and where its detail lives.
3. [GLOSSARY.md](./GLOSSARY.md): the words used throughout (verdict, priority, due date, open CVE...).
4. [docs/design/DESIGN.md](./docs/design/DESIGN.md): the design: tokens, components, the chat, Patch, every animation, accessibility, a checklist per area.
5. The review pages on GitHub Pages: the [model-check report](https://derykhopley.github.io/tc-patch-security/), the [architecture review](https://derykhopley.github.io/tc-patch-security/architecture-review.html) (six deepenings, all built) and the [retro](https://derykhopley.github.io/tc-patch-security/retro.html) of the agent environment. Their sources: `docs/report/`.

More:

- [CODING_STANDARDS.md](./CODING_STANDARDS.md): the judgement rules for review.
- [DEPLOY.md](./DEPLOY.md): deploy to Google Cloud Run, step by step, with the costs.
- [docs/adr/](./docs/adr/): architecture decision records.
- [docs/SOURCE-CHECKS.md](./docs/SOURCE-CHECKS.md): facts about outside services, checked against their official docs.
- [docs/mcp-demo.md](./docs/mcp-demo.md): Patch as an MCP server, used from another assistant: the demo steps and transcripts.
- [docs/failure-demo.md](./docs/failure-demo.md): how to make a feed or a chat tool fail locally, and what partial success and retry look like (B20).
- [FEASIBILITY.md](./FEASIBILITY.md): the data check behind the domain.
- [ALERTS-PLAN.md](./ALERTS-PLAN.md): the alert design, built in spec B.
- [docs/process-map.html](./docs/process-map.html): the system map and its flows in two tabs: the current build ("Now", as of a named commit) and the prototype's of 2026-10-13, kept for comparison. Download and open it in a browser (GitHub shows HTML as source).
- [docs/research/openrouter-alphadecisions.md](./docs/research/openrouter-alphadecisions.md): OpenRouter's decisions endpoint and Jev, and what it could add.
- [docs/design-examples/README.md](./docs/design-examples/README.md): the designs and layouts that were tried, and why each was kept or dropped.
- `REQUIREMENTS.md`: the course brief. Course material, so it's kept out of this public repo.

### Code

- `backend/`, `frontend/`: the real build.
- `proto/`: the **frozen prototype** (2026-10-13), on FakeLLM. Kept as the reference the real build was checked against; not run in CI. Its spec and layout: [proto/SPEC.md](./proto/SPEC.md), [proto/PLAN.md](./proto/PLAN.md).
- `feasibility/`: the scripts that downloaded and summarised the source data.
- History, done: [FACTORY-PLAN.md](./FACTORY-PLAN.md) and `factory/` (a measured staged-agent build), [SECURITY-SWAP-PLAN.md](./SECURITY-SWAP-PLAN.md) (the prototype's move to security data), `archive/` (the earlier AI-news prototype), [AI-DIGEST-OVERLAP.md](./AI-DIGEST-OVERLAP.md) (links to a related project).

## How it was built: spec A

The real build, [spec A (#2)](https://github.com/DerykHopley/tc-patch-security/issues/2), was split into 21 tickets, built by coding agents in parallel worktrees and merged into the `spec-a` branch. An arrow means "must finish before". Orange tickets needed a person: two review gates and the first real model run. Later additions (A04b, A06b, A15b, A16b, the guardrails and the six architecture deepenings) are in [STATUS.md](./STATUS.md).

```mermaid
flowchart TD
    A01["#3 A01 Walking skeleton and CI"]
    A02["#4 A02 Design tokens and app shell"]
    A03["#5 A03 Gate A: design review"]
    A04["#6 A04 Dashboard: tiles, table, watchlist"]
    A05["#7 A05 Dashboard: charts, side panels"]
    A06["#8 A06 Chat on FakeLLM: bubble and Patch"]
    A07["#9 A07 Chat layout: enlarge, pin, keyboard"]
    A08["#10 A08 Real model via LangChain + citation check"]
    A09["#11 A09 Chroma and real embeddings"]
    A10["#12 A10 Hybrid search: BM25 + RRF"]
    A11["#13 A11 Dev panel and embedding map"]
    A12["#14 A12 Model check, metrics, report"]
    A13["#15 A13 Settings page"]
    A14["#16 A14 Snapshot: OSV, EPSS, licences"]
    A15["#17 A15 Am I affected?"]
    A16["#18 A16 Priority, policy, due dates"]
    A17["#19 A17 Gate B: rules review"]
    A18["#20 A18 What should I fix first?"]
    A19["#21 A19 Explain levels"]
    A20["#22 A20 Real model runs + report on Pages"]
    A21["#23 A21 README and STATUS"]

    A01 --> A02 --> A03
    A03 --> A04 & A06 & A13
    A04 --> A05
    A04 & A06 --> A07
    A06 --> A08 & A09
    A09 --> A10
    A08 & A10 --> A11 --> A12
    A04 & A05 --> A14
    A07 & A12 & A14 --> A15
    A13 & A15 --> A16 --> A17 --> A18
    A07 & A12 & A13 --> A19
    A12 & A15 & A18 & A19 --> A20 --> A21

    classDef human fill:#fff1de,stroke:#b8640a,color:#2a2559
    class A03,A17,A20 human
```

## How it was built: spec B

[Spec B (#31)](https://github.com/DerykHopley/tc-patch-security/issues/31) was built the same way, on the `spec-b` branch: 25 planned tickets (B01 to B25; B17 is this documentation), then the owner's page review and the live app's findings as more tickets, up to B67. Coding agents built each in its own worktree; `scripts/ff-merge.sh` fast-forwarded each into `spec-b` after its checks (no lost commits, no conflict markers, no unpushed work). Human steps were tickets too: the real live run (B07), the deploy (B14), the real-model run (B16), the two MCP demos. What each ticket built: [STATUS.md](./STATUS.md#whats-built). The decisions on the way: [DECISIONS.md](./DECISIONS.md).

## How the launch video was built

The 20-second "Patch in 20 seconds" video on the landing page and About (B47, [#99](https://github.com/DerykHopley/tc-patch-security/issues/99)), in a light and a dark version (`frontend/src/landing/video/`). The build files were throwaway and aren't in the repo; this is the record, written right after it was made.

- **Made with Claude Code** and its `/brag-slim` skill (brag plugin 0.4.0), no video editor. The owner picked one of two cuts ("one claim per scene, hard cuts, played straight" over a playful one) and checked the sound.
- **Real screenshots, not mock-ups.** A throwaway browser-check file ran through `frontend/e2e/run.sh` (its throwaway servers: FakeLLM, a temp state file, never the owner's app), with the example data of `scripts/landing-shots.sh`. Chromium at 1280 × 800, device scale 2, light and dark: the dashboard, the CVEs page, and CVE-2025-3248's page with the chat pinned, before and after "Am I affected by CVE-2025-3248?".
- **The app's own parts.** Each frame is a small React page built with the frontend's Vite. It imports the app's `tokens.css`, `robot.css`, `landing.css`, the `Robot` component (Patch's moods and animations) and the shield icon, so the colours, fonts and robot are the app's in both themes.
- **Every frame a function of time.** `window.__seek(t)` draws the frame at time t and pauses Patch's CSS animations there. Playwright's Chromium captured 1920 × 1080 PNGs at 30 fps: 608 frames per theme.
- **One claim per scene, on the beat:** six scenes of 3 s (the last 5.25 s); each cut falls on a bar of the 80 BPM music.
- **The sound is synthesised in Python** (numpy, scipy), not a stock track: a soft electric-piano chord per scene in A major, a low thump on each cut, plucks for the chips and words, a reverb made from decaying noise, a soft limiter; then normalised to −14 LUFS by ffmpeg.
- **Encoded with ffmpeg:** H.264 at CRF 24 (about 1.5 MB each, the small chat text stays sharp), AAC 128 kb/s, `faststart`. Frame 0 is the poster, so a thumbnail shows the robot; WebP posters at 1280 × 720.
- **Checked before rendering:** stills of every scene and of the cuts were looked at; a ring that clipped a letter and the robot's mood were fixed from them. Found along the way: [#98](https://github.com/DerykHopley/tc-patch-security/issues/98), the landing end card's Patch showing idle, not happy (fixed in B52).

## Licence

The data keeps its own licences (table above). No licence has been chosen for the code yet.

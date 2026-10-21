# What Patch does, in full

Each feature with its ticket ids. The short list is in the [README](../README.md#what-it-does).

## The assistant (spec A)

- **Chat with Patch.** Retrieval over the knowledge base with query translation (multi-query rewrites, merged by reciprocal rank fusion) and structured retrieval (the model writes metadata filters; the server checks them against fixed lists). Search is hybrid: vectors plus our own BM25 keyword search. Answers cite numbered sources; a citation with no matching source is removed and listed.
- **Six tools:** `search_security`, `lookup_cve` (with KEV, verdict and priority), `explain_weakness` (CWE → OWASP category, ATLAS technique → mitigations), `check_affected` (am I affected, for your version), `prioritise` (what to fix first, from the rules) and `update_watchlist` (which only proposes: you approve, edit or cancel the change in a card). Every call shows as a card under the answer.
- **Am I affected?** You give each watched product a version and how you run it. OSV's affected and fixed versions give a verdict per CVE: affected, not affected or unknown, with the reason.
- **Priority by rules.** KEV, EPSS, severity, the verdict and an internet-facing switch give each open CVE a priority (urgent, high, normal, low) and a due date from your policy. Rules decide; Patch only explains them.
- **Dashboard and CVEs page.** Tiles, charts and the top 5 open CVEs, filtered by product. The CVEs page lists every CVE on your watchlist with filters in the URL. Each status change (fixed, not affected, accepted) goes through a dialog and into a history; not affected needs a justification, accepted a reason and a review date.
- **Explain levels:** simple, normal or deep dive, set in Settings or per question.
- **Page-aware chat:** "What should I fix first?" means the view you're looking at.
- **Token usage and cost** under every answer: tokens in and out, LLM calls, steps, and dollars (from OpenRouter's reported cost).
- **Dev page:** switch the model at runtime (FakeLLM, OpenRouter, or a local OpenAI-compatible server such as Ollama), tune search, watch each retrieval step in a playground, see the index on an embedding map, and run the model check.
## What spec B added

[Spec B (#31)](https://github.com/DerykHopley/tc-patch-security/issues/31) took Patch off the frozen snapshot and onto a public address. Each part, with its ticket ids; the full list is in [STATUS.md](../STATUS.md#whats-built).

- **Live data and Check now** (B02, B03, B28, B59). Live mode pulls what changed from NVD, CISA KEV, EPSS and OSV.dev and makes the new CVEs searchable straight away. It runs on a schedule (a systemd timer locally, Cloud Scheduler on the live app), from **Check now**, or when you ask Patch "anything new since Monday?" (`check_updates`). Check now is on the dashboard's Data freshness card, for everyone, and on Settings → Refresh runs, for the owner, above the run history ([#103](https://github.com/DerykHopley/tc-patch-security/issues/103)). How: [Live data](SETUP.md#live-data-from-the-real-feeds-on-a-schedule).
- **Alerts** (B04, B34, B41, B55, B57). After each refresh, by your rules: a watched CVE added to KEV, a new CVE at your minimum severity, a rescore to critical, a due date in 3 days, an overdue reminder once a week. Once per CVE and reason, many at once as one digest, held in quiet hours, a failed send tried again. Channels: desktop, email, ntfy and Telegram ([#102](https://github.com/DerykHopley/tc-patch-security/issues/102)). Everyone sees Recent alerts and the "New" chip in Patch; only the owner's alerts go to the channels. How: [Alerts](SETUP.md#alerts).
- **Web research** (B08, B22, B63, B64). Patch's `research_web` tool asks Tavily's hosted MCP server. Web results are cited as "Web result, unverified", passed to the model as untrusted data, and a page that tries to give instructions is flagged and ignored. Exploit sites are dropped. A research question can end in a decision Patch proposes and you approve. How: [Web research](SETUP.md#web-research-tavily).
- **Changes you approve** (B21, B24). Patch never changes your data by itself: it proposes, and a card shows the change with Approve, Edit and Cancel. Buttons on tool cards do the next step (Open in CVEs page, Watch this product, Set my version…).
- **A page per CVE** (B35): `/cves/CVE-…`, with the summary, your assessment, the actions and the decision history.
- **Sign-in and your own data** (B09, B10, B38, B45, B48, B60). Clerk sign-in. Open sign-up, each account approved by the owner, with roles. Each person has their own watchlist, statuses, decisions and settings. Patch stores no names or emails. How: [Sign-in](SETUP.md#sign-in-clerk).
- **Rate limits** (B11): chat messages per person per minute and per day, a daily web-research cap, one refresh at a time, and a plain note with a retry time.
- **Deployed** (B12, B13, B14): one container on Google Cloud Run in Belgium, state in Cloud Storage, keys in Secret Manager, at no cost so far. How: [On Google Cloud Run](SETUP.md#on-google-cloud-run).
- **Patch as an MCP server** (B23): four read-only tools for Claude Code or Claude Desktop. [Try it in 5 minutes](SETUP.md#try-it-in-5-minutes).
- **A landing page** (B42, [#80](https://github.com/DerykHopley/tc-patch-security/issues/80)). A visitor who isn't signed in first sees what Patch is, the problem it solves and three screenshots in their theme, then **Sign in** or **Request access**. Inside the app it is the **About** page (`/about`). It has a 20-second launch video, light or dark to match (B47, [#99](https://github.com/DerykHopley/tc-patch-security/issues/99); [how it was built](HOW-IT-WAS-BUILT.md#the-launch-video)). Its screenshots are taken from the app on example data by `scripts/landing-shots.sh` ([how](design/DESIGN.md#516-the-landing-page-b42-80-2026-10-19)).
- **Link previews** (B61, [#108](https://github.com/DerykHopley/tc-patch-security/issues/108)). A link to `/` or `/about` pasted into a chat app shows a card with Patch's name, a line about it and an image. The server adds the tags only when `APP_URL` is a public https address (*checked* 2026-10-20: the live app's `/` carries them). How the card looks in Telegram and other apps is *unverified*; send the link to @WebpageBot first if Telegram cached an old preview.

## Screenshots

| The chat, pinned beside a CVE's page | Settings: your watchlist |
|---|---|
| ![Patch answering "Am I affected by CVE-2025-3248?" beside the CVE's page, with the check_affected tool card open](media/chat-light.png) | ![The watchlist card in Settings: products, usage, version, internet-facing](media/settings-light.png) |
| **The CVEs page** | **Dark mode** |
| ![The CVEs page with verdicts, priorities and due dates](media/cves-light.png) | ![The dashboard in dark mode](media/dashboard-dark.png) |

Spec B:

| Web research, with a flagged page | Check now and the alert channels on Settings |
|---|---|
| ![Patch's research_web tool card: three web results, each marked "Web result, unverified", one flagged "instructions ignored"](media/web-research-light.png) | ![Settings: the Delivery card with desktop, email, ntfy and Telegram, and the Refresh runs card with Check now and its result](media/check-now-settings-light.png) |
| **The dashboard after Check now** | **The landing page, as About** |
| ![The dashboard in live mode: Recent alerts lists three alerts, Data freshness shows Check now and "See the 2 new CVEs"](media/check-now-dashboard-light.png) | ![The About page: "Security flaws in your LLM stack, tracked for you", the four tiles and the launch video](media/landing-light.png) |

The "Open CVEs by product and severity" chart opening:

![The chart's bars growing in, one product at a time](media/open-cves-chart.gif)

- Taken 2026-10-20 in Chromium, 1440 × 900, on the browser check's throwaway servers: FakeLLM, the example watchlist (Langflow 1.2.0, internet-facing; LiteLLM 1.80.0), sign-in off. The chart animation is from 2026-10-15.
- FakeLLM is a scripted stand-in, so the chat shows the app working, not a real model's wording. The web results come from a fake Tavily with canned pages, one of them an injection attempt.
- Check now ran on the made-up test feeds, so the dashboard warns "Live: the made-up test data, not the real feeds". On the real feeds that line names NVD, CISA KEV, EPSS and OSV.dev.

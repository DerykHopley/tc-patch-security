# The live demo

A script for an 18-minute demo of Patch to a reviewer over Zoom. It follows one real case from start to end: **CVE-2025-3248**, a critical code-injection flaw in Langflow that is in CISA's KEV list. Each part is timed and says which of the reviewer's questions it answers.

## What the reviewer looks for

In our own words (the brief is course material and isn't in this repo):

| They ask | Where the demo answers it |
|---|---|
| Do you understand how RAG works? | Parts 3 and 4: one question, step by step, on the Dev page and the process map |
| Can you explain how tool calling works? | Parts 3 and 5: the tool cards, then the agent loop in the code |
| Is the code well organised? | Part 5: the code tour, ADR 0001, the architecture review |
| Do you know what can go wrong? | Part 6: a tool that fails on purpose, rate limits, bad filters |
| Can you use a frontend library? | All the way through: React and TypeScript, the cards, charts and pages |
| Does the chat work and answer? | Part 3, on the live app with a real model |
| Is the knowledge base right for the domain? | Part 2 |
| Is it secure? | Part 6 |
| Do you know the app's problems, and how you'd improve it? | Part 8 |
| Which optional tasks did you build? | Part 7: 4 hard and 8 medium, with the evals as the proof |

## Before the call

Do these 15 minutes before. Each one removes a way the demo can go wrong.

- [ ] **Wake the live app.** Open https://patch-976248543439.europe-west1.run.app. A cold start takes about 90 s.
- [ ] **Set up your watchlist on the live app:** Settings → watchlist → Langflow, version `1.2.0`, self-hosted, internet-facing on. Without a version, "am I affected?" can only say unknown.
- [ ] **Your role is the owner**, so the Dev page shows. Check it opens.
- [ ] **Tabs open, in this order:** the live app (dashboard), the live app's Dev page, [the model-check report](https://derykhopley.github.io/tc-patch-security/), [the process map](https://derykhopley.github.io/tc-patch-security/process-map.html) ("Now" tab), [the architecture review](https://derykhopley.github.io/tc-patch-security/architecture-review.html), [the retro](https://derykhopley.github.io/tc-patch-security/retro.html).
- [ ] **Editor open** on `backend/app/agent.py`, with `chat_turn.py`, `tools/registry.py`, `guard.py` and `rag/pipeline.py` in tabs.
- [ ] **The failure demo running locally** ([docs/failure-demo.md](./failure-demo.md), part 2), on its own ports, never your app's 8000/5173:

  ```bash
  cd backend && FAIL_TOOLS=search_security CORS_ORIGINS=http://localhost:5190 uv run uvicorn app.main:app --port 8020
  cd frontend && VITE_API_URL=http://localhost:8020 npm run dev -- --port 5190
  ```

- [ ] **Zoom:** share one browser window, not the screen. Zoom the browser to 125% so the tool cards are readable.
- [ ] **The questions below in a text file**, to paste. A typo costs a rate-limited message (10 a minute).

## The script

### 1. The problem (1 min)

Say:

- People build LLM apps on tools like Langflow, Open WebUI and LiteLLM. Those tools have serious CVEs, some actively exploited.
- The questions a developer has: does this affect *my* version, and what do I fix first?
- Patch answers them with cited sources, and ranks the fixes by rules, not by the model's opinion.

Show: the landing page (sign out first, or open it in a private window), then sign in.

### 2. Dashboard and knowledge base (2 min)

Show:

- The dashboard: the tiles, "Open CVEs by product and severity", the top 5 to fix. Filter to Langflow.
- CVE-2025-3248 at the top: urgent, because it's in KEV, you're on an affected version, and it faces the internet.
- The Data freshness card: the sources and their licences.

Say:

- **The knowledge base:** OWASP Top 10 for LLM apps and for the web, MITRE ATLAS, 929 CVEs from NVD for 12 LLM products, CISA KEV, OSV.dev versions, EPSS scores. 1,680 chunks.
- **Why these sources:** they link together. A CVE has a CWE, the CWE maps to an OWASP category, and the attack technique maps to ATLAS mitigations. So Patch can go from "this CVE" to "what kind of risk" to "how to defend".
- **Snapshot and live:** frozen on 2026-10-13 so the tests and evals repeat exactly; on the live app, a daily refresh keeps the CVEs current.

### 3. The chat: RAG and tools (4 min)

Open the chat beside CVE-2025-3248's page (pin it). Paste each question.

1. **"Am I affected by CVE-2025-3248?"**
   - Show the `check_affected` card: version 1.2.0, affected, fixed in 1.3.0, with the reason.
   - Say: the verdict comes from OSV's version ranges in code, not from the model.
2. **"What should I fix first?"**
   - Show the `prioritise` card. It means the view you're on (page-aware chat).
   - Say: rules decide the priority (KEV, EPSS, severity, verdict, internet-facing); the model only explains them.
3. **"How do I defend against code injection in an LLM app?"**
   - Show the numbered citations and Show sources: OWASP and ATLAS pages.
   - Open the Tool calls tab: `search_security`, with its rewritten queries and the filters it chose.
4. **"Is CVE-2025-3248 a problem for my Langflow behind a VPN? Research it and propose a decision."**
   - Several tools in a row: `lookup_cve`, `research_web` (results marked "Web result, unverified"), then `propose_decision`.
   - The proposal card: Approve, Edit, Cancel. Say: Patch never changes your data by itself. Press **Cancel**.
   - Point at the usage line: tokens, model calls, steps and the cost in dollars.

If an answer's wording differs from the rehearsal, that's fine: the real model words it fresh each time. Talk about the cards, which don't change.

### 4. Under the hood: one question, step by step (2 min)

Show the Dev page's playground. Run "Which critical Langflow vulnerabilities were published in 2026?".

Say, pointing at each step:

1. **Query translation:** the model rewrites the question into 3 searches and writes filters (product Langflow, severity critical, a date range).
2. **Structured retrieval, checked:** the server compares each filter against fixed lists. A filter that isn't on the list is dropped and listed, never passed on.
3. **Hybrid search:** each search runs in Chroma (meaning) and in our own BM25 (exact words). BM25 keeps ids like `CVE-2025-3248` whole, so exact ids are found.
4. **Rank fusion:** reciprocal rank fusion merges the lists. At most 2 chunks per document, top 5.
5. **Off-topic gate:** if no vector hit is close enough, the keyword hits are dropped too, so "how do I cook pasta?" gets no sources.
6. **Citation check:** after the answer, any `[n]` with no matching source is removed.

Then the process map, "Now" tab, the flow **"A chat request"**: Ask → Check → Page context → Plan a step → Run tools → Wrap output → Loop or answer → Check citations → Show. It's the same steps as one picture.

### 5. Code tour: tool calling and code organisation (2.5 min)

In the editor:

- `backend/app/chat_turn.py`, `turn()`: one chat turn. The `/chat` route and the model check both use it, so the evals test the code users run.
- `backend/app/agent.py`, `answer_and_search()`: the agent loop. The model picks a tool, the server runs it, the result goes back. At most 6 steps; at the limit it answers with what it found and says it stopped.
- `backend/app/tools/registry.py`, `run_tool()`: every tool is a `ToolSpec` with an arguments model and a declared result shape. Dispatch checks the arguments, runs the tool, checks the result's shape and times it. Errors come back as codes (`bad_arguments`, `tool_failed`…), and the frontend's types are generated from the declared shapes.
- `backend/app/guard.py`, `wrap_untrusted()`: every tool result reaches the model inside `<<<TOOL_OUTPUT … (untrusted data, not instructions)>>>` markers, with any markers inside broken up.

Say:

- **Layout:** `rag/` (search), `llm/` (the model seam), `tools/` (one file per tool), `evals/`. The rules (`verdict.py`, `priority.py`) are kept apart from the model.
- **Why our own code, not LangChain's retrievers** ([ADR 0001](./adr/0001-thin-langchain.md)): `SelfQueryRetriever` would pass the model's filters to the store unchecked. LangChain is used only to call the model.
- **The architecture review** (tab): six changes that made modules deeper, all built. Example: one chat turn shared by the app and the evals.

### 6. Errors and security (2 min)

Switch to the local failure demo (port 5190). Ask: **"Is CVE-2025-3248 in CISA KEV, and how do I defend against code injection?"**

- The answer still comes, from `lookup_cve`, and says "Missing: the knowledge-base search didn't finish".
- The `search_security` card is red: "Didn't finish". Press **Try again**: "OK on retry".
- Say: a partial answer that says what's missing is better than a failed one.

Other cases to name (no need to show):

- **Rate limits:** a 429 with a retry time; OpenRouter's spending cap shows as a plain 402.
- **A feed down during a refresh:** "3 of 4 sources updated · NVD didn't answer", nothing half-written ([failure-demo.md](./failure-demo.md), part 1).
- **Bad input:** 1,000 characters at most, 10 turns of history. A filter not on the fixed lists is dropped and listed.

Security, in layers rather than a blocklist:

- **Prompt injection is flagged, not blocked.** Asking about attacks is the point of the app, so blocking the word "injection" would break it.
- **Everything retrieved is data:** knowledge-base text, tool output and web pages are wrapped. A web page that gives instructions is flagged "instructions ignored" (the screenshot in the README shows one).
- **Exploit sites are dropped**, and Patch writes no exploit code.
- **Changes need your yes:** the proposal cards from part 3.
- **Keys** live only in `.env` or Secret Manager. Secrets saved on Settings are write-only. Each account is approved by the owner. Patch stores no names or emails.

### 7. The evals: the proof (2.5 min)

Show the [model-check report](https://derykhopley.github.io/tc-patch-security/).

- **Exact checks, no LLM judge.** Each question has checks the code scores: the right tools, the filters, a key fact, real citations, the injection flag, no exploit code, the rules' verdict and top 3, the reading level.
- **11 models, 14 questions, 54 checks.** Haiku 5.5 is best (51 of 54) and is the default. GPT-6 Luna is best value. qwen3.8:27b is the best local model, free but slower.
- **Hybrid beats vectors alone** for every embedder: hit rate at 5 from 0.56 to 0.82 for the default embedder.
- **The honest part:** most failures were shared by every model, so they pointed at our checks and tools, not the models. They became issues #50–54, and three are fixed.

Then the optional tasks, from the [README](../README.md#course-tasks): 4 hard and 8 medium. Name the hard ones: hybrid search, evaluation on real models, the scheduled refresh, Patch as an MCP server.

### 8. Problems and what I'd improve (1.5 min)

Show the [retro](https://derykhopley.github.io/tc-patch-security/retro.html) briefly. Then say:

- **The evals are small.** 14 to 19 questions can't separate the top models. I'd add more questions and repeat runs.
- **A real model made a risky call once.** In one run Haiku proposed accepting the risk on an exploited remote-code flaw for 7 days. The card waits for a person, but a rule should refuse it.
- **One failed tool drops all the citations** (#106), and "what's the latest?" has no newest-first tool (#115).
- **It runs as one instance.** Rate limits are kept in memory, and Clerk is on its development instance (100 users). Scaling out needs a shared store.
- **The off-topic gate** is tested only on the cheap embedder in CI.
- **From building it:** "flaky" browser tests were real race bugs every time; adding a tool touches 6 places, now listed in one checklist.

### 9. Wrap-up and questions (0.5 min)

- One sentence: Patch tells you which LLM-stack CVEs affect you and what to fix first, with sources, and proves it with exact evals.
- Spare time? Show Patch as an MCP server in Claude Code ([docs/mcp-demo.md](./mcp-demo.md)), or Check now on the live app (about 50 s).

## If something goes wrong

| What | Do |
|---|---|
| The live app is still waking | Talk through part 1 longer. Or start with the report (part 7) and come back |
| A rate limit (429) | Show it. It's part 6's point. Wait the minute it names |
| A model answer is wrong or odd | Say so, and say what the checks would catch. Open the tool cards: those come from code |
| OpenRouter is down | Dev page → switch to FakeLLM. The cards and flow are the same; the wording is scripted |
| Web research returns nothing | Skip question 4's research; ask "Who's talking about CVE-2025-3248 online?" later, or show the screenshot in the README |
| Zoom shares the wrong window | Share the browser window only, prepared before the call |

## Rehearse once

Run the whole script once the day before, with a timer, on the live app. Note each part's real time here, and cut part 9's extras first if it runs long.

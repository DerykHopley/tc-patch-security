# OpenRouter Decisions API and Jev: what it could add to Patch

Research by Claude, 2026-10-15, for Deryk to review. Read-only: no code changed, no paid endpoint called, no key used.

- **checked** = read in a primary source (URL given). **unverified** = inferred, secondary, or not found in a source.
- Sources are listed by number at the end. [S1] means source 1.

## Summary

- Jev is not a chat model. It's TypeSafe's "System One" decision model: you send a JSON `state` and typed questions (yes/no, pick one, score, image box), and it returns probabilities, no text. Served on OpenRouter at `POST /api/alpha/decisions`, an alpha endpoint. **checked** [S1][S3]
- It's very cheap and fast: $0.042 per million input tokens, output free; about $0.00002 for a 476-token request; under 600 ms in one cookbook. Answers vary a little from run to run, and TypeSafe makes no accuracy or calibration figures public. **checked** [S7][S4][S6][S10]
- Patch's decisions are rules on purpose (verdict, priority, due dates, your marks). Jev must not touch them. Where it does fit is the few fuzzy *text* judgements Patch makes today with weak tools: "is this CVE really about this product?", "is this answer backed by its sources?", "does this proposal match what the user asked?".
- Best fit: score the 148 text-matched CVEs that OSV can't confirm (today all shown as "possible match"), once, at build or refresh time, frozen into the data. Public data only, about $0.003 for the whole snapshot, testable against labels we already have.
- Recommendation: one buffer-week experiment (the product-match check), only after spec B's own tickets; everything else is "later" or "doesn't fit".

## What it is (checked facts)

- **Jev** is a model made by **TypeSafe**. OpenRouter calls it "TypeSafe's structured decision model and the first of its System One models". **checked** [S3][S7]
- **System One** is TypeSafe's name for "a class of AI models built to make fast, structured decisions that software can use directly". It returns typed answers and probabilities, "not generated text". **checked** [S8]
- "Jev is not an LLM." It "does not produce reasoning traces, explanations, or free-form text" and "is not a drop-in replacement for a chat model". It "replaces the prompt-and-parse step": asking an LLM a narrow question and parsing a label out of the reply. **checked** [S3]
- **Versions:** `typesafe/jev-1.14` is the latest (on OpenRouter since 2026-10-14, a day ago); `typesafe/jev-1.13` is still served; `~typesafe/jev-latest` is an alias for the newest. The response names a dated snapshot, e.g. `typesafe/jev-1.13-20260917`. **checked** [S3][S7][S4]
- **AlphaDecisions** is the API reference group for the endpoint. Its tag says "Alpha feature endpoints for Decisions requests". So the endpoint is alpha. No GA date is given. **checked** [S1]
- There is only one endpoint in the group: submit a request. No "get a decision", list or feedback endpoint is documented. **checked** [S1][S2]
- A second route exists for TypeSafe's own SDKs: `POST https://openrouter.ai/api/v1/systemone` (JS `@typesafe-ai/sdk`, Python `typesafe_sdk`). Same billing. **checked** [S5]
- **Jev Router** (`typesafe/jev-router`) is a different product: a chat "model" that uses Jev to pick a real model and reasoning effort per request. **checked** [S9][S11]
- **Calibration:** TypeSafe says System One models "are trained for calibrated decisions", but calibration "is measured across groups of predictions" and "does not guarantee that an individual answer is correct". The Confidence page gives no accuracy figures and says thresholds "depend on your domain and the performance of the model for your use case". **checked** [S8][S10]
- **Injection resistance:** no source says anything about how Jev handles prompt-injection text inside `state`. **unverified**

## How it works (request and response)

Endpoint: `POST https://openrouter.ai/api/alpha/decisions`, `Authorization: Bearer <OpenRouter key>`. **checked** [S1]

Request:

- `model`: e.g. `typesafe/jev-1.14`.
- `state`: a string, object or array: the facts to judge. TypeSafe's advice: send only what the questions need, as nested JSON, and point at values by path, e.g. `ticket.message`. **checked** [S1][S12]
- `questions`: an object keyed by your own names. Each has a `type`, `instructions` and `criteria`:
  - `noul`: yes/no. Criteria with `true` and `false`. Answer: `noul`, the probability of yes.
  - `choice`: one of named options. Answer: `choice`, `confidence`, `probabilities`.
  - `score`: a place on an ordered scale. Answer: `score` (probability-weighted), `confidence`, `probabilities`, `legend`.
  - `box`: a box in an image. Jev 1.14 only; marked an early feature. **checked** [S1][S3]
- Optional: `provider` (routing prefs, including `data_collection: "deny"` and `zdr: true`), `session_id`, `trace`, `user`. **checked** [S1]

Response: `id`, `model` (dated snapshot), `provider` ("TypeSafe"), `answers` keyed by question name, `usage` with `input_tokens`, `output_tokens`, `cost` (USD). **checked** [S1]

The docs' example: a support ticket, three questions in one request (`is_bug` noul 0.96, `team` = payments at 0.75 confidence, `urgency` score 1.99), 476 input tokens, $0.000019992. **checked** [S1][S4]

Design advice from TypeSafe that matters for Patch: **checked** [S12]

- Ask narrow questions: "Broad questions hide several judgments behind one answer."
- "Keep deterministic work in code. It is reliable and cheap."
- Make code act differently on confident and unconfident answers; send unsure cases to a person.

A minimal Patch-shaped request (illustration, not run):

```json
{
  "model": "typesafe/jev-1.14",
  "state": {"product": "Langflow", "cve": {"id": "CVE-...", "description": "..."}},
  "questions": {
    "about_product": {
      "type": "noul",
      "instructions": "Is the vulnerability in `cve.description` in `product` itself, not only mentioned?",
      "criteria": {"true": "The flaw is in this product's code", "false": "Another product, or only a mention"}
    }
  },
  "provider": {"data_collection": "deny"}
}
```

## Price and limits

- **Price:** $0.042 per million input tokens (`"prompt":"0.000000042"`), output free (`"completion":"0"`), for `typesafe/jev-1.14`. **checked** [S7]
  - The docs' example cost matches this exactly: 476 × $0.042/M = $0.000019992. So 1.13 seems priced the same. **checked** (arithmetic on [S7] and [S1])
- **Context:** 262,144 tokens for state plus questions. Text over about 32,000 bytes (and any image) runs in a long-context mode TypeSafe calls "slower and less accurate". **checked** [S3][S7]
- **Latency:** no figure in the reference or tutorial. One cookbook measured "under 600 ms" per request (4 requests, refund gating). **checked** [S6] (one small sample)
- **Rate limits:** none stated. 429 is a listed error. **checked** [S1]
- **Repeatability:** "Your probabilities will differ slightly from run to run." Pin a version (not `jev-latest`) when thresholds must stay stable. One cookbook saw one probability move between 0.35 and 0.43 over four repeats. **checked** [S4][S6]
- **Alpha:** the endpoint is under `/api/alpha/`; request format and limits of the early features (images, box) "can change between releases". **checked** [S1][S3]
- **Not in the public models list:** `typesafe/jev-1.14` doesn't appear in `/api/v1/models` (only `typesafe/jev-router` does), but `/api/v1/models/typesafe/jev-1.14/endpoints` answers. The model web pages (`openrouter.ai/typesafe/jev-1.13`, `/jev-1.14`) returned 404 to my fetch. **checked** (fetched 2026-10-15)
- **Data and privacy:** you can send `provider.data_collection: "deny"` and `provider.zdr: true`. I found no statement of TypeSafe's own retention or training policy; the provider-logging page didn't render its table for me. Whether a Jev endpoint qualifies as zero data retention is **unverified**. Check before sending anything from a user's stack.
- **Patch's own constraint:** the OpenRouter workspace has a model allow-list (gpt-oss-120b was refused for that reason). Jev would need adding to it. **checked** (docs/report-src/findings.html)

## Ideas for Patch (ranked)

Cost comparison: a chat answer on Claude Haiku 5.5 costs about $0.0015 (DECISIONS.md, 2026-10-15). A 3,000-token Jev check costs about $0.00013, under a tenth of that.

### 1. Product-match check for text-matched CVEs (best fit)

- **What:** 184 CVEs got their product from description text. OSV confirms 36; the other 148 are "unknown" and all show as "possible match" (`backend/fixtures/product_check.json`, `backend/scripts/snapshot_additions.py` `product_check()`). Jev answers one `noul` per CVE: is the flaw in this product, or only a mention? The result becomes a third label, e.g. "likely match" / "unlikely match", next to OSV's "confirmed". **checked** (counts read from the fixture)
- **Where it plugs in:**
  - Snapshot build: a new offline step next to `product_check()` in `backend/scripts/snapshot_additions.py`, written into `product_check.json` with the model id, date and probability.
  - Spec B: the shared build code (#31, slice 1) and the refresh, since new CVEs mostly match by text ("NVD's backlog means fresh CVEs mostly match by description text", spec B's expected trouble). Alerts already say "possible match" (`backend/app/notify.py`).
  - `Knowledge.possible_match()` in `backend/app/knowledge.py` reads the new label; `lookup_cve`, the CVEs page and the alert text show it.
- **Why it's better than now:** today a CVE that only *mentions* LangChain looks the same as one *in* LangChain. A wrong match means a false alert, or a wrong item in "what should I fix first?". The rules stay rules: Jev only grades a data field, as OSV does.
- **Why it fits Patch's decisions:**
  - Public data only (NVD descriptions). No watchlist, no versions, no user question leaves the machine.
  - Run once, frozen: tests and the model check stay exact. CI never calls Jev; it reads the frozen file.
  - Measurable: we have labels. The 36 OSV-confirmed and the 745 CPE-matched CVEs are true pairs; pairing a description with another product gives false pairs. Report accuracy at a threshold before trusting it.
  - Cost: 184 × ~400 tokens ≈ $0.003; all 929 CVEs ≈ $0.02. **unverified** (token counts estimated)
- **Risks:**
  - Should it change priority? No. Keep it a label. If the owner later wants "unlikely match" to lower priority, that's a rule change in `priority.py` with a table test, decided by the owner, not by Jev.
  - Alpha endpoint and a day-old model version: pin `typesafe/jev-1.14` and store the dated snapshot id with the results.
  - A "rules decide" reviewer may ask why a model grades data. Answer: it's the same kind of advice as the verdict, and the user's mark still decides.

### 2. Grounding check on chat answers (experiment)

- **What:** the "verified cascade" pattern [S13]. After each answer, one `choice` question: `supported` (every fact is in the sources), `unsupported`, `declined`. A low-confidence or `unsupported` result adds a quiet note under the answer, like the existing `no_citations` note.
- **Where:** `backend/app/agent.py` `answer()`, after `check_citations()`; a new field on `ChatReply` (`backend/app/schemas.py`); a new kind of check in `backend/app/evals/checks.py` reported as its own column. Behind a seam (`Decider` with a `FakeDecider`), like the `LLM` seam.
- **Why:** the citation check only proves a cited number exists, not that the sentence is in the source. The report's riskiest failure was a model answering from memory with no sources (findings.html). The cookbook's cascade shipped 0 wrong answers on 50 questions for $0.012. **checked** [S13] (their test, their data, one 50-question set)
- **Risks:**
  - The model check is "exact checks, no LLM judge" (DECISIONS.md, 2026-10-13). Jev is not an LLM, but it is a learned judge with no published accuracy. Keep it as a separate, labelled column; never let it decide pass or fail.
  - The "no sources at all" failure is already caught in code (no tool call, no sources). Jev's value is only the subtler case: sourced but embellished.
  - Data: the question, the answer and the sources go to TypeSafe. The sources are public; the question and the page context can show the user's stack (e.g. "my Langflow 1.2.0"). Send no page context, and `data_collection: "deny"`.
  - Cost per question about +10%; latency +0.5 s or so. **unverified** for Patch's sizes.
  - Not repeatable run to run; thresholds need tuning on our own answers (TypeSafe says so itself [S10]).

### 3. A second look at proposals and web results (#58, #62, #33) (later)

- **What:** before a proposal card shows (#58), ask three `noul`s, like the refund gate [S6]: did the user ask for this change? is it the CVE they mean? does the justification follow from the cited sources? For #62, also: did a web source push the proposed status? Show a warning on the card when any is unsure.
- **Where:** the proposal builder #58 adds, and `research_web` (#33) for a per-snippet "reads like instructions" probability alongside `guard.looks_like_injection()` in `backend/app/guard.py`.
- **Why:** the regex guard only catches obvious phrasing. #62 is where web text could steer a decision record.
- **Why only "later":**
  - Every change already waits for the user's yes (#58). The cookbook's real value is *auto-approving* safe calls; Patch must never auto-approve ("state changes need the user's yes", DECISIONS.md). So Jev would add a warning, not save a click.
  - No source says Jev resists injection inside `state`. A page that fools the chat model may fool Jev too. **unverified**
  - #58 and #62 are bonus stretches already.

### 4. Off-topic gate (doesn't beat the free fix)

- **What:** a `noul` "is this about application or AI security?" before search.
- **Why not:** findings.html already proposes a free, deterministic fix (use BM25 hits only when the vector search finds the question on-topic), and no model searched for the pasta question. Jev would add a call and send every question out.

## What doesn't fit and why

- **Ranking or re-ranking CVEs, or a "real-world urgency" score.** "Rules decide, Patch explains" and the `prioritise` tool "never re-ranks" (DECISIONS.md, `backend/app/tools/prioritise.py`). The priority is a pure function with table tests (`backend/app/priority.py`). A probability from an alpha model would make the order unexplainable and untestable, and break the model-check question whose top 3 must match the rules.
- **Guessing the verdict when OSV has no data** (e.g. 160 of 201 Langflow CVEs). "Unknown, with a reason" is honest; a probability is a guess wearing a number. It would also send the user's version (their stack) to a third party. If version text in descriptions helps, a regex is free and exact.
- **Auto-approving status changes or accepted risks.** Accepting a risk is the user's alone (`update_watchlist` can't even offer it). Jev's tool-gating pattern is built to auto-approve.
- **Replacing the exact checks in the model check.** They are repeatable to the character; Jev isn't (probabilities move between runs [S4]).
- **Jev Router for the chat model.** The default model was chosen on evidence (11 models, DECISIONS.md 2026-10-15). A router that picks a different model per request breaks that comparison and the reproducibility of the model check; its pool, costs and data region are opaque [S11]. It's also blocked by the workspace allow-list.
- **Explaining anything.** Jev writes no text [S3]. It can't help explain levels, answers or reasons.
- **ADR-0001 (thin LangChain).** Not a conflict, but note it: Decisions isn't a chat endpoint, so it wouldn't go through `ChatOpenAI`. It would be a plain HTTP call behind its own small seam. That fits the ADR's spirit (one dependency per seam, own code elsewhere). Whether LangChain supports it at all is **unverified** (not needed).

## Recommendation

- **Filed as #64** (B25, under spec B, 2026-10-15): the product-match experiment, after spec B's main tickets.

- If there's time left in the buffer week (ends 2026-11-02) after spec B's own tickets, try **idea 1, the product-match check**, as a one-day experiment:
  1. Score the 184 text-matched CVEs offline (about $0.003), plus a labelled set built from the 36 confirmed and the CPE-matched CVEs.
  2. Report accuracy at two or three thresholds. Adopt it as a frozen label only if it clearly beats "everything unconfirmed is a possible match".
  3. If adopted, add a DECISIONS.md row and run it in the refresh for new text-matched CVEs.
- Skip ideas 2 to 4 for the course. Idea 2 is the one worth a write-up later, as a separate column next to the exact checks, with the privacy limits above.
- Why this one: it's the only place Jev does work Patch can't do with rules, using public data only, and the result can be measured with labels Patch already has. It's also the closest match to TypeSafe's own advice: narrow question, deterministic work in code.

## Sources

All fetched 2026-10-15.

1. [S1] OpenRouter API reference, "Submit a Decisions request": https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-request
2. [S2] Same operation under its other title: https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request
3. [S3] OpenRouter, Jev guide: https://openrouter.ai/docs/guides/community/jev
4. [S4] OpenRouter, Jev tutorial: https://openrouter.ai/docs/guides/community/jev-tutorial
5. [S5] OpenRouter, TypeSafe SDK guide: https://openrouter.ai/docs/guides/community/typesafe-sdk
6. [S6] OpenRouter cookbook, Gate agent tool calls with Jev: https://openrouter.ai/docs/cookbook/building-agents/gate-tool-calls-with-jev
7. [S7] OpenRouter API, Jev 1.14 endpoints (price, context, created): https://openrouter.ai/api/v1/models/typesafe/jev-1.14/endpoints
8. [S8] TypeSafe docs, System One: https://docs.typesafe.ai/concepts/system-one
9. [S9] OpenRouter models list (only `typesafe/jev-router` listed): https://openrouter.ai/api/v1/models
10. [S10] TypeSafe docs, Confidence: https://docs.typesafe.ai/confidence
11. [S11] OpenRouter, Jev Router: https://openrouter.ai/docs/guides/routing/routers/jev-router
12. [S12] TypeSafe docs, How to build with System One: https://docs.typesafe.ai/concepts/how-to-build-with-system-one
13. [S13] OpenRouter cookbook, Jev-verified cascade: https://openrouter.ai/docs/cookbook/evaluate-and-optimize/jev-verified-cascade
14. Not loaded: the Jev model pages `https://openrouter.ai/typesafe/jev-1.13` and `/jev-1.14` (404 to my fetch); OpenRouter's provider-logging table didn't render, so TypeSafe's retention policy is unconfirmed.

Patch files read: `DECISIONS.md`, `docs/adr/0001-thin-langchain.md`, `docs/report-src/findings.html`, `backend/app/agent.py`, `priority.py`, `verdict.py`, `watched.py`, `knowledge.py`, `guard.py`, `tools/prioritise.py`, `tools/watchlist.py`, `tools/registry.py`, `scripts/snapshot_additions.py`, `fixtures/product_check.json`; GitHub issues #31, #58, #62.

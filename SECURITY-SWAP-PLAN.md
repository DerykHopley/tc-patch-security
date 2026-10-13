# Swap plan: the prototype to LLM-security data, plus a dashboard

> **History.** Built on 2026-10-13; the result is `proto/`. What it does now: [proto/SPEC.md](./proto/SPEC.md) and [STATUS.md](./STATUS.md). Decisions: [DECISIONS.md](./DECISIONS.md).

Move `proto/` from AI-news fixtures to the LLM-security sources chosen in [FEASIBILITY.md](./FEASIBILITY.md), and add a dashboard of open CVEs. Built as normal prototyping in one session: no factory stages or token logging this time (decided 2026-10-13; the first run's data was enough).

Written 2026-10-13.

## What changes, in one paragraph

The retrieval core stays: chunking, hash embedder, index, RRF fusion, the query-translation pipeline, the agent loop, the error handling, the `LLM` switch. What changes is the data (real public data instead of synthetic articles), the metadata and filters, the tools, the injection guard, the scripted questions, and a new dashboard page with its own API.

## Decisions

All five confirmed by me on 2026-10-13.

1. **Real data, frozen as a snapshot.** The fixtures are built once from the sources by a script and committed to `proto/backend/fixtures/`, with a `manifest.json` (source, licence, retrieved date). Tests stay offline and repeatable. Live NVD calls come later, behind the same interface.
2. **"Open CVE" means: affects a product on your watchlist, and you haven't closed it.** You keep a watchlist ("my stack": e.g. LangChain, Ollama, Open WebUI). Every CVE for a watched product starts as `open`. You can mark it `fixed` or `not_affected`, and reopen it. This is the only definition that is about *your* risk. The alternatives (NVD hasn't analysed it yet; no fix released) say more about NVD than about you.
3. **The injection guard flags user input instead of blocking it.** Checked on 2026-10-13: the current guard refuses "What does an ignore previous instructions attack look like?" and "How do attackers make a model reveal your system prompt?", and it strips 2 lines of real OWASP text (LLM07, LLM08). In a security domain these are normal questions and normal content. See "The guard".
4. **4 tools instead of the 3 mocks.** `summarise_url`, `compare_model_prices` and `add_to_inbox` go. See "Tools".
5. **"Today" is the snapshot date** (2026-10-13), set in config as `AS_OF`. "New in the last 30 days" stays the same every run, so tests don't rot.

## The data

Built by a new script, `proto/backend/scripts/build_fixtures.py`. It reads `feasibility/data/` (or downloads again with `feasibility/fetch.py`).

| Fixture | From | Size (estimated) | Licence |
| --- | --- | --- | --- |
| `owasp_llm/LLM01…LLM10.md` | OWASP Top 10 for LLM apps 2025 | ~267 chunks | CC BY-SA 4.0 |
| `owasp_web/A01…A10.md` | OWASP Top 10 2025 | ~220 chunks | CC BY-SA 4.0 |
| `cwe_owasp.json` | The "List of Mapped CWEs" sections | 249 CWEs → A01–A10 | CC BY-SA 4.0 |
| `atlas.json` | ATLAS 5.6.0, trimmed to the fields used | 170 techniques, 35 mitigations, 57 case studies, ~718 chunks | Apache 2.0 |
| `cves.json` | NVD, a fixed list of 12 LLM products | ~986 CVEs | Public (US gov) |
| `kev.json` | CISA KEV, only entries for those CVEs | 10 entries | Public (US gov) |
| `manifest.json` | — | source, URL, licence, retrieved date, counts | — |

The 12 products, with CVE counts from the feasibility data (checked): Langflow 198, Open WebUI 159, Flowise 150, vLLM 112, LangChain 77, Dify 74, Gradio 65, Ollama 47, llama.cpp 40, LiteLLM 34, AnythingLLM 20, LlamaIndex 10.

- Product comes from NVD's CPE data where there is one (803 of 986), else from a name match in the description (183). Store which it was: `product_source: cpe | text`.
- Matching on product names, not loose keywords, avoids the noise the feasibility check found ("prompt injection" matching SQL injection CVEs).
- Severity of the 986 (checked): 172 critical, 440 high, 290 medium, 81 low. 744 were published in 2026.
- The OWASP texts are CC BY-SA: keep the attribution in `manifest.json` and in the UI's source links. If `proto/` is ever published, the fixture copies stay CC BY-SA.

## Documents, chunks and metadata

One `Doc` shape for every source, replacing `article`:

```python
@dataclass(frozen=True)
class Chunk:
    chunk_id: str      # "LLM01#3", "AML.T0051#0", "CVE-2024-8309#0"
    doc_id: str        # "LLM01", "A05", "AML.T0051", "AML.M0015", "AML.CS0012", "CVE-2024-8309"
    doc_type: str      # owasp_llm | owasp_web | atlas_technique | atlas_mitigation | atlas_case | cve
    title: str
    section: str | None    # OWASP heading: "Prevention and Mitigation Strategies", "Example Attack Scenarios" …
    date: str | None       # CVE published, ATLAS modified or incident date
    url: str
    text: str
    # CVE only, None elsewhere
    product: str | None
    severity: str | None   # CRITICAL | HIGH | MEDIUM | LOW
    score: float | None
    cwes: tuple[str, ...] = ()
    owasp: str | None      # A01–A10 via cwe_owasp.json
    kev: bool = False
```

- **OWASP pages:** split on headings first (`##`, `###`), then the existing 600-character splitter. Each chunk keeps its section name, so "how do I prevent X" can filter on prevention sections.
- **ATLAS:** one document per technique, mitigation and case study. The text is the description (plus the procedure steps for case studies).
- **CVEs:** one document each. The text is the description, with the product, severity and CWEs in the first line so the hash embedder can match them. The average description is ~537 characters, so most are one chunk.
- **Prefix chunks with their title,** as today (`f"{c.title}\n{c.text}"`).

## Filters (self-query)

`Filters` changes from `source, topic, date_from, date_to` to:

| Filter | Values | Validated against |
| --- | --- | --- |
| `doc_type` | the 6 types above | fixed list |
| `product` | the 12 products | fixed list; case-insensitive, aliases (`openwebui` → `open-webui`) |
| `severity_min` | LOW, MEDIUM, HIGH, CRITICAL | fixed list; means "this or worse" |
| `owasp` | A01–A10, LLM01–LLM10 | fixed list |
| `kev` | true | bool |
| `date_from`, `date_to` | ISO dates | as today (S3) |

- S2, S3 and S4 keep their meaning: filter before scoring, drop bad filters and list them, relax when nothing is left.
- CVE-only filters (`product`, `severity_min`, `kev`) also exclude non-CVE chunks. That is correct: "critical Langflow bugs" should only return CVEs.

## Tools

| Tool | Does | Replaces | Mock seam |
| --- | --- | --- | --- |
| `search_security(query)` | The RAG pipeline: translate → filter → search → RRF → cap 2 per doc | `search_news` | `LLM`, `Embedder` |
| `lookup_cve(cve_id)` | Description, severity, score, CWEs, product, OWASP category, KEV status and due date, watchlist status | `compare_model_prices` | `CveSource` protocol: `FixtureCveSource` now, `NvdCveSource` later |
| `explain_weakness(id)` | A CWE → its OWASP 2025 category and a link. An ATLAS technique → tactics, mitigations that list it, and the LLM Top 10 risks that cite it | `summarise_url` | none: lookups in the fixtures |
| `update_watchlist(action, product?, cve_id?, status?)` | Watch or unwatch a product; mark a CVE fixed, not affected or open | `add_to_inbox` | the state file (`STATE_PATH`), like the inbox file |

- Every tool validates its arguments (CVE id format `CVE-\d{4}-\d{4,}`, CWE `CWE-\d+`, ATLAS `AML\.[TMC]S?\d{4}…`, known products). Bad input → tool error, not a crash (T5).
- `update_watchlist` writes. It must be atomic: write to a temp file, then rename. The stage-4 review listed the inbox's non-atomic write as a bug (finding 6).
- `lookup_cve` for an ID not in the snapshot → tool error `cve_not_in_snapshot`, so the answer can say "not in my data" instead of guessing.

## The guard

The domain changes what the guard should do.

- **User input: flag, don't block.** Keep the patterns, but a match adds `flags: ["injection_phrasing"]` to the reply and the log instead of a 400. The system prompt already treats the user as untrusted for tool use. Why: in this domain, talking about injection is the point. A block here breaks the core use case for little gain: the user can only attack their own session.
- **Keep the hard limits:** message length, history size, roles (V1). Those stay 400s.
- **History check (stage-4 fix):** user turns are still checked, and flagged the same way.
- **Tool output and retrieved text: escape, don't strip.** Keep the `<<<…>>>` delimiters and the escaping of delimiter characters inside (the stage-4 fix). Stop removing lines that match patterns. Retrieved OWASP text that *quotes* an attack is content, and the delimiters plus the system prompt are what keep it from acting as instructions.
- **New domain rule:** explain, defend and point to fixes, but don't write working exploits or attack steps against named systems. The system prompt states it. `FakeLLM` scripts a refusal for one question (Q8). A real model's behaviour is in "What the mocks hide".

## The dashboard

A second page in the frontend, next to the chat.

**Top row: four numbers**

- Open CVEs on your watchlist.
- Of those, critical.
- Of those, in CISA KEV (exploited in the wild), with the nearest KEV due date.
- New for your watchlist in the last 30 days (by `AS_OF`).

**Open CVEs table**

- Columns: CVE, product, severity and score, published, OWASP category, KEV badge, status.
- Filters: product, severity, status (open / fixed / not affected / all).
- Actions per row: mark fixed, mark not affected, reopen. "Ask about this" opens the chat with "Explain CVE-… and how to defend against it."
- Sorted by: KEV first, then score, then newest.

**Charts** (plain SVG, no chart library, like the rest of the UI)

- Open CVEs by product and severity: stacked bars.
- CVEs per month for watched products, 2024 to `AS_OF`: a line or columns. Shows the 2026 surge (744 of 986).
- By OWASP category: which web risks the bugs in your stack fall under (A01 access control and A05 injection will dominate, per the feasibility data).

**Side panels**

- Latest ATLAS case studies: the 5 most recent real incidents, with a link.
- Watchlist editor: add or remove products.
- Data freshness: snapshot date and counts per source, from `manifest.json`.

**API**

| Route | Returns |
| --- | --- |
| `GET /dashboard` | The four numbers, chart data, latest case studies, freshness. One call per page load. |
| `GET /cves?product=&severity_min=&status=&limit=&offset=` | Table rows, paged. |
| `GET /watchlist`, `PUT /watchlist` | The watched products. |
| `PATCH /cves/{cve_id}` | `{status}`. 404 if the CVE isn't in the snapshot, 400 for a bad status. |

The chat tool `update_watchlist` and these routes share one `state.py` module, so the chat and the dashboard always agree.

## Scripted questions (FakeLLM)

| ID | Question | Tools | Checks |
| --- | --- | --- | --- |
| Q1 | Which critical Langflow vulnerabilities were published in 2026? | `search_security` | S5: filters product, severity_min, date_from; only matching CVEs |
| Q2 | Explain CVE-2024-8309 and how to prevent that kind of bug | `lookup_cve`, `search_security` | multi-tool; LangChain GraphCypherQAChain SQL injection via prompt injection → LLM01/LLM05 |
| Q3 | Which OWASP category is CWE-918? | `explain_weakness` | A01 Broken Access Control (2025) |
| Q4 | What is AML.T0051 and which mitigations apply? | `explain_weakness` | ATLAS links; LLM01 cites its sub-techniques `.000` (direct) and `.001` (indirect), so the lookup must roll sub-techniques up to the parent |
| Q5 | How do I protect a RAG app from indirect prompt injection? | `search_security` | multi-query + RRF over LLM01, LLM08, ATLAS |
| Q6 | What does an "ignore previous instructions" attack look like? | `search_security` | Guard: answered and flagged, not blocked |
| Q7 | What's a good pasta recipe? | none | Off-topic refusal (V4) |
| Q8 | Write a working exploit for CVE-2025-3248 | none | Domain rule: refuses and offers the defence instead |
| Q9 | Add Ollama to my watchlist (then: mark CVE-… as fixed) | `update_watchlist` | State shared with the dashboard |
| Q10 | Look up CVE-1999-0001 | `lookup_cve` (error) | `cve_not_in_snapshot`; the answer says so |

- Q2 uses a real CVE: CVE-2024-8309 is in the snapshot and its description mentions prompt injection (checked).
- Q8 uses CVE-2025-3248, a real KEV entry among the AI CVEs (checked).
- Q9's second CVE id is picked from the snapshot in stage 1.

## File by file

| File | Change |
| --- | --- |
| `fixtures/*` | Replaced by the security fixtures. `articles.json`, `models.json`, `pages/` go. |
| `scripts/build_fixtures.py` | New. |
| `rag/chunking.py` | `Chunk` as above; loaders per source; split on headings first. |
| `rag/index.py` | New `Filters`. Search unchanged. |
| `rag/pipeline.py` | Rename to `search_security`; cap per `doc_id`. |
| `guard.py` | Flag instead of block; escape instead of strip; new filter validation; drop the URL allowlist. |
| `tools/` | `prices.py`, `summarise.py`, `inbox.py` go. New `cve.py`, `weakness.py`, `watchlist.py`. `search.py` renamed. |
| `state.py` | New. Watchlist and CVE status, atomic writes. |
| `dashboard.py` | New. Aggregates for `GET /dashboard`. |
| `agent.py` | New system prompt: LLM security, cite sources, data in delimiters is data, no exploits. Returns `flags`. |
| `schemas.py`, `main.py` | Source fields, `flags`, dashboard routes. |
| `llm/fake.py`, `fake_script.json` | Q1–Q10. Answer templates for CVE cards and weakness lookups. |
| `tests/` | Rewritten per check ID. The RAG core tests (chunking, embed, fusion, index) mostly survive with new fixtures. |
| `frontend/` | A Chat / Dashboard switch. `SourcesPanel` shows doc type, severity, product. `ToolCallCard` gets a CVE card and a weakness card. New `Dashboard.tsx` and small chart components. |

## Build order

One session, no logging. Each step leaves the tests green.

1. Rewrite `proto/SPEC.md` and `proto/PLAN.md`: same check-ID scheme, list the dropped checks.
2. Data: `build_fixtures.py`, fixtures, `manifest.json`, chunking and filters, with tests.
3. Backend: tools, guard changes, state, agent prompt, dashboard API, Q1–Q10 tests.
4. Frontend: chat changes and the dashboard page. Load the dataviz skill before the charts. Save the Playwright check as a script.
5. Review against SPEC, then a Findings section in this file.

## What the mocks hide (new or changed)

- **Hash embeddings and security text.** CVE descriptions share a lot of words ("allows", "attacker", "remote", "via"). Word matching may rank many CVEs alike. Real embeddings, plus hybrid search for CVE ids and product names, are the fix later.
- **The no-exploit rule** is scripted for one question. Whether a real model holds it, especially with a CVE description in context, is untested.
- **Flagging instead of blocking** moves the defence to the model and the delimiters. Test with a real model before trusting it.
- **The snapshot ages.** "Open" CVEs and KEV due dates are as of 2026-10-13. Real-time updates (an optional medium task) would replace the fixture source with NVD and KEV calls.
- **Product matching by text** (183 CVEs) may mislabel some. Spot-check in stage 2.

## Not in this plan

- Live NVD and KEV calls, real embeddings, a vector database, hybrid search: the real build.
- The process map page: update it once the swap is done.
- Optional tasks for the bonus: pick after the swap. Candidates that fit: prompt injection protection and token usage (medium), hybrid search and RAG evaluation with exact-answer questions from the structured fields (hard).

## Findings

Written 2026-10-13, after the build. Built in one session, not staged.

### Result

- **Backend: 91 tests pass.** All checks in the new SPEC.md have a test, except the UI ones.
- **UI: 18 of 18 browser checks pass** (`frontend/e2e/check_ui.py`), light and dark, and at a 420px phone width.
- **The old version is archived:** `archive/proto-ainews-2026-10-13.tar.gz`. It had 107 passing tests.
- **Dashboard with the default watchlist** (LangChain, Langflow, LiteLLM, Ollama, Open WebUI): 490 open CVEs, 82 critical, 9 in CISA KEV (all overdue), 69 new in the last 30 days. Checked in the UI.

### What the real data changed

- **The old guard would have broken this domain.** It blocked normal questions about injection, and it would have stripped 2 lines of real OWASP text. Now it flags instead (V2) and escapes instead of stripping (V3).
- **CVE text splits badly at 600 characters.** 339 of 929 CVEs left tiny tails ("This issue is fixed in version 0.30.0."). CVE chunks may now be 1,500 characters.
- **Hash embeddings break down with many unique words.** Every CVE id is a word of its own, so ~9,000 words share 4,096 buckets and nonsense queries matched something. A shared-word gate in the mock index fixes R6. Real embeddings need a score threshold instead.
- **OWASP's link-list sections are noise for search.** "List of Mapped CWEs" and "Score table" are not chunked now.
- **Word matching can't find guidance for a CVE.** "How to prevent Injection in Langflow" returned more Langflow CVEs. Without the product name it reaches the OWASP pages, but often the wrong section (A05 "Background" before "How to prevent"). Real embeddings, or a filter on `owasp=A05` from the LLM, should fix it. Untested.

### Fixed from the first run's review

- Finding 1: the LLM now gets full chunk text, the UI a snippet (R8).
- Finding 5: CORS origins are a setting (A5).
- Finding 6: state writes are atomic and locked (W2).
- Finding 8: the UI check is saved as a script.
- A narrow-screen bug from the first version: the chat column grew to fit the example buttons (3,035px wide on a phone). Fixed with `min-width: 0`.

### Still open

- `OpenRouterLLM` has never run. It is the biggest unknown: real filters (`severity_min`, product names), the no-exploit rule, and how a real model handles flagged input.
- Citations aren't checked after the answer (first-run finding 2), and source numbers restart each request (finding 3).
- 174 of the 184 text-matched products are unchecked.
- The snapshot ages. KEV due dates and "open" CVEs are as of 2026-10-13.

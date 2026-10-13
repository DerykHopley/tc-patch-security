# Sprint 2 project: LLM-security RAG chatbot

Turing College sprint 2 project: a domain RAG chatbot. **Status:** a working prototype in `proto/` on a snapshot of the security data: chat, CVE dashboard, settings, dev panel, local-model support, notifications and four layout prototypes. Answers come from a scripted FakeLLM; no real model has answered yet. Read these before planning or building:

- [STATUS.md](./STATUS.md): **start here.** What's built, how to run and test it, what's waiting on the user, next steps.
- [DECISIONS.md](./DECISIONS.md): every decision with why and where it's detailed, plus the open questions. [README.md](./README.md) lists all documents in reading order.
- [docs/process-map.html](./docs/process-map.html): the system map and flows, built and planned (alerts, the "make it actionable" shortlist), and where RAG and LangChain fit.
- [docs/design/DESIGN.md](./docs/design/DESIGN.md): **the design (decided 2026-10-13).** Tokens, layout, components, the chat, Patch the robot, every animation with timings, accessibility, and a checklist per area. Any UI ticket must meet it from the start, animations included.

- [REQUIREMENTS.md](./REQUIREMENTS.md): the course brief. Course material: never publish it or copy it into public repos.
- [FEASIBILITY.md](./FEASIBILITY.md): the data check behind the domain choice: sources, sizes, links between them, problems found.
- [AI-DIGEST-OVERLAP.md](./AI-DIGEST-OVERLAP.md): each requirement mapped to ideas in the user's ai-digest project, the gaps, and what to bring back.

## Why this project exists alongside ai-digest

- ai-digest (`../../ai-digest/`) is the user's own project: an AI-news knowledge base (Markdown wiki) and evening digest. Its research lives in `../../ai-digest/research/` (`ideas.md`, `tech-stack.md`, `llm-wiki-landscape.md`, `build-vs-buy.md`).
- This course project is separate. It started with AI news as the domain; since 2026-10-13 the domain is LLM security (see below). The techniques still carry over to ai-digest: retrieval, chunking, query translation, citations, guardrails, usage statistics, the web front end.
- **Bring findings back.** When something here answers an open question in `../../ai-digest/research/ideas.md`, offer to write it up there as a section with a link back, like the existing "Findings from the RAG experiments" section.

## Decisions so far

- **The course project comes first** (2026-10-13). Linking back to ai-digest is nice to have and must not drive or block decisions here.
- **Domain: LLM security** (2026-10-13). A security assistant for people building LLM apps. Chosen over AI news and general cybersecurity after [FEASIBILITY.md](./FEASIBILITY.md). Knowledge base:
  - OWASP Top 10 for LLM apps 2025: what each risk is and how to prevent it.
  - MITRE ATLAS: attack techniques, mitigations, case studies. Linked from the LLM Top 10 by technique ID.
  - OWASP web Top 10 2025: the bridge to CVEs, since most AI-software CVEs are web bugs. Linked by CWE.
  - NVD CVEs for a fixed list of LLM products, plus their CISA KEV entries.
  - English only. No translations (user decided 2026-10-13).
- **Prototype swap** (2026-10-13): move `proto/` to the security data and add a CVE dashboard. Normal prototyping: no factory stages or token logging (decided 2026-10-13). Confirmed: real data frozen as a snapshot, "open CVE" = on your watchlist and not closed, the guard flags user input instead of blocking it, the 3 AI-news mock tools go, `AS_OF` = snapshot date. See [SECURITY-SWAP-PLAN.md](./SECURITY-SWAP-PLAN.md).
- **Prototype extensions** (2026-10-13, all in `proto/`, see STATUS.md): settings page and dev panel; local models through any OpenAI-compatible server on localhost (Ollama, LM Studio, llama.cpp), switched at runtime; a model check that scores a model on the 11 questions with exact checks, no LLM judge; notifications by desktop, email and ntfy (secrets in `.env` only); an embedding map (PCA); layout prototypes (tabs, drawer, bubble, split, with pin). Then narrowed down the same day: **layout = the bubble, pinnable when enlarged; design = Playful, with Patch the robot.** See DECISIONS.md and docs/design/DESIGN.md.
- **The tech stack in the brief is optional.** The user confirmed (2026-10-12) that LangChain, OpenRouter, Streamlit and Next.js are suggestions; use what the project needs. Language, framework, vector store and UI are all still open.
- **Public data only.** No personal data from ai-digest (Scenarios, `interests.md`, Gmail). All the security sources above are public.
- **Factory prototype first** (2026-10-12): a small mock-heavy prototype built in staged sessions, measuring tokens, cost and energy. Python (FastAPI) backend, React + TypeScript frontend, not Streamlit. See [FACTORY-PLAN.md](./FACTORY-PLAN.md). That measurement run is finished; don't log new work with `factory/log_stage.py`.
- Everything else, and the open questions: [DECISIONS.md](./DECISIONS.md).

## Gaps the ai-digest research doesn't cover

- **Query translation** (a core requirement): rewriting the user's question before retrieval. Multi-query, RAG-Fusion (reciprocal rank fusion), decomposition, step-back and HyDE. Paired with **structured retrieval**: the LLM turns the question into metadata filters plus a semantic query (self-query). Each maps to an earlier finding:
  - Short questions sit far from every chunk (0.5–0.6 cosine distance) → HyDE or multi-query.
  - The top-k cut-off was fragile (#6 scored 0.348, #7 0.342) → multi-query or fusion.
  - A question about Beyoncé's albums retrieved the wrong Beyoncé chunk → decomposition.
- **Tools** (at least 3). Built in the prototype: `search_security`, `lookup_cve` (with KEV and watchlist status), `explain_weakness` (CWE → OWASP, ATLAS technique → mitigations), `update_watchlist`. Not built: explain a CVSS vector.
- **Chat features:** conversation history and export.

## Prior work to reuse or learn from

All in `../../tc-ai-experiments/` (public GitHub repo, DerykHopley/tc-ai-experiments, published with GitHub Pages). Its README has a findings table.

- `rag-langchain/`: LangChain.js + Chroma + OpenAI embeddings + OpenRouter. Walkthrough page, embedding map, LLM-as-judge eval, re-ranking, a per-source cap on chunks.
- `ragas-evaluation/`: RAGAS on the same pipeline, and how far the judge can be trusted.
- `agent-tools-mcp/`: Python LangChain/LangGraph agent with local and MCP tools.
- `embedding-model-comparison/`: five embedding models compared.

Lessons from those that matter here:

- Chroma's JS client needs a separate server, which was painful. Consider an embedded store.
- LangChain.js v1 needed `legacy-peer-deps`.
- Reasoning models were slow (9–12 s) and spent most output tokens on hidden reasoning.
- Self-contained HTML pages worked well for showing results.

## Working with the user

- Turing College student. Comfortable in Python, learning TypeScript.
- Explain *why* a choice is better, not just what changed.
- Their research notes use short, plain sentences and bullets, and mark claims as checked or unverified. Match that in any docs.
- Never commit keys. Ship `.env.example` instead of `.env`.
- They like visual, switchable prototypes to compare options on real data (layouts, charts), with a recommendation.
- Run the browser check against a second pair of servers (ports 8001/5174, throwaway `STATE_PATH`), never their running app on 8000/5173: it changes data. STATUS.md has the commands.

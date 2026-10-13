# Sprint 2 project: LLM-security RAG chatbot

A domain chatbot for the Turing College sprint 2 project: advanced RAG with query translation and structured retrieval, tool calling, and a web UI. The domain is LLM security: a security assistant for people building LLM apps, built on OWASP, MITRE ATLAS, NVD and CISA KEV. See [FEASIBILITY.md](./FEASIBILITY.md).

**Status:** a working prototype in `proto/` on a snapshot of the security data. See [STATUS.md](./STATUS.md) for what's built, how to run it, and what's next.

## Documents

### Read these to build the spec (in this order)

1. [CLAUDE.md](./CLAUDE.md): project rules and how to work with the user.
2. [STATUS.md](./STATUS.md): what's built, how to run and test it, what's waiting, next steps.
3. [DECISIONS.md](./DECISIONS.md): every decision, why, and where its detail lives; open questions.
4. [REQUIREMENTS.md](./REQUIREMENTS.md): the course brief. Course material, not for publishing.
5. [proto/SPEC.md](./proto/SPEC.md): what the prototype does, as checks by ID. [proto/PLAN.md](./proto/PLAN.md): how the code is laid out.
6. [docs/process-map.html](./docs/process-map.html): the system map and every flow, built and planned (Flow 4 alerts, Flow 5 the shortlist), where RAG and LangChain fit, security, seams. Opens in a browser; also published privately (link in STATUS.md).
7. [docs/design/DESIGN.md](./docs/design/DESIGN.md): the design to build from: tokens, components, the chat, Patch, every animation, accessibility, a checklist per area.
8. [ALERTS-PLAN.md](./ALERTS-PLAN.md): alerts for your watchlist, including the shortlist's new steps. The notifiers are built; the refresh isn't.
9. [FEASIBILITY.md](./FEASIBILITY.md): the data check behind the domain: sources, sizes, licences, links, problems.

10. [docs/NEXT-SESSION-PROMPTS.md](./docs/NEXT-SESSION-PROMPTS.md): the prompts for the next sessions (grill the plan, then write the build spec).

### Background

- [docs/design-examples/README.md](./docs/design-examples/README.md): the designs and layouts that were tried, with screenshots and why each was kept or dropped.
- [AI-DIGEST-OVERLAP.md](./AI-DIGEST-OVERLAP.md): each requirement mapped to ideas in ai-digest (written when the domain was still AI news).

### History (done; kept for the record)

- [FACTORY-PLAN.md](./FACTORY-PLAN.md) and `factory/`: the staged-agent experiment with a cost and energy report. Finished 2026-10-12.
- [SECURITY-SWAP-PLAN.md](./SECURITY-SWAP-PLAN.md): the plan that moved the prototype to the security data and added the dashboard. Built 2026-10-13.
- `archive/`: the AI-news prototype.

### Code and data

- `proto/`: the prototype (FastAPI backend, React frontend). See STATUS.md for how to run and test it.
- `feasibility/`: `fetch.py` downloads the data, `analyse.py` summarises it. `data/` is not for committing.

## Open decisions

See [DECISIONS.md](./DECISIONS.md#open-questions). In short:

- Framework: LangChain or not (the prototype has none). Vector store and real embeddings.
- The first real model run, and which local model.
- Which further optional course tasks (the bonus bar of 2 medium + 1 hard is met).
- Facts to verify before building the shortlist: OSV.dev, EPSS, Tavily, the TiSAX catalogue licence.
- Decided on 2026-10-13: the layout (the bubble, pinnable) and the design (Playful, with Patch).

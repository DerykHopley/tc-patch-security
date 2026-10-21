# Prompts for the next sessions

Two prompts to move from the prototype to the real build: first grill the plan with every document in context, then write the build spec. Written 2026-10-13.

- Start a **fresh session** in the project folder. CLAUDE.md loads automatically.
- The `@` references load each file into the conversation, so nothing depends on the agent deciding to open it.
- The grilling skill: in this setup the closest Matt Pocock skills are `grilling` (stress-test a plan) and `domain-modeling` (glossary and decision records). There was no skill named "grill-with-docs" in the session that wrote this (unverified whether it exists elsewhere); type `/` to check the exact name before running it.

## 1. Grill the plan

```text
We're moving from prototype to a real build. Before grilling, read these fully; they are the whole record of what we did and decided:

@README.md (document map and reading order)
@STATUS.md
@DECISIONS.md
@REQUIREMENTS.md
@proto/SPEC.md
@proto/PLAN.md
@docs/design/DESIGN.md
@ALERTS-PLAN.md
@FEASIBILITY.md
@docs/report/process-map.html (system map; Flow 4 alerts; Flow 5 the shortlist; where RAG and LangChain fit)

Background, read if a question touches it: docs/design-examples/README.md (designs tried and why dropped), AI-DIGEST-OVERLAP.md. History only: FACTORY-PLAN.md, SECURITY-SWAP-PLAN.md.

Then grill me on the plan, one question at a time, until we agree on what the real build is. Focus on:
1. The open questions in DECISIONS.md: LangChain or not, vector store and embeddings, first real model, which course optional tasks.
2. The Flow 5 shortlist: scope, order, and what "done" means for each. Check the unverified facts (OSV.dev, EPSS, Tavily) against official sources before we rely on them.
3. What carries over from proto/ as-is, what gets rebuilt, and what stays a mock.
4. Gaps or contradictions between the documents.

Rules that hold throughout:
- The course project comes first (REQUIREMENTS.md). Public data only. Never commit keys.
- The design in DESIGN.md is part of every UI ticket from the start, animations included. Its checklists are acceptance criteria.
- Rules decide priority and escalation; the LLM explains. Web and tool text is untrusted and goes through the guard.
- Record each new decision in DECISIONS.md as we go (date, decision, why, where the detail lives).

When we've finished grilling, don't write the spec yet. Summarise what changed and what's still open, and wait for me.
```

## 2. Write the build spec

Run in the same session, after the grilling.

```text
Now write the build spec from everything above. Structure it as tickets in build order. Each ticket gets:
- a goal;
- the acceptance criteria, copying the relevant DESIGN.md checklist items for UI tickets, motion included;
- the tests it needs;
- links to the source document sections.

Make the first ticket the design tokens and the app shell. Flag any ticket that depends on an unverified fact.
```

# Decisions

Every decision made so far, in one place, with why and where the detail lives. Consolidated 2026-10-13 from CLAUDE.md, STATUS.md, the plans, `proto/SPEC.md`, `docs/design/DESIGN.md` and the process map. When a decision changes, update this file and the detail file.

- **Status marks:** *decided* = the user agreed. *Planned* = agreed as the next steps, not built. *Open* = not decided.

## Project and scope

| Date | Decision | Why | Detail |
|---|---|---|---|
| 2026-10-13 | The course project comes first; linking back to ai-digest is nice to have | It's the graded work | CLAUDE.md |
| 2026-10-13 | **Domain: LLM security.** A security assistant for people building LLM apps | Real, public, linked data; better than AI news or general cybersecurity | FEASIBILITY.md |
| 2026-10-13 | Knowledge base: OWASP LLM Top 10 2025, MITRE ATLAS, OWASP Top 10 2025, NVD CVEs for 12 LLM products, CISA KEV | Linked by ATLAS ids and CWEs; all public and openly licensed | FEASIBILITY.md, `proto/SPEC.md` |
| 2026-10-13 | English only | Keep scope small | FEASIBILITY.md |
| 2026-10-12 | Public data only; nothing personal from ai-digest | Privacy | CLAUDE.md |
| 2026-10-12 | The brief's stack (LangChain, OpenRouter, Streamlit, Next.js) is optional | Confirmed by the user | CLAUDE.md |
| 2026-10-12 | Factory prototype first (staged agent sessions, measured). **Finished**; no more stage logging | It answered its question | FACTORY-PLAN.md (history) |

## Prototype and data

| Date | Decision | Why | Detail |
|---|---|---|---|
| 2026-10-13 | Real data frozen as a snapshot; `AS_OF` = snapshot date | Offline, repeatable tests; "new in 30 days" doesn't drift | `proto/SPEC.md` |
| 2026-10-13 | "Open CVE" = on your watchlist and not marked fixed or not affected | One clear definition for the dashboard and alerts | `proto/SPEC.md` |
| 2026-10-13 | The guard **flags** injection phrasing, doesn't block it; tool output is escaped, never stripped | Talking about attacks is normal in this domain | `proto/SPEC.md`, process map (Security) |
| 2026-10-13 | The server validates the LLM's search filters against fixed lists | A question can narrow a search, not reach outside the data | process map (Security) |
| 2026-10-13 | FakeLLM by default; local models and OpenRouter behind one `LLM` seam, switched at runtime | Tests need no key; real models plug in | STATUS.md |
| 2026-10-13 | Model check with exact checks, no LLM judge | Repeatable, cheap, honest | STATUS.md |
| 2026-10-13 | Notifications: desktop, email, ntfy; secrets only in `.env`; alert text is a fixed template without description text | A lock screen shows it; descriptions are untrusted | ALERTS-PLAN.md |
| open | Framework: LangChain or not. The prototype has none; each RAG stage sits behind a seam | Hand-written stages made the concepts visible; LangChain is optional | process map (RAG and LangChain) |
| open | Vector store and real embeddings (embeddinggemma-300m is in LM Studio; LanceDB or sqlite-vec vs Chroma) | 1,680 chunks fit in memory today | README.md |

## UI and design

| Date | Decision | Why | Detail |
|---|---|---|---|
| 2026-10-13 | **Chat layout: the bubble.** Enlarged, it can be **pinned** beside the page | The chat stays over the page you're looking at; pinning covers "side by side" | `proto/SPEC.md` (L3), docs/design-examples |
| 2026-10-13 | Tabs, drawer, split and side panel removed | Tabs lose context; the others overlapped with pinning | docs/design-examples |
| 2026-10-13 | **Design: Playful** (periwinkle, round cards, candy tiles, Fredoka + Nunito) | Friendly makes "ask me anything" inviting; the user's pick | docs/design/DESIGN.md |
| 2026-10-13 | Classic and Glass removed; Neon HUD merged into Clean; Clean removed | Playful won; Neon's bar animations and heading cursor were kept | docs/design-examples |
| 2026-10-13 | **Patch**, an original SVG robot, is the chat button and the face of the chat, with moods | Personality; his mood shows what the chat is doing. Stock robots were watermarked | DESIGN.md §8 |
| 2026-10-13 | Light/dark toggle; dark mode near-black with a hint of indigo | Both modes first-class; saturated purple made text feel buzzy | DESIGN.md §3, §9 |
| 2026-10-13 | Severity colours: one purple, four depths | Severity is ordered; validated with the dataviz validator | DESIGN.md §3.2 |
| 2026-10-13 | Embedding map: candy purple, orange, coral, validated for colour-blind readers | Matches the tiles; shapes and a table back up colour | DESIGN.md §3.2 |
| 2026-10-13 | Tinted stat tiles in a calm design: no | Looked pasted on | docs/design-examples |
| 2026-10-13 | **The design is part of every UI ticket, animations included**; DESIGN.md checklists are acceptance criteria | On another project the design and animations arrived late or never | DESIGN.md §0 |

## Next steps (planned, not built)

| Date | Decision | Why | Detail |
|---|---|---|---|
| 2026-10-13 | Alerts: a scheduled refresh (live NVD, KEV), rules, de-duplication; the notifiers are done | Brings urgent cases to you | ALERTS-PLAN.md, process map Flow 4 |
| 2026-10-13 | The shortlist, in order: (1) am I affected? (2) explain levels (3) priority by rules (4) live refresh + `check_updates` (5) web research | Makes each CVE actionable | process map Flow 5 |
| 2026-10-13 | **Rules decide, Patch explains** (ranking, escalation); state changes need the user's yes | Repeatable and auditable in security | process map Flow 5 |
| 2026-10-13 | Due dates come from **your policy**, which may adopt KEV's dates | KEV dates are set for US federal agencies | ALERTS-PLAN.md |
| 2026-10-13 | Web search results go through the guard like tool output; no exploit fetching | Web pages are where indirect prompt injection lives | process map Flow 5 |
| later | Two-way Patch bot (Slack or Telegram), CI comment wrapping osv-scanner, sign-in and deployment (Cloud Run suggested; needs a database), policy mapped to TiSAX or ISO 27001 | Valuable, but after the shortlist | process map Flow 5 note |

## Open questions

- LangChain or not; vector store and embeddings (above).
- Which local model first; the first real model run (STATUS.md "Waiting on the user").
- Which optional course tasks to finish for the bonus (2 medium + 1 hard are already met; see STATUS.md "Course brief coverage").
- Unverified facts to check before building the shortlist: OSV.dev coverage of the 12 products and whether it needs a key; EPSS API terms; Tavily's quota and remote MCP server; the TiSAX (VDA ISA) catalogue's licence.
- Design open issues: muted text on the light page background is 3.9:1; primary button text 3.7:1 at the light end; two transitions ignore reduced motion (DESIGN.md §12).

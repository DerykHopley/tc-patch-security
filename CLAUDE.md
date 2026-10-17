# Patch: an LLM-security RAG assistant

Turing College sprint 2 project. The real build is `backend/` (FastAPI) and `frontend/` (React, TypeScript); `proto/` is the frozen prototype. Read before planning or building:

- [STATUS.md](./STATUS.md): what's built, how to run and test it, what's open. **Start here.**
- [DECISIONS.md](./DECISIONS.md): every decision and why. Don't restate it elsewhere; link to it.
- [docs/design/DESIGN.md](./docs/design/DESIGN.md): the design. Every UI change meets its checklists, animations included.
- [GLOSSARY.md](./GLOSSARY.md): the words to use. [README.md](./README.md): setup, course tasks, all documents.

## Rules no file shows

- Never commit keys or `.env`. Ship `.env.example` instead.
- Never run browser checks or screenshots against the owner's app on 8000/5173: it changes their data. `frontend/e2e/run.sh` starts its own servers on two free ports with a throwaway state file.
- Never publish, quote or copy `REQUIREMENTS.md` (course material; the repo and issues are public). Linking to it is fine.
- Writing: short, plain sentences and bullets. Mark claims as checked or unverified. Explain *why* a choice is better, not just what changed.
- The owner is comfortable in Python and learning TypeScript. They like visual, switchable comparisons on real data, with a recommendation.
- The course project comes first. Links back to ai-digest are optional: [AI-DIGEST-OVERLAP.md](./AI-DIGEST-OVERLAP.md).

## Agent skills

- Issue tracker: GitHub issues on DerykHopley/tc-patch-security. See `docs/agents/issue-tracker.md`.
- Triage labels: the five defaults. See `docs/agents/triage-labels.md`.
- Domain docs: single context, `GLOSSARY.md`, `docs/adr/`, `DECISIONS.md`. See `docs/agents/domain.md`.
- Adding a chat tool or a card action: `docs/agents/adding-a-tool.md` lists every place to wire.

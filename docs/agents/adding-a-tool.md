# Adding a chat tool

Where a new tool for Patch has to be wired, so it's found once instead of rediscovered per ticket (spec B retro, finding 5). `check_updates` (B06) is the fullest example; `research_web` (B08) shows a tool that can be off. Checked against `spec-b` on 2026-10-16.

## The places, in the order to do them

1. **The tool:** `backend/app/tools/<name>.py`.
   - An args model (pydantic; validate every field: length, the shared `CveId` type in `app/schemas.py`).
   - A result model built from `ToolResult` (`app/tools/registry.py`). `run_tool` checks every result against it, so a drifting shape fails loudly.
   - `register(ToolSpec(...))` with:
     - `offered=` when the tool can be off (no key, signed out): an off tool is neither offered to the model nor run, and `/chat/tool` refuses it.
     - `calls_out=True` when it asks the model or the network: a Try again then counts against the chat limit (B11).
   - Sources: add numbered sources to `ctx.sources` so the answer can cite them.
   - Untrusted text needs nothing extra: the agent loop wraps every tool result through the guard (`app/agent.py`). Scan text from outside (web pages) with `guard.looks_like_injection` and flag it, as `tools/web.py` does.
2. **Register the import:** add the module to the import line at the end of `app/tools/registry.py`. Importing registers it.
3. **The system prompt:** `app/agent.py` says when to use the tool and how its sources are cited.
4. **FakeLLM:** `app/llm/fake.py`.
   - An answer branch in `_answer` (by tool name).
   - A default route in `_default_calls` if an unscripted question should reach it.
   - A script in `backend/fixtures/fake_script.json` for the model check.
5. **Frontend types:** run `uv run python -m app.tools.typescript` from `backend/`. It rewrites `frontend/src/toolResults.ts`, and a test fails while that file is stale.
6. **The card:** a component in `frontend/src/chat/ToolCallCard.tsx`, picked by `call.name`. A tool that proposes a change returns a proposal (`proposal_id`), and the chat shows B21's card for it (`toolCalls.proposalOf`).
7. **DESIGN.md:** an entry in §6.2 (tool cards) and a line in its checklist: light and dark, 400px, keyboard, reduced motion.
8. **Reduced motion:** if the card moves, add a scene to the shared check (`frontend/e2e/test_reduced_motion.py`).
9. **The model check** (`app/evals/`): a question with exact checks when the tool needs proving on real models.

## Only some tools

- **Exposed to other assistants:** add it to the MCP server's specs (`app/mcp_server.py`). Read-only tools only.
- **Next-step buttons on its card:** `app/card_actions.py` (fixed actions only). Changes go through a proposal (B21).
- **Changes state:** it never acts. It calls the one way in, `proposals.propose(action, deps, cve_id=, product=, fields=, why=, sources=)`, and returns the proposal; the user's Approve applies it. `propose` checks what the action needs and the fields it takes, and raises `InputError` (`run_tool` makes it the tool's error): don't catch it. It returns `NoChange` when it's already so: return `{message}`. A new kind of change is one entry in `proposals.CHANGES` plus its inputs in `ProposalCard.tsx`'s `INPUTS` (B27).

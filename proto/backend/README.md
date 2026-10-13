# Prototype backend

FastAPI backend for the LLM-security assistant. Built from [SPEC.md](../SPEC.md) and [PLAN.md](../PLAN.md).

```bash
uv sync
uv run pytest                                     # 135 tests, no key, no network
uv run uvicorn app.main:app --reload --port 8000  # FakeLLM; state in data/state.json
cp .env.example .env                              # then, for the real LLM:
uv run --env-file .env uvicorn app.main:app --port 8000
```

Rebuild the fixtures from `feasibility/data/` (run `feasibility/fetch.py` first for fresh data):

```bash
uv run --with pyyaml python -I scripts/build_fixtures.py
```

## Local models

Any OpenAI-compatible server on this machine works. In the app: Dev → Model → Local model → pick a preset → Find models → Save. Then "Run model check".

- **Ollama:** `ollama serve`, then `ollama pull <model>`. URL `http://localhost:11434/v1`.
- **LM Studio:** Developer tab → Start server, and load a model. URL `http://localhost:1234/v1`.
- **llama.cpp:** `llama-server -m model.gguf`. URL `http://localhost:8080/v1`.

The model needs tool calling for the chat to use the tools. The model check shows how well it does.

## Decisions made while building

- **CVE chunks may be 1,500 characters, not 600.** At 600, 339 of 929 CVEs split and left tiny tails like "This issue is fixed in version 0.30.0." that matched nonsense queries. At 1,500 only 3 split. OWASP and ATLAS text stays at 600.
- **The mock index only returns chunks that share a word with the query.** Every CVE id is a word of its own, so ~9,000 distinct words share the hash embedder's 4,096 buckets, and a nonsense query always collided with something. The gate keeps R6 literal. Turn it off (`word_gate=False`) with real embeddings and use a score threshold.
- **"List of Mapped CWEs" and "Score table" sections are not chunked.** They are link lists and numbers. The CWE map lives in `fixtures/owasp.json` for `explain_weakness`.
- **Products come from NVD's CPE data when present (745), else from the product named first in the description (184).** 10 spot checks of the text matches were all right.
- **Unscripted questions with a CVE id** run `lookup_cve`, then search for how to prevent its OWASP category, without the product name (with it, search returned more CVEs instead of guidance). The dashboard's "Ask about this" uses this path.

# Prototype build plan: LLM-security assistant

How the code is laid out for [SPEC.md](./SPEC.md). Written 2026-10-13. Replaces the AI-news plan (archived in `archive/proto-ainews-2026-10-13.tar.gz`).

## Layout

```text
proto/
  backend/
    scripts/build_fixtures.py  # feasibility/data → fixtures/ (a frozen snapshot)
    fixtures/
      owasp_llm/LLM01–10.md    # OWASP Top 10 for LLM apps 2025, images stripped
      owasp_web/A01–10.md      # OWASP Top 10 2025
      owasp.json               # page titles and URLs, CWE → A01–A10, LLM page → ATLAS ids
      atlas.json               # ATLAS 5.6.0, trimmed
      cves.json, kev.json      # 929 CVEs for 12 LLM products, 9 KEV entries
      manifest.json            # as_of, sources, licences, counts
      fake_script.json         # Q1–Q11
    app/
      main.py                  # routes: /chat, /dashboard, /cves, /watchlist, /settings, /alerts, /dev/*, /health
      config.py                # settings; AS_OF defaults to the snapshot date
      knowledge.py             # loads the snapshot; CveSource seam (fixture now, NVD later)
      state.py                 # watchlist, CVE statuses, settings, alerts log; atomic writes, a lock
      notify.py                # notifiers (desktop, email, ntfy, preview), the alert template
      dashboard.py             # numbers for /dashboard and /cves
      guard.py                 # limits, injection flagging, filter validation, delimiting
      agent.py                 # the tool loop and system prompt
      rag/                     # chunking, hash embedder, index + filters, RRF, pipeline, PCA map
      tools/                   # search_security, lookup_cve, explain_weakness, update_watchlist
      llm/                     # LLM protocol, FakeLLM, one OpenAI-compatible client, the router
      evals.py                 # the model check
  frontend/
    src/components/            # Chat, Dashboard, charts, cards, panels
    e2e/check_ui.py            # the browser check
```

## Mock seams

- `LLM`: `FakeLLM` (scripted) or `OpenRouterLLM`.
- `Embedder`: `HashEmbedder` (word matching). The index's word gate belongs to this mock.
- `CveSource`: `FixtureCveSource` reads the snapshot. A live NVD and KEV source would replace it.
- `State`: a JSON file. Fine for one user.
- `LLM`: the router picks FakeLLM, OpenRouter or a local server per call.
- `Notifier`: desktop, email, ntfy, and a preview that sends nothing.

## How a chat request flows

1. `guard.check_message`: limits (400 on breach), injection phrasing flagged.
2. `agent.answer`: system prompt + history + message, then up to 4 `llm.step` calls.
3. Each tool call runs through `registry.run_tool` (validate → run → time → record). Output is delimited as untrusted data.
4. `search_security`: `llm.translate` → filters validated → one search per rewrite → RRF → at most 2 chunks per document. The LLM gets full chunk text; the UI gets snippets.

## Tests

`uv run pytest`: 135 tests named after their check IDs. One shared index per run, a fresh state file per test.

| File | Covers |
| --- | --- |
| `test_chunking.py` | R1, R2 |
| `test_embed.py`, `test_fusion.py` | R3, Q-T2 (unchanged from the first version) |
| `test_index.py` | R4, R6, S2 |
| `test_pipeline.py` | Q-T1, Q-T3, R5, R8, S3–S5 |
| `test_guard.py` | V1–V3, V7 |
| `test_tools.py` | T2–T5 |
| `test_state.py` | W1, W2, W4 |
| `test_agent.py` | T6, T7, R7 |
| `test_api.py` | A2–A5, V1, V6, Q1–Q11, D1–D4, U10, W3 |
| `test_settings.py` | G1–G4, X1–X5 |
| `test_models.py` | M1–M3 (a fake OpenAI-compatible server in memory) |
| `test_notify.py` | N1–N4 (fake SMTP, ntfy and desktop runners) |

The UI checks (U1–U12, G2–G4, X2–X3) are in `frontend/e2e/check_ui.py`.

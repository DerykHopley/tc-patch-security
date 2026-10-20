# The model-check report: how it's made

- `findings.html`: the written findings, an HTML fragment. A draft by Claude, reviewed by Deryk (A20, #22).
- The report is built locally, because the runs need the OpenRouter key and the GPU. The runs themselves stay in `backend/data/evals/` (not in git).
- `runs.json` names the runs the report shows: the model-check runs (`models`), the retrieval runs (`retrieval`, in the order the charts list them) and the findings file. To show other runs, edit it and commit it with the new report.
- Rebuild it from `backend/`:

  ```bash
  uv run python -m app.evals report --runs ../docs/report-src/runs.json --out ../docs/report/index.html
  ```

- With `--runs` there is no fallback: a run id that isn't saved, or a missing or empty list, stops the build with an error that names it. Why: a fallback to "the latest run per model" once published a run nobody had reviewed (retro, 2026-10-15). Checked 2026-10-15: the command rebuilds the published page byte for byte except the "Generated" time.
- The "Off-topic threshold" chart needs retrieval runs made since it was added (2026-10-15): older runs show "No threshold data". To refresh them, run the retrieval check again for each embedder. It asks about 60 questions and no model. Ollama is free; OpenRouter costs a fraction of a cent. Then put the new run ids in `runs.json` and build the report as above.

  ```bash
  EMBEDDER=ollama EMBED_MODEL=nomic-embed-text INDEX_PATH=data/index-ollama-nomic uv run --env-file .env python -m app.evals retrieval
  EMBEDDER=openrouter INDEX_PATH=data/index-openrouter uv run --env-file .env python -m app.evals retrieval
  ```

- `docs/report/index.html` is the published page. `.github/workflows/pages.yml` uploads only `docs/report/` to GitHub Pages, on a push to `main` or `spec-a` that changes it.
- Before committing a new report, check it holds no key, no `.env` content and no course-brief text.

## The architecture review

- `docs/report/architecture-review.html`, published at https://derykhopley.github.io/tc-patch-security/architecture-review.html.
- Six deepening candidates from the `improve-codebase-architecture` review of `spec-a` (2026-10-15). All six are built and merged; each card shows what was built. The decisions are DECISIONS.md's 2026-10-15 rows.
- Unlike the model-check report, it loads Tailwind and Mermaid from CDNs, so it needs a network connection to show its styles and diagrams.

## The retro

- `docs/report/retro.html`, published at https://derykhopley.github.io/tc-patch-security/retro.html.
- What slowed the coding agents down during spec A and what to change in their environment (2026-10-15). All eight findings are done: CLAUDE.md in A21 (#23), guardrails in #56, the rest as agent memory and a prompt line. Each card shows what was done.
- Like the architecture review, it loads Tailwind and Mermaid from CDNs.

## The new questions on a real model (B16, #47)

B15 (#46) added the questions for spec B's tools. All 19 are FakeLLM-checked. **Done 2026-10-20:** Claude Haiku 5.5 answered them, run `20261020-074212-784-d4da` (16 of 19, 90 of 93 checks), in `findings.html` under "Spec B's new questions". The owner dropped gpt-oss-120b. The run was made on the live app and rescued by a download, because Cloud Run keeps runs only on the instance's disk. When two runs share a model, the report adds each run's day to its name (B16).

- New or changed since the 2026-10-15 runs: `Q-updates` (`check_updates`), `Q-web` ("who's talking", `research_web`, the injection page), `Q-research` (the research workflow), `Q-partial` (a failed step), and Q9/Q10 (now proposals, B21). `Q-affected` and `Q12` keep their questions but have relaxed expectations (#54): the report's grid marks the 2026-10-15 runs "old expectation" on those rows.
- The web questions search the saved results (`backend/fixtures/web_canned.json`): no Tavily key, no credits. `check_updates` never fetches in a model-check run, even in live mode.
- No key is needed beyond OpenRouter's. Run it in snapshot mode (the default).

Before you run:

1. Dev page → **Max agent steps** is 6 or more (the CLI uses the state file's saved value; `Q-research` needs 5 rounds). A saved 4 stays 4.
2. `openai/gpt-oss-120b` was not on the OpenRouter workspace's allow-list on 2026-10-15. Add it there first, or the run stops on its first question.

Run, from `backend/`:

```bash
LLM_PROVIDER=openrouter OPENROUTER_MODEL=openai/gpt-oss-120b uv run --env-file .env python -m app.evals model-check
# optional, local and free (about 25 s a question):
LLM_PROVIDER=local LOCAL_LLM_MODEL=qwen3.8:27b uv run --env-file .env python -m app.evals model-check
# only the new questions, for a quick look:
... python -m app.evals model-check --ids Q-updates Q-web Q-research Q-partial Q9 Q10
```

- Cost: 21 answers (Q12 is asked at three levels). At the default model's $0.0015 a question that's about $0.03; gpt-oss-120b should be less. *Unverified*: check the run's total in its output.
- Then add the run ids to `runs.json`, rebuild the report (above), and write what the model got wrong in `findings.html`: a wrong tool, no web citation, a followed injection (`injection_ignored`, `prompt_kept`), or a missing warning (`warns_injection`). Open an issue for each fix needed.

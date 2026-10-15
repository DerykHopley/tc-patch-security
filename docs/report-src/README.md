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
- Candidates for discussion from the `improve-codebase-architecture` review of `spec-a` (2026-10-15): nothing in it is built. Decisions on it go in DECISIONS.md or an ADR.
- Unlike the model-check report, it loads Tailwind and Mermaid from CDNs, so it needs a network connection to show its styles and diagrams.

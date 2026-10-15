# The model-check report: how it's made

- `findings.html`: the written findings, an HTML fragment. A draft by Claude, reviewed by Deryk (A20, #22).
- The report is built locally, because the runs need the OpenRouter key and the GPU. The runs themselves stay in `backend/data/evals/` (not in git).
- Rebuild it from `backend/`, naming the runs to show:

  ```bash
  uv run python -m app.evals report --findings ../docs/report-src/findings.html \
    --models 20261015-105401-709-f2d4 20261015-105401-689-8695 20261015-105558-693-322e 20261015-110149-704-d6a4 \
    --out ../docs/report/index.html
  ```

- The "Off-topic threshold" chart needs retrieval runs made since it was added (2026-10-15): older runs show "No threshold data". Run the retrieval check again for each embedder first. It asks about 60 questions and no model. Ollama is free; OpenRouter costs a fraction of a cent. Then build the report as above. It picks the newest run per embedder unless `--retrieval <ids>` names others.

  ```bash
  EMBEDDER=ollama EMBED_MODEL=nomic-embed-text INDEX_PATH=data/index-ollama-nomic uv run --env-file .env python -m app.evals retrieval
  EMBEDDER=openrouter INDEX_PATH=data/index-openrouter uv run --env-file .env python -m app.evals retrieval
  ```

- `docs/report/index.html` is the published page. `.github/workflows/pages.yml` uploads only `docs/report/` to GitHub Pages, on a push to `main` or `spec-a` that changes it.
- Before committing a new report, check it holds no key, no `.env` content and no course-brief text.

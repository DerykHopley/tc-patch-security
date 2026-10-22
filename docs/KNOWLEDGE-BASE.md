# The knowledge base

All public and openly licensed, frozen as a snapshot on 2026-10-13. The counts are from `backend/fixtures/manifest.json`.

| Source | What it gives | Downloaded from | Licence | Count |
|---|---|---|---|---|
| OWASP Top 10 for LLM Applications 2025 | The 10 LLM risks and how to prevent them | [GitHub: OWASP/www-project-top-10-for-large-language-model-applications](https://github.com/OWASP/www-project-top-10-for-large-language-model-applications) | CC BY-SA 4.0 | 10 pages |
| OWASP Top 10 2025 (web) | The 10 web risks, and the CWE → category map that links CVEs to OWASP | [GitHub: OWASP/Top10](https://github.com/OWASP/Top10) | CC BY-SA 4.0 | 10 pages, 249 CWEs |
| MITRE ATLAS 5.6.0 | AI attack techniques, mitigations, case studies | [GitHub: mitre-atlas/atlas-data](https://github.com/mitre-atlas/atlas-data) | Apache 2.0 | 262 entries |
| NVD CVE API 2.0 | CVEs for the 12 tracked LLM products | [nvd.nist.gov](https://nvd.nist.gov/developers/vulnerabilities) | Public (US government) | 929 CVEs |
| CISA KEV 2026.10.08 | Which of those CVEs are known to be exploited, and CISA's deadline | [cisa.gov](https://www.cisa.gov/known-exploited-vulnerabilities-catalog) | CC0 1.0 | 9 matches |
| OSV.dev | Affected and fixed versions, from GitHub Advisory Database records | [osv.dev](https://osv.dev) | CC-BY 4.0 | 514 records |
| EPSS | The chance each CVE is exploited in the next 30 days | [first.org/epss](https://www.first.org/epss) | Attribution requested by FIRST | 929 scores |

- **Attributions:** OWASP Top 10 for LLM Applications 2025 and OWASP Top 10:2025, by the OWASP Foundation. MITRE ATLAS, by The MITRE Corporation. CVE records from the National Vulnerability Database (NIST). CISA Known Exploited Vulnerabilities Catalog; no endorsement by CISA implied. Affected and fixed versions from OSV.dev, taken from GitHub Advisory Database records (CC-BY 4.0). EPSS by FIRST.
- **NVD notice:** This product uses the NVD API but is not endorsed or certified by the NVD.
- The dashboard's "Data freshness" card shows the same sources, licences and notices.
- **The 12 tracked products:** Langflow, Open WebUI, Flowise, vLLM, LangChain, Dify, Gradio, Ollama, llama.cpp, LiteLLM, AnythingLLM, LlamaIndex.
- **Text-matched CVEs:** 184 CVEs got their product from description text, not NVD's product data. OSV confirms 36; the other 148 are labelled "possible match".
- 1,680 chunks in the search index. How the sources link and why this domain: [FEASIBILITY.md](../FEASIBILITY.md).

## How the data gets in

- `feasibility/fetch.py` downloaded the raw NVD, KEV, OWASP and ATLAS files; they're kept in `backend/snapshot_raw/`.
- `backend/scripts/build_fixtures.py` builds the frozen snapshot in `backend/fixtures/` from them, offline. With `--fetch` it first re-downloads OSV and EPSS.
- `backend/fixtures/manifest.json` records each source with its URL, licence, attribution, retrieval date and count.
- **To refresh the data:** run `python3 -I feasibility/fetch.py`, copy the new files into `backend/snapshot_raw/`, change `AS_OF` in `build_fixtures.py`, then `cd backend && uv run python -m scripts.build_fixtures --fetch` and rebuild the index. *Unverified:* not re-run since 2026-10-14. Live mode keeps the CVE data current without it (spec B, [#32](https://github.com/DerykHopley/tc-patch-security/issues/32), [#36](https://github.com/DerykHopley/tc-patch-security/issues/36)).
- **In snapshot mode (the default) the app makes no live calls to these sources.** In live mode with `FEEDS=real`, the refresh calls NVD, KEV, EPSS and OSV.dev at fixed URLs; ATLAS and the OWASP pages stay snapshot data. Answers link back to the original pages: GitHub for OWASP, atlas.mitre.org, nvd.nist.gov and cwe.mitre.org.

## Other data the app uses (not knowledge sources)

- **Your local state:** the watchlist, product versions, CVE statuses and their history, settings, the alert log. One JSON file, `backend/data/state.json` (git-ignored).
- **Embeddings:** the hash embedder runs locally and is free (the default). Real embeddings come from OpenRouter's API (`gemini-embedding-2`, the live app's) or a local Ollama model (`mxbai-embed-large`). The index is stored locally in `backend/data/`.
- **Optional outside services:** OpenRouter or a local model server for the chat; Tavily for web research (only the search query is sent); Clerk for sign-in (Patch keeps only the user id); ntfy, Telegram, email (SMTP) or the desktop for alerts. Model keys live in `backend/.env` only; the alert channels' secrets in `backend/.env` or, saved on Settings, in the owner's state (never sent back to the browser).

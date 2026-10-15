# Source checks: OSV.dev, EPSS, Tavily, MCP SDK, NVD, KEV, VDA ISA

Facts the shortlist (process map, Flow 5) relies on, checked against official docs and live API calls on 2026-10-14. Everything here is *checked* unless marked otherwise.

## OSV.dev

- No key needed (every call worked without one). FAQ: "Currently there is not a limit on the API." https://google.github.io/osv.dev/faq/
- No single licence: each source keeps its own. GitHub Advisory Database (GHSA), PyPI and Go: CC-BY 4.0, attribution required. https://google.github.io/osv.dev/data/
- `POST /v1/query` with `{package: {ecosystem, name}, version?}` returns `vulns[]` with `affected[].ranges[].events` (`introduced` / `fixed`) and `affected[].versions[]`.
- `POST /v1/querybatch` returns ids only; fetch each with `GET /v1/vulns/{id}`.
- **Look up by package, not by CVE id.** `GET /v1/vulns/CVE-…` returns an NVD-converted record with git commit ranges only. The package versions are on the GHSA alias. Example: CVE-2025-3248 → GHSA-rvqx-wpfh-mfx7, `langflow` fixed in 1.3.0.
- PyPI results come twice (GHSA and PYSEC): de-duplicate by CVE alias.

Coverage of our 12 products (unique CVEs after de-duplication, against the snapshot):

| Product | Package | OSV CVEs | Snapshot CVEs |
|---|---|---|---|
| Langflow | PyPI `langflow` | 41 | 201 |
| Open WebUI | PyPI `open-webui` | 158 | 165 |
| Flowise | npm `flowise`, `flowise-components` | 112 | 150 |
| vLLM | PyPI `vllm` | 91 | 111 |
| LangChain | PyPI `langchain`, `-core`, `-community` | 23 / 9 / 7 | 53 |
| Gradio | PyPI `gradio` | 51 | 68 |
| LiteLLM | PyPI `litellm` | 39 | 36 |
| Ollama | Go `github.com/ollama/ollama` | 16 | 35 |
| LlamaIndex | PyPI `llama-index`, `-core` | 22 / 10 | 11 |
| llama.cpp | git commit ranges only | 27 | 40 |
| Dify | none | 0 | 37 |
| AnythingLLM | none | 0 | 22 |

- So: OSV gives "fixed in" versions for 9 products, commit ranges for llama.cpp, nothing for Dify and AnythingLLM.
- OSV is not a full CVE list (Langflow 41 of 201). NVD stays the main list; OSV adds versions.

## EPSS (FIRST)

- `https://api.first.org/data/v1/epss?cve=A,B,…`: comma-separated, up to 2,000 characters per query. No registration. 1,000 requests per minute. https://api.first.org/
- Updated daily, around 13:30 UTC. Current model EPSS v5 (v2026.06.15). https://www.first.org/epss/data
- Score = probability of exploitation activity in the next 30 days (0–1). Percentile = share of scored CVEs with a lower score.
- Licence: none named; the site footer says "All Rights Reserved". FAQ: "Attribution is requested when EPSS data is used in publications or products." Show "EPSS by FIRST". https://www.first.org/epss/faq.html
- Live, 2026-10-13: CVE-2025-3248 0.99993 (percentile 0.99988); CVE-2024-8309 0.13738 (0.96438).

## Tavily

- Free: 1,000 credits a month, no credit card. Basic search 1 credit, advanced 2. Key required (`tvly-…`). Development keys: 100 requests/min. https://docs.tavily.com/documentation/api-credits
- `POST /search`: `search_depth`, `max_results` (0–20), `include_domains`, `include_raw_content`, `topic`, `time_range`. Each result has `title`, `url`, `content` (snippet), `score`.
- Hosted remote MCP server: `https://mcp.tavily.com/mcp/?tavilyApiKey=<key>` (also a header or OAuth). Tools `tavily-search`, `tavily-extract`. Open source: `tavily-ai/tavily-mcp` (MIT). https://docs.tavily.com/documentation/mcp
  - The key sits in the URL: never log that URL.
- Terms: use "solely for Customer's internal business purposes"; no "automated decisions without human oversight"; 18+. Nothing on attribution. https://tavily.com/terms

## Tavily MCP and the LangChain adapter (B08, checked 2026-10-15)

- `langchain-mcp-adapters` **0.3.2** (PyPI, 2026-08-06): needs `langchain-core>=1.3.3,<2`, `mcp>=1.24,<2` (installed: `mcp` 1.30.0). https://pypi.org/project/langchain-mcp-adapters/
  - Streamable HTTP connection: `{"transport": "streamable_http", "url", "headers", "timeout", "httpx_client_factory", "auth"}` (read from the installed `sessions.py`).
  - **A key in the URL isn't treated as secret.** The adapter passes the URL as is to the MCP SDK; the SDK logs `Connecting to StreamableHTTP endpoint: {url}` at DEBUG (`mcp/client/streamable_http.py`), and httpx logs every request URL at INFO. So we send the key in `headers` instead (DECISIONS.md, B08). Checked by test B08.8.
- **Tool names:** `tavily_search`, `tavily_extract`, `tavily_crawl`, `tavily_map`, `tavily_research`, `tavily_feedback` (underscores) in the open-source server's code. https://github.com/tavily-ai/tavily-mcp/blob/main/src/index.ts
  - The docs and README write `tavily-search` (hyphen). We accept either name. Which one the **hosted** server lists is *unverified*: listing its tools needs a key.
- **`tavily_search` arguments** (same file): `query` (required), `search_depth` (basic, advanced, fast, ultra-fast; default basic), `topic` (general, news), `time_range`, `start_date`, `end_date`, `max_results` (5 to 20, default 5), `include_images`, `include_image_descriptions`, `include_raw_content` (default false), **`include_domains` and `exclude_domains`** (lists of domains, default empty), `country`, `include_favicon`, `exact_match`.
- **Result text** (`src/format-results.ts`): `Detailed Results:`, then per result a blank line and `Title:`, `URL:`, `Content:` (plus `Raw Content:`, `Favicon:` when asked). **No published date** over MCP.
- **Key:** `https://mcp.tavily.com/mcp/?tavilyApiKey=<key>`, an Authorization header, or OAuth. https://docs.tavily.com/documentation/mcp
  - The docs say "in the Authorization header" without a format; the README says `Authorization: Bearer <key>`. *Unverified* on the hosted server (no key).
  - A `DEFAULT_PARAMETERS` header can override arguments; we don't send it.
- **Plain search API:** `POST https://api.tavily.com/search`, `Authorization: Bearer tvly-…`. `exclude_domains` up to 150 domains; `max_results` 0 to 20; `published_date` per result only with `topic: news` or `include_published_date`, and it's Tavily's estimate (beta). https://docs.tavily.com/documentation/api-reference/endpoint/search
- Whether the hosted server is the same code as `tavily-mcp` isn't stated: the docs list the local server as an alternative, with OAuth and session handling added on the hosted one. *Unverified.*

## MCP Python SDK (checked 2026-10-15, for B23)

- PyPI `mcp`: the newest release is **2.3.0** (2026-10-02). The newest 1.x is **1.30.0** (2026-09-07). Checked on https://pypi.org/pypi/mcp/json.
- **We pin `mcp>=1.30.0,<2`.** `langchain-mcp-adapters` 0.3.2 (B08's web-research client) requires `mcp<2.0.0,>=1.24.0` (checked on PyPI), so one lock file can't hold 2.x yet. What 2.x changed: *unverified*, not read.
- stdio in 1.30: `mcp.server.stdio.stdio_server()` gives the read and write streams; the low-level `mcp.server.lowlevel.Server.run(read, write, server.create_initialization_options())` serves them. stdout carries the protocol, so logs must go to stderr. Checked by running it as a subprocess (test B23.8).
- `@server.call_tool(validate_input=False)` skips the SDK's own JSON-schema check, so our pydantic models give the errors. A handler may return a `CallToolResult` as is. Checked in the 1.30 source and by the tests.
- In-process testing: `mcp.shared.memory.create_connected_server_and_client_session(server)` gives a connected `ClientSession`. Checked (tests B23.1 to B23.7).
- Streamable HTTP in 1.30: `FastMCP.run(transport="streamable-http")` (default path `/mcp`), `FastMCP.streamable_http_app()` (a Starlette app), and `mcp.server.streamable_http_manager.StreamableHTTPSessionManager` (`handle_request`) to mount in an existing ASGI app. Present in the 1.30 source; *not run*.
- Tool annotations (`readOnlyHint`, `destructiveHint`, `idempotentHint`, `openWorldHint`) are hints for the client, not enforced. Checked in `mcp.types.ToolAnnotations`.

## NVD API 2.0

- `lastModStartDate` and `lastModEndDate`: both required, at most 120 days apart (confirmed from the API's own error messages).
- 5 requests per 30 s without a key, 50 with one.
- Required notice: "This product uses the NVD API but is not endorsed or certified by the NVD." https://nvd.nist.gov/developers/terms-of-use

## CISA KEV

- Feed: https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json (catalogue 2026.10.13, 1,741 entries).
- Licence: CC0 1.0. No CISA logo, no implied endorsement. The manifest says "Public (US government)"; it should say CC0.

## VDA ISA (TISAX)

- Licence: CC BY-ND 4.0 (licence tab of https://enx.com/isa2027-en.xlsx). Unchanged copies with attribution are fine. Changed versions must be marked "modified version not approved by the Licensor", without VDA logos.

## Stack checks (2026-10-14, second pass)

### Chroma (`chromadb` 1.5.9)

- Runs inside the Python process, no server: `chromadb.PersistentClient(path=...)`. https://docs.trychroma.com/docs/run-chroma/clients
- `where` filters: `$gt/$gte/$lt/$lte` compare int and float only, so store dates as ints (`20260914`). One field or one logical operator per filter object; a range needs `$and`. `$in` works on strings. https://docs.trychroma.com/reference/where-filter
- **No BM25 or hybrid search in local Chroma.** The Search API (sparse vectors, BM25, RRF) is "available in Chroma Cloud only". Local has `where_document` `$contains` / `$regex`, case-sensitive. https://docs.trychroma.com/cloud/search-api/overview
- Precomputed vectors can be passed in (`embeddings=`, `query_embeddings=`).
- Installed size measured at 483 MB (kubernetes 124 MB, onnxruntime 68 MB, Rust bindings 57 MB).
- `langchain-chroma` 1.1.0 (2025-12-12): maintained, quiet.

### Embeddings

- OpenRouter has `POST /api/v1/embeddings`: `openai/text-embedding-3-small` $0.02 per million tokens (about a cent for 3,500 chunks). EmbeddingGemma isn't offered. https://openrouter.ai/docs/api/reference/embeddings
- `fastembed` 0.9.0 (ONNX, CPU, 221 MB installed): `bge-small-en-v1.5` 384 dims, 67 MB. No EmbeddingGemma.
- EmbeddingGemma-300m: Gemma licence (accept before download), 768 dims (MRL 512/256/128); ONNX build exists; CPU speed not published.
- LangChain `OpenAIEmbeddings` against OpenRouter or LM Studio: set `check_embedding_ctx_length=False`.

### Hosting

- Vercel: FastAPI runs as one function; Python bundle limit 500 MB; Hobby 300 s, 2 GB; read-only filesystem except `/tmp`, not kept; Hobby cron once a day (±59 min); Hobby is non-commercial only.
- Cloud Run: free tier 2M requests, 360,000 GB-s, 180,000 vCPU-s a month; scales to 0; filesystem in memory, not kept. Cloud Scheduler: 3 free jobs per billing account. Firestore free: 1 GiB, 50k reads and 20k writes a day. Cloud Storage free: 5 GB in us-east1, us-west1, us-central1.

### OpenRouter

- Per-key spending cap (`limit`); over the cap → 402 `openrouter_key_limit`.
- Every response includes `usage.cost`.
- Free (`:free`) models with tools exist; 20 requests/min, 50 a day (1,000 a day after $10 of credits).
- Low-cost models listing `tools` and `structured_outputs` (USD per million tokens, in / out; tool-calling quality unchecked): `openai/gpt-oss-120b` 0.037 / 0.17; `anthropic/claude-haiku-5.5` 0.10 / 0.50; `qwen/qwen3.8-flash` 0.15 / 0.47; `deepseek/deepseek-v4.1-flash` 0.025 / 0.89; `google/gemini-3.1-flash-lite` 0.25 / 1.50.

## Clerk (checked 2026-10-14)

- Free (Hobby) plan: 50,000 monthly retained users per app, email/password, up to 3 social providers, "Require invitations" (invite-only), no credit card. Clerk branding stays. https://clerk.com/pricing
- **The email allowlist is paid in production** ("free to use in development mode"). Invite-only mode is free. https://clerk.com/docs/guides/secure/restricting-access
- **Production needs a domain you own**; `*.vercel.app` is ruled out by name, `*.run.app` by the same DNS rule (inferred). Without a domain you run a development instance, with its banner and limits. https://clerk.com/docs/guides/development/deployment/production
- React on Vite: `@clerk/react` (not the old `@clerk/clerk-react`), `VITE_CLERK_PUBLISHABLE_KEY`, `<Show when="signed-in">`; `useAuth().getToken()` gives a Bearer token for our API.
- FastAPI: `clerk-backend-api`, `authenticate_request(..., AuthenticateRequestOptions(authorized_parties=[...], jwt_key=...))`; `jwt_key` checks without a network call. Session tokens live 60 s: call `getToken()` per request. Check `azp` against our origins (else CSRF risk). Whether a Starlette `Request` goes in directly is unchecked (may need a small adapter).
- Playwright: `@clerk/testing` with testing tokens. Unit tests override the auth dependency.
- Publishable key in the frontend; secret key in `.env` only.

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

### What B03's adapter relies on (2026-10-15, `backend/app/feeds.py`)

- `resultsPerPage` up to 2,000, paged with `startIndex` until `totalResults`: *checked* by `feasibility/fetch.py`'s runs on 2026-10-13.
- Dates sent as `2026-10-15T09:00:00.000Z`: the same format `feasibility/fetch.py` used for `pubStartDate` and got answers. *Unverified* for `lastModStartDate`; the real run (#40) checks it.
- The key goes in an `apiKey` header (NVD's developer docs). *Unverified* here: no key was used.
- Pacing is a rolling window: at most 5 (or 50) requests in any 30 s. Tested against a fake server only.
- EPSS: `limit` is set to the batch size, since the API returns 100 rows by default (*unverified*, from the API docs; the snapshot fetch already set it). Each `cve=` list is at most 2,000 characters, commas literal.
- None of the four services was called while building B03: every test uses a local fake server.

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

### Cloud Run deploy (B13, 2026-10-16)

- `google-cloud-storage` **3.17.1** (PyPI, installed by `uv add`): `Bucket.get_blob`, `Bucket.list_blobs(prefix=)`, `Bucket.blob`, `Blob.upload_from_string(data, content_type, if_generation_match=)`, `Blob.download_as_bytes(if_generation_match=)` and `Blob.delete` exist with those arguments; `google.api_core.exceptions.PreconditionFailed.code` is 412 and `NotFound.code` 404; an upload sets the blob's `generation` from the reply (`_prep_and_do_upload` calls `_set_properties`). *Checked* by reading the installed library, offline. `GcsStore` relies on exactly these. Never run against a real bucket.
- The image with it: 1.7 GB uncompressed (`frontend/e2e/container.sh`, 2026-10-16). *Checked.*
- *Unverified* (no account; written from memory of Google's docs, to confirm in #45): the `gcloud` commands and flags in DEPLOY.md; the address form `https://<service>-<project number>.<region>.run.app`; that `roles/storage.objectUser` includes listing; Secret Manager's free 6 secret versions and 10,000 accesses; Cloud Storage's free 5,000 class A and 50,000 class B operations; Artifact Registry's free 0.5 GB; that a secret mounted as `:latest` is read when an instance starts; that 1 GiB of memory is enough; Clerk's `PATCH /v1/instance` `allowed_origins`.

## Clerk (checked 2026-10-14)

- Free (Hobby) plan: 50,000 monthly retained users per app, email/password, up to 3 social providers, "Require invitations" (invite-only), no credit card. Clerk branding stays. https://clerk.com/pricing
- **The email allowlist is paid in production** ("free to use in development mode"). Invite-only mode is free. https://clerk.com/docs/guides/secure/restricting-access
- **Production needs a domain you own**; `*.vercel.app` is ruled out by name, `*.run.app` by the same DNS rule (inferred). Without a domain you run a development instance, with its banner and limits. https://clerk.com/docs/guides/development/deployment/production
- React on Vite: `@clerk/react` (not the old `@clerk/clerk-react`), `VITE_CLERK_PUBLISHABLE_KEY` (we read the key from `/health` instead, B10), `<Show when="signed-in">`; `useAuth().getToken()` gives a Bearer token for our API.
- FastAPI: `clerk-backend-api`, `authenticate_request(..., AuthenticateRequestOptions(authorized_parties=[...], jwt_key=...))`; `jwt_key` checks without a network call. Session tokens live 60 s: call `getToken()` per request. Check `azp` against our origins (else CSRF risk). Whether a Starlette `Request` goes in directly: yes (B10, below).
- Playwright: `@clerk/testing` with testing tokens. Unit tests override the auth dependency.
- Publishable key in the frontend; secret key in `.env` only.

### Clerk: the checks at the start of B10 (2026-10-16)

- **Does a Starlette request go to `authenticate_request` directly? Yes** (*checked*). clerk-backend-api 7.0.0's `Requestish` protocol asks only for a `headers` mapping (`security/types.py`), and Starlette's `Request.headers` is one. It reads `Authorization: Bearer …` first, then a `__session…` cookie. With `jwt_key` set it verifies with PyJWT, RS256 only, no network (`security/verifytoken.py`: the JWKS fetch is only in the `secret_key` branch); it checks `exp`, `nbf`, `iat` (5 s skew) and, when `authorized_parties` is set, requires `azp` and that it's in the list. It does **not** check `iss` or `sts`. Our test B10.2–B10.4 runs this real path with our own RSA key. https://github.com/clerk/clerk-sdk-python (`src/clerk_backend_api/security/`)
- **Does a Clerk development instance work on a `*.run.app` origin?** *Unverified, likely yes.* Clerk's environments guide says preview deployments on a host's own domain (its example: Vercel's) should use **development keys**, and that development instances talk to Clerk cross-site, passing the dev browser token in the query string (`__clerk_db_jwt`) instead of a cookie, so no shared root domain is needed. Nothing names `run.app`. Confirm in the deploy (#44, #45): sign in on the service URL. https://clerk.com/docs/guides/development/managing-environments
- Development instances: at most 100 users, not for production, all paid features available. Same page.
- Session token claims: Clerk's manual-verification guide names only `exp`, `nbf`, `azp` and `sts` (`pending` when Organizations is required and the user has none; reject those). The user id is `sub` (*checked* in the SDK's code, not in the guide). Name and email are not in the default token: add them as custom claims, `{"name": "{{user.full_name}}", "email": "{{user.primary_email_address}}"}` (both shortcodes are on Clerk's page). *Since B48 (#77) Patch reads neither: no custom claims are needed.* https://clerk.com/docs/guides/sessions/manual-jwt-verification, https://clerk.com/docs/guides/sessions/customize-session-tokens
- Testing tokens: made by the Backend API (`POST https://api.clerk.com/v1/testing_tokens` with the secret key; the endpoint is the Backend API's "Testing Tokens" tag, *unverified* by a call) and added as the `__clerk_testing_token` query parameter to Frontend API requests. Short-lived, one instance. `@clerk/testing` is for JavaScript test runners; our browser check is Python, so it does those two steps itself. https://clerk.com/docs/guides/development/testing/overview
- `@clerk/react` 6.17.5 (2026-10-01): `ClerkProvider`, `SignIn` (`routing="hash"`, `withSignUp`), `useAuth().getToken()`, `useUser`, `useClerk().signOut`, `ClerkLoading`/`ClerkLoaded`/`ClerkFailed` (*checked* in its type files). Its script loader waits 15 s before it reports a failed load (`scriptLoadTimeout`, *checked* in `@clerk/shared`'s code).

### Clerk: SSO with invite-only, for B31 (2026-10-17)

Why the owner's Discord sign-in landed on `https://<instance>.accounts.dev/sign-in` (#78). Clerk's docs say little about these cases, so most answers come from Clerk's own code: `@clerk/ui` 1.38.1 (the components `@clerk/react` 6.17.5 loads; its source maps hold the TypeScript source) and `@clerk/clerk-js` 6.39.1, both from npm. "*Checked* in code" means read there, not tried against a real instance.

- **Where the hosted page came from** (*checked* in code). `<SignIn>` takes its sign-in and sign-up URLs from its props, then `ClerkProvider`'s `signInUrl`/`signUpUrl`, then the instance's `displayConfig`, which is the Account Portal (`contexts/components/SignIn.ts`). We set none. An SSO sign-in for an account Clerk doesn't know comes back "transferable", and `handleRedirectCallback` sends it to the sign-up URL (`clerk-js`, `_handleRedirectCallback`): the Account Portal. With `ClerkProvider` given paths on Patch's page, that can't happen.
- **`withSignUp` keeps sign-up inside `<SignIn>`** (*checked* in code). With `withSignUp` set, `<SignIn>` runs the "combined flow" even in Restricted mode: its sign-up steps are its own routes under `create` (`#/create`, `#/create/sso-callback`, `#/create/continue`, …), and an SSO callback returns to `#/create/sso-callback` on the same page.
- **OAuth with hash routing needs no `/sso-callback` route** (*checked* in code). With `routing="hash"` the callback URL is the current page with `#/sso-callback` (or `#/create/sso-callback`), handled by the mounted component (`common/redirects.ts` `buildRedirectUrl`). No path routing needed.
- **Restricted mode without an invitation** (*checked* in code). `<SignUp>`'s first step shows Clerk's "access restricted" card when the mode isn't public and there's no ticket (`SignUpStart.tsx`). So in Restricted mode, `#/create` without a ticket is only ever that card: Patch shows its own message there. Clerk's error codes for a refused sign-up: `sign_up_mode_restricted` (403, "New sign-ups are currently restricted.") and, for the allowlist, `not_allowed_access` (*checked* in Clerk's Frontend API errors page). Its components word any error code from `localization.unstable__errors.<code>` (*checked* in code, `makeLocalizable.tsx`).
- **Can an invitee finish signing up with an SSO provider? Yes, through the invitation link** (*checked* in code; *unverified* against a real instance). `<SignUp>` reads `__clerk_ticket` from the page's query string, creates the sign-up with the ticket, and, when that still misses something (a password), shows the form *with* the SSO buttons; its code comment says so (`SignUpStart.tsx`: "render the SignUp form with other available options to complete it (e.g. OAuth)"). Clerk's docs only say: "you must handle the sign-up flow in your code for that page … embed the `<SignUp />` component". Whether the SSO account's email must match the invited email: *unverified*. https://clerk.com/docs/guides/users/inviting
- **Invitation links go to the Account Portal unless they carry a redirect URL** (*checked* in Clerk's docs). "When the user visits the invitation link, they will be redirected to the Account Portal sign-up page." A redirect URL can be given only through the Backend API (`POST /v1/invitations` with `redirect_url`): "You currently cannot specify a redirect URL when creating an invitation in the Clerk Dashboard." The ticket arrives as `?__clerk_ticket=…`. https://clerk.com/docs/guides/users/inviting, https://clerk.com/docs/reference/backend/invitations/create-invitation
- **An invitee who skips the link and signs up with an SSO provider directly**: does a pending invitation for the same email let it through? *Unverified*: no Clerk page says. Assume not; the owner's round trip on #78 checks it.
- **The allowlist works in "Open" sign-up mode only, and is paid in production** (*checked* in Clerk's docs: "applies to applications in Open access mode"; "requires a paid plan for production use, but all features are free to use in development mode"). Whether it checks an SSO sign-up's email: *unverified*, the page doesn't say. https://clerk.com/docs/guides/secure/restricting-access
- **Account linking by verified email** (*checked* in Clerk's docs). "Clerk will attempt to link the OAuth account with any existing Clerk account that shares the same email address." Verified on both sides: linked and signed in, even for a password account. Verified only in Clerk: Clerk verifies the email first, then links. Unverified in Clerk: extra safeguards, maybe a password change. A different email isn't linked: sign in, then add it in the user profile. So the owner's Discord sign-in links only if Discord's verified email is the one on the Clerk account. https://clerk.com/docs/guides/configure/auth-strategies/social-connections/account-linking
- **The free plan allows up to 3 social providers** (*checked* 2026-10-14, above).

### Clerk: open sign-up, bot protection and linking accounts, for B38 (2026-10-19)

For #81: sign-up is open (Public mode) and the owner approves accounts in Patch; every signed-in user can link another SSO provider. Read in Clerk's docs and in Clerk's own code: `@clerk/ui` 1.38.1 and `@clerk/clerk-js` 6.39.1 from npm (their source maps hold the TypeScript source), and `@clerk/react` 6.17.5's and `@clerk/shared`'s type files in `frontend/node_modules`. "*Checked* in code" means read there, not tried against a real instance.

**Bot protection on open sign-up**

- **It's on every plan, the free one too** (*checked* on the pricing page: the Security features row "Bot protection: Ensure only real users can sign up" is Yes for Hobby, Pro and Business). https://clerk.com/pricing
- **What it is and where to switch it** (*checked* in Clerk's docs): "Challenge suspicious sign-ups" makes sign-ups that look automated, or come through VPNs, Tor or proxies, pass a challenge before the account is made. Sign-ups only, never sign-ins. "Enabled by default for new applications." Dashboard: **Protect → Protections**, the "Challenge suspicious sign-ups" row (Enable / Manage / "Setup required"). It needs ClerkJS 6.39.0 or later (the loaded clerk-js is 6.39.1, *checked* above) and a Content Security Policy that allows the challenge (Patch sets none). https://clerk.com/docs/guides/secure/bot-protection
- **It works with Patch's own form** (*checked* in Clerk's docs: "Clerk's prebuilt `<SignUp />` component shows the challenge inside the sign-up form"; *checked* in code: `<SignIn>`'s first step, `SignInStart.tsx`, and the sign-up step `<SignIn withSignUp>` runs, `SignUpStart.tsx`, both render Clerk's `CaptchaElement`). Patch uses `<SignIn withSignUp>`, so the challenge shows on Patch's page.
- **For an SSO sign-up specifically** the docs say only that it covers sign-ups: whether an SSO sign-up gets a challenge is *unverified*.
- **What's left without it** (if the owner's dashboard doesn't offer it): anyone, or any bot, can make accounts. Each account still sees only the request screen, and Patch alerts the owner once per account (a refused one can never ask again). A development instance holds at most 100 users (above), so a flood would fill it.

**Linking another provider to the signed-in user (the Connected accounts card)**

- **From the frontend: `user.createExternalAccount({ strategy, redirectUrl })`** (*checked* in Clerk's JavaScript reference and `@clerk/shared`'s `user.d.ts`): "Adds an external account for the user … useful if you want to allow an already signed-in user to connect their account with an external provider … so that they can sign in with that provider in the future." The provider must be switched on in the dashboard. It returns an `ExternalAccountResource`; its `verification.externalVerificationRedirectURL` is the provider's page. https://clerk.com/docs/js-frontend/reference/objects/user.md
- **The flow Clerk's own profile page uses** (*checked* in code, `@clerk/ui` `ConnectedAccountsMenu.tsx`): `useReverification(...)` around `user.createExternalAccount({ strategy, redirectUrl: window.location.href })`, then a full-page navigation to `externalVerificationRedirectURL`. Clerk's custom-flow guide does the same, with `useReverification` "to require the user to reverify their credentials before being able to add an external account" and the redirect to "the same page the user started on". Patch does this from its own Settings page: never Clerk's hosted pages. https://clerk.com/docs/guides/development/custom-flows/account-updates/manage-sso-connections
- **`useReverification` is exported by `@clerk/react` 6.17.5** (*checked* in its `index.d.mts`). When the instance asks for reverification, it opens Clerk's own dialog on the page.
- **The redirect back with hash routing.** `redirectUrl` is any full URL or path; the guides use a plain page path, and on that page Clerk reloads the user (`reloadUserAfterOAuthCallback`, *checked* in code). Patch's app routes by path (`/settings`); Clerk's hash routing is only inside `<SignIn>`, which isn't on the page once signed in. Patch sends `https://<Patch>/settings#connected-accounts`. Whether Clerk's Frontend API keeps the `#connected-accounts` part on the way back: *unverified* (if not, the page opens at Settings' top). Whether a production instance asks for the redirect address to be allowed: *unverified*.
- **Listing:** `user.externalAccounts` (every linked account), with `verifiedExternalAccounts` and `unverifiedExternalAccounts` getters; an account whose link failed carries `verification.error` (`longMessage`). Clerk's profile lists the verified ones and the failed ones (*checked* in code, `ConnectedAccountsSection.tsx`).
- **Unlinking:** `externalAccount.destroy()` (*checked* in `externalAccount.d.ts`; the custom-flow guide wraps it in `useReverification`). **Neither Clerk's docs nor its profile code stop you removing the last way to sign in** (*checked*: no such rule in `RemoveResourceForm.tsx` or the guide). So Patch checks it: a password, or another verified linked account, must stay. An email-code sign-in, if the instance allows it, isn't counted (Patch can't read the instance's settings from the public API), so Patch may refuse an unlink that would have been safe, never the other way round.
- **A provider whose email differs from the account's.** Clerk's account-linking page says a different email isn't linked automatically: "sign in … with their main email account", then add the other email in the profile. It doesn't mention `createExternalAccount` for this case. The JavaScript reference above describes connecting a provider to a signed-in user with no email condition. **Checked by the owner on 2026-10-19 (#81): Clerk links it.** Linking Discord from Patch's Connected accounts card (`createExternalAccount`) worked with a Discord email different from the Clerk account's. **Side effect (checked the same day in Clerk's dashboard):** linking adds the provider's verified email to the user's email addresses. So a later sign-in with *another* provider using that email (here Google) is linked automatically by email (the account-linking rule above). Patch is unaffected: it sees the same user id. For a test sign-up, use an email the owner's user doesn't hold. https://clerk.com/docs/guides/configure/auth-strategies/social-connections/account-linking
- **A provider account already used by another Clerk user** (e.g. the owner once made a separate account by signing in with Discord): Clerk has an error code `external_account_exists` (*checked* in code, `@clerk/ui`'s error codes). That it's what this case returns: *unverified*. Then delete the other user in the dashboard first.
- **Which providers to offer.** Clerk's list of the instance's enabled providers (`userSettings.socialProviderStrategies`) is in its environment, which `@clerk/react` doesn't expose publicly (*checked*: only internal hooks read it). Patch offers Google and Discord, the providers the README asks for; one that isn't switched on fails with Clerk's own message.

**Names and emails for the Requests card**

- **`clerk_backend_api` 7.0.0 `Clerk(bearer_auth=<secret key>).users.list(request={"user_id": [...], "limit": n})`** returns `User` objects with `first_name`, `last_name`, `username`, `email_addresses` (each with `id`, `email_address`) and `primary_email_address_id` (*checked* in the installed SDK's `users.py` and `models/`). Never called by the tests: they replace the lookup with a fake. The Backend API's largest page: *unverified* (Patch asks for 100 ids per call). **Checked against the owner's real Clerk dev instance on 2026-10-19:** with `CLERK_SECRET_KEY` set, the lookup found 2 of 2 users, each with a name and a primary email.

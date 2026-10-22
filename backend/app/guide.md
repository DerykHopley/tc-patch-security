<!--
The Patch guide (#148): what the patch_guide tool answers how-to questions from. One section per topic.
Each section: "## <topic>", then "Title:" and "Where:" (an in-app path, or "-" when it isn't a page), a blank line,
then the text. Written from the code and the docs as they are; every claim is checkable there. Short plain sentences,
GLOSSARY.md's words, nothing that isn't built. backend/tests/test_patch_guide.py checks the topics, the paths
against the frontend's routes and anchors, and the facts the code also holds.
-->

## start
Title: Getting started
Where: /about

Patch tracks the CVEs in the LLM products you use and answers questions about LLM and web application security. Start on Settings: in the Watchlist card, tick the products you use, give each one your version, and press Save changes. The Dashboard then sums up the open CVEs on your watchlist, and the CVEs page lists them with their priority and due date. Ask Patch anything with the Patch button at the bottom right, Ask Patch in the sidebar, or Ctrl+K (Cmd+K on a Mac). About, in the sidebar, says what Patch is and what it is for.

## dashboard
Title: The dashboard
Where: /

The dashboard is the first page: a summary of the open CVEs on your watchlist. Its Watchlist card picks which products the tiles, charts and Top 5 count. The four tiles are Open CVEs, Open and critical, Open and exploited in the wild (CISA KEV), and New in the last 30 days; each one opens the CVEs page with that filter. The charts show open CVEs by product and severity, CVEs per month, and open CVEs by OWASP Top 10 (web, 2025) category. Top 5 open CVEs is the head of the CVEs page's list. On the side are Data freshness (with Check now in live mode), Recent alerts and the latest AI incidents from MITRE ATLAS.

## cves
Title: The CVEs page
Where: /cves

The CVEs page lists the CVEs for the products on your watchlist, most urgent first, with each one's priority, due date, severity, EPSS, verdict and status. It shows the open ones until you pick another status. Filter it by product, severity, status, verdict, and CISA KEV only; in live mode also by new CVEs you haven't seen yet. The filters are kept in the address, so a link opens the same view. Each row has one main action and the rest under More: Mark fixed, Not affected, Accept risk, Accept again or Reopen, depending on its status. Each status change opens a dialog and is saved in the CVE's decision history: not affected needs a justification, accepted needs a reason and a review date. Click a CVE id to open its CVE page.

## cve_page
Title: The page for one CVE
Where: /cves

Every CVE has its own page at /cves/ followed by its id, for example /cves/CVE-2025-3248. Any CVE id in the list, the Top 5, an alert or Patch's answers links to it. It shows the full summary, the product and versions, the facts (severity, CISA KEV, EPSS), your assessment with the actions, the decision history, and links to NVD and OSV. Ask Patch on the page asks Patch about that CVE. Opening the page marks a new CVE as seen. Back returns you to the list where you were.

## watchlist_and_versions
Title: Your watchlist and versions
Where: /settings#watchlist

Your watchlist is the products you use; only their CVEs count as yours. Change it on Settings, in the Watchlist card: tick a product, then press Save changes. Patch tracks a fixed list of 12 products: AnythingLLM, Dify, Flowise, Gradio, LangChain, Langflow, LiteLLM, llama.cpp, LlamaIndex, Ollama, Open WebUI and vLLM; you can't add another one. For each ticked product, set its usage, your version and whether it is internet-facing. The version is what the version check compares with each CVE's fix, so give the one you run, for example 1.2.0 for Langflow. You can also tell Patch your version in the chat: it proposes saving it, and nothing changes until you approve. For Dify and AnythingLLM there is no version data, and llama.cpp lists only code commits, so their verdicts stay unknown.

## am_i_affected
Title: Am I affected?
Where: /cves

The verdict says whether a CVE touches your version of a product: affected, not affected or unknown, with the reason. It compares the version on your watchlist with the affected and fixed versions OSV lists for the CVE. Without a saved version, the verdict is unknown. The CVEs page shows it in the Verdict column and filter; ask Patch "Am I affected by CVE-2025-3248?" for one CVE. The verdict is advice only: your CVE status is your decision. When the verdict is not affected on an open CVE, the row offers "Mark not affected?", which only you can click.

## priority_and_due_dates
Title: Priority and due dates
Where: /settings#priority

Each open CVE gets a priority (urgent, high, normal or low) with its reasons, from fixed rules; Patch explains them and never changes them. A CVE in CISA KEV is urgent unless the verdict is not affected; critical is high, and so is a high EPSS on an internet-facing product; high and medium severity are normal; low is low. A not affected verdict lowers the priority one level. The due date is the publication date (or the date it was added to KEV) plus your policy's days for that priority: by default 7, 30, 90 and 180 days. Change the days, whether to use CISA's KEV deadline, and the EPSS threshold on Settings, in the Priority and due dates card. A CVE with no fixed version yet is never overdue: its due date is the date to decide by. Ask Patch "What should I fix first?" for the list in the rules' order.

## chat_and_sources
Title: Chatting with Patch, and sources
Where: -

Open the chat with the Patch button, Ask Patch in the sidebar, or Ctrl+K. Patch knows which page you are on and the CVEs page's filters, so "what should I fix first?" means the view you are looking at. Answers cite numbered sources as [1]: click one to see the source. Under an answer, "Show sources" opens its details: the Sources, Tool calls (one card per tool Patch used) and, after a search, the Query plan. The explain level (simple, normal or deep dive) is set on Settings, in Patch's answers, and the chat header can change it for one question. Make larger enlarges the chat, and then Pin docks it beside the page (not on a phone). The conversation is kept until you close the tab.

## proposals
Title: Changes Patch proposes
Where: -

Patch never changes your data by itself. When you ask it to watch or remove a product, set a CVE's status or save your version, it shows a proposal card with the change. Nothing changes until you press Approve; you can also Edit or Cancel it. A proposal expires after an hour, and one whose CVE or watchlist changed in the meantime can't be approved: ask again. Buttons on tool cards, such as Watch this product or Set my version…, make proposals too. Patch won't propose accepting the risk of a CVE in CISA KEV while its verdict is unknown or affected.

## alerts
Title: Alerts
Where: /settings#alerts

Alerts come after each refresh of the live data, so in snapshot mode there are none. Choose what alerts you on Settings, in the Alerts card: a CVE on your watchlist added to CISA KEV, a CVE you marked fixed added to KEV, a new CVE at or above your minimum severity (High by default), a new CVE with no severity yet, and an open CVE rescored as critical. Due-soon and overdue reminders are always on while alerts are. More alerts than your digest limit in one check (5 by default) come as one digest. The channels are desktop, email, ntfy and Telegram; the owner sets them up, and only the owner's alerts go to them. Everyone sees their own alerts in Patch: the last 5 in the dashboard's Recent alerts card, the last 20 on Settings (in Delivery for the owner, in Alerts for anyone else).

## live_data_and_check_now
Title: Live data and Check now
Where: /

Patch runs on a frozen snapshot of the data or on live data; the sidebar card says which, with the as-of date. Only the owner switches between them, on Settings in the Data card. In live mode a refresh fetches what changed from NVD, CISA KEV, EPSS and OSV.dev. It runs on the owner's schedule (Settings, Refresh runs: every 1, 3, 6, 12 or 24 hours, or paused), or when someone presses Check now on the dashboard's Data freshness card. At most one refresh runs every 5 minutes; a press before then says when the next one is allowed. You can also ask Patch "Anything new since Monday?": it runs the same check.

## web_research
Title: Web research
Where: -

Patch can search the web for what its knowledge base can't have, such as vendor advisories and news. Ask for it, for example "Who's talking about CVE-2025-3248 online?". It works only when the server has a Tavily key. By default there are 30 searches a day for each person and 30 for everyone together; the research card says how many are left today. Patch sends only a short query of its own words, never your watchlist. Web results are cited like other sources but always marked "Web result, unverified", and a page that tries to give instructions is flagged and ignored.

## roles_and_access
Title: Sign-in, access and roles
Where: /settings#requests

With sign-in off, there is one user and everything is theirs. With sign-in on, anyone can sign up, and a new account asks for access with an optional note; the owner approves or refuses it on Settings, in the Requests card. The owner picks a role when approving, or later. A Viewer, the default, has the dashboard, the CVEs, the chat and their own watchlist. Trusted also sees the Dev page read-only and may use the search playground. A Reviewer may change the Dev settings, but only their own copy. Only the owner runs the model check, sets the alert channels and the schedule, and switches live data.

## dev_page
Title: The Dev page
Where: /dev

The Dev page shows how Patch works inside: the chat model (FakeLLM, OpenRouter or a local model), the search settings, the index, and an embedding map. The search playground shows each step of one search. The owner can also run the model check and the retrieval check there and read the model-check report. It is in the sidebar only for Trusted, Reviewer and the owner, and only when the server has it on. Trusted sees it read-only, and a Reviewer's changes apply only to their own chat.

## mcp_server
Title: Patch as an MCP server
Where: -

Patch offers four read-only tools to other assistants, such as Claude Code or Claude Desktop, over MCP: search_security, lookup_cve, explain_weakness and check_affected. It runs from a copy of Patch's code on your own machine, not from the web app. The assistant starts it itself with `cd backend && uv run python -m app.mcp_server`. With Claude Code: `claude mcp add patch -- uv --directory /absolute/path/to/backend run python -m app.mcp_server`. It has no watchlist: give check_affected your version and usage in the question. It can't change anything.

## privacy
Title: Your data and privacy
Where: /settings#start-over

Patch keeps your watchlist, CVE statuses, decision history and settings, separately for each person. It stores no names or emails: an optional display name on Settings, in Profile, is only for your user menu. Your questions and the tools' results go to the chat model chosen on the Dev page; the sidebar card names it. Web research sends only a short search query. The chat is kept only in this browser tab, and is cleared when you close it or sign out. Start over, the last card of Yours on Settings, deletes your own data.

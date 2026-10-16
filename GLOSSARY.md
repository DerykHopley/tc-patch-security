# LLM-security assistant (Patch)

A security assistant for people building LLM apps: it answers questions about risks, attacks and CVEs from public sources, and tracks the CVEs in the products you use. Decisions and their reasons are in [DECISIONS.md](./DECISIONS.md); this file only fixes the words.

## Language

### Knowledge

**Knowledge base**:
The public sources Patch answers from: OWASP Top 10 for LLM apps 2025, OWASP Top 10 2025, MITRE ATLAS, NVD CVEs for the tracked products, and CISA KEV.
_Avoid_: corpus, dataset, docs

**Product**:
One of the fixed list of LLM products whose CVEs are tracked (for example Langflow, LiteLLM, Open WebUI).
_Avoid_: package, vendor, tool

**Snapshot**:
The knowledge base frozen on one date, so answers and tests repeat exactly.
_Avoid_: fixtures (that's the folder), cache

**Live data**:
The CVE data in live mode (`DATA_MODE=live`): the snapshot's files, refreshed from the feeds, kept as whole versions. Starts as a copy of the snapshot. OWASP and ATLAS stay snapshot data.
_Avoid_: real-time data, cache

**Refresh**:
One run that fetches the feeds (NVD, KEV, EPSS, OSV), builds a new version of the live data and moves *last checked*. Check now, the CLI and later the chat and the schedule all start the same refresh.
_Avoid_: sync, update, poll

**Partial run**:
A refresh where some feeds answered and some didn't (B20). What answered is written; a failed feed keeps its data; *last checked* stays. A **failed run** is one where no feed answered: nothing is written.
_Avoid_: half refresh, degraded run

**Skipped run**:
A refresh that was asked for but refused by the 5-minute rule (or because one was running): nothing was fetched. Shown in the run history as "Skipped: too soon"; the same refusal again counts up instead of adding a line (B19).
_Avoid_: failed run (a failed run did ask the feeds)

**Paused schedule**:
The scheduled refresh switched off on Settings (B19). No scheduled run starts; Check now, the CLI and `check_updates` still run one, and alerts held through quiet hours still go out.
_Avoid_: disabled refresh, alerts off (that's a different switch)

**Didn't finish** (a step):
A tool call that stopped short in an answer and may pass on a second try: a timeout, a rate limit, a service that's down. Its card says "Didn't finish" and offers **Try again**, which runs that step only. The answer says the step is missing, never that it worked.
_Avoid_: partial answer, skipped

**As-of date**:
The date "today" means for the data: the snapshot date in snapshot mode, today (UTC) in live mode.
_Avoid_: now, current date

**KEV**:
CISA's catalogue of CVEs known to be exploited in the wild. A CVE is "in KEV" when it appears there.
_Avoid_: exploited list, CISA list

**KEV deadline**:
The remediation date KEV sets for a CVE, meant for US federal agencies. A fact about the CVE, not your deadline.
_Avoid_: due date (that's yours), KEV due date

**EPSS**:
FIRST's daily estimate of how likely a CVE is to be exploited in the next 30 days, with its percentile among all CVEs.
_Avoid_: exploit score, risk score

**Source**:
A numbered piece of the knowledge base that an answer cites as `[n]`.
_Avoid_: reference, document, chunk (a chunk is how it's stored)

**Web source**:
A numbered web page from `research_web` (B08), cited as `[n]` like a source but always marked "Web result, unverified". It's untrusted text.
_Avoid_: search result, link

### Your stack

**Watchlist**:
The products you say you use. Only CVEs for watched products count as yours.
_Avoid_: stack, subscriptions

**CVE status**:
Your mark on a CVE for a watched product: open, fixed, not affected or accepted. Open until you say otherwise. Only you set it: never a rule, the verdict or Patch.
_Avoid_: state, resolution

**Open CVE**:
A CVE for a product on your watchlist whose status is open, or accepted with its review due. Only your status decides this, never the verdict.
_Avoid_: active CVE, unresolved CVE

**Accepted**:
Your status for a CVE you've decided to live with for now (risk accepted), with a reason, a review date and optionally a compensating control. Not open, not overdue, not in the priority order until its review date.
_Avoid_: ignored, waived, snoozed

**Review due**:
An accepted CVE whose review date has come (at the as-of date). It's back in the open list and counts, its acceptance shown, until you accept it again, fix it, mark it not affected or reopen it.
_Avoid_: expired, lapsed

**Decision record**:
What you decided about one CVE and why: the status, its justification or reason, a note, the review date and compensating control, when, and who. Every status change appends one to the CVE's history; none is ever edited or removed (only the full reset clears them).
_Avoid_: audit log, comment

**Justification**:
Why a CVE is not affected, one of the five VEX reasons: component not present, vulnerable code not present, vulnerable code not in execute path, vulnerable code cannot be controlled by adversary, inline mitigations already exist. Required for not affected.
_Avoid_: excuse, reason (that's for accepted)

**Usage**:
How you run a watched product: self-hosted app, library, comes in through another package, or hosted service. Recorded with your version.
_Avoid_: deployment type, install type

**Verdict**:
The version check's advice on whether a CVE touches your version of a product: affected, not affected, or unknown. Advice only; your status is the decision.
_Avoid_: affected status, affectedness

**Who acts**:
Who has to do something about a CVE: you, upstream (the package that brings it in), or the vendor (for a hosted service).
_Avoid_: owner, assignee

### Urgency

**Priority**:
How urgent an open CVE is for you: urgent, high, normal or low, with the reasons. Set by fixed rules, never by Patch.
_Avoid_: risk, rank, score

**Policy**:
Your deadlines: how long you allow per priority, and whether to adopt the KEV deadline.
_Avoid_: SLA, rules (the rules compute priority)

**Due date**:
The date by which you mean to deal with an open CVE, from your policy.
_Avoid_: deadline (say KEV deadline for CISA's)

**Overdue**:
An open CVE that has a fix, past its due date.
_Avoid_: late, expired

**No fix yet**:
An open CVE for which OSV lists no fixed version for the product's packages (open range, or last-affected only). It's never overdue; its due date is the "decide by" date: accept, mitigate or replace. A CVE with no OSV record isn't "no fix yet": that's unknown.
_Avoid_: unfixable, unpatched

**Internet-facing**:
Your mark on a watched product that people outside can reach. Raises priority.
_Avoid_: exposed, public

**Assessment**:
Everything Patch knows about one CVE for your stack: the verdict, your decision record, the priority and the due date. A CVE whose product isn't on your watchlist still gets one: not watched, no status, no priority.
_Avoid_: evaluation, report, row (that's the CVEs page's view of it)

### Safety

**Untrusted text**:
Any text Patch didn't write and you didn't type: retrieved knowledge, tool output, web pages. It's data, never instructions.
_Avoid_: external content

**Flag**:
To mark a message as looking like an injection attempt, log it, and still answer it.
_Avoid_: block, reject (a flagged message is never blocked)

**Proposal** (proposed change):
A change Patch suggests to your watchlist, a CVE's status or a product's details. Nothing changes until you approve it; you can edit or cancel it. It expires after an hour. A **proposed decision** (B22) is a proposal of a CVE's decision record at the end of web research: it lists the sources it rests on.
_Avoid_: action, pending change, request

### Alerts

**Alert**:
A short message, built only from structured fields, that tells you about one CVE on your watchlist (or a digest of several).
_Avoid_: notification (that's the delivery), warning

**Alert reason**:
Why an alert fired, for example new, kev, now critical. Each CVE and reason alerts once.
_Avoid_: trigger, type

**Channel**:
Where alerts are delivered: desktop, email or ntfy.
_Avoid_: notifier (that's the code), sink

**Digest**:
One message for many alerts: more than the digest limit in one check (default 5), or what quiet hours held. It gives counts by alert reason, never the CVE ids.
_Avoid_: summary, batch

**Quiet hours**:
A daily time window in which alerts are held, then sent as one digest when it ends.
_Avoid_: do not disturb, mute

**Alerts log**:
The record of every alert message: when, why, and what each channel did with it (sent, recorded only, not set up, failed). The dashboard's "Recent alerts" card shows the last 20.
_Avoid_: history (that's a CVE's decisions), notifications

**Owner**:
The one user whose alerts go to the channels, named by `OWNER` in the server's environment (locally the default user). Every other user's alerts are shown in the app only.
_Avoid_: admin, account holder

**Default user**:
The one user while sign-in is off (locally and in the tests). Their state is the state file.
_Avoid_: local user, guest

**Sign-in**:
Clerk, invite-only, switched by `AUTH` (off locally and in the tests). On, every API route but `/health` needs a signed-in user; a signed-out visitor sees the sign-in screen.
_Avoid_: login, auth (except the setting's name)

**Session token**:
The short-lived (60 s) token Clerk gives the signed-in browser. The frontend sends a fresh one with every API call; the backend checks it with the instance's JWT public key.
_Avoid_: JWT (it is one, but say what it's for), API key

### The assistant

**Patch**:
The assistant, and the robot that is its face in the UI.
_Avoid_: the bot, the chatbot, the agent

**Page context**:
What Patch is told about the view under the chat: the page, the CVEs page's filters (product, severity, status, verdict, KEV, since) and the selected CVE. Fixed fields only, each checked against a fixed list; anything else is dropped and listed. Never free text.
_Avoid_: page state, screen text

**Selected CVE**:
The CVE last asked about with "Ask about this" on the CVEs page, during that visit. Part of the page context.
_Avoid_: active CVE, focused CVE

**Fix first**:
The top of the priority order for the page's view, as the `prioritise` tool returns it. Rules set the order; Patch explains it and never re-ranks.
_Avoid_: recommendation, Patch's ranking

**Explain level**:
How Patch pitches an answer: simple, normal, or deep dive. The facts and sources stay the same at every level.
_Avoid_: tone, mode, persona

**Model check**:
The scripted questions asked of one model, each answer scored by exact checks (right tools, filters, key fact, real citations, cites sources, flagged, no exploit code). No LLM judges another.
_Avoid_: eval, benchmark, LLM-as-judge

**Retrieval check**:
Questions whose right source comes from structured fields (a CVE id → that CVE), asked of one embedder's search; scored by hit rate at 5 and MRR.
_Avoid_: embedding eval, recall test

**Run**:
One saved model check or retrieval check: who or what was checked, when, every score. The evaluation report is built from runs.
_Avoid_: result, session

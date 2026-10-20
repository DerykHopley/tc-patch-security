# Alerts plan: new CVEs on your watchlist

Get a phone notification when a CVE for a watched product appears, gets added to CISA KEV, or gets scored critical. Builds on the prototype in `proto/` and the process map's "Flow 4".

Written 2026-10-13. The rules, de-duplication, delivery and the alerts panel were built in B04 (#37, 2026-10-15): `backend/app/alerts.py`; what the build chose where this plan left room is in DECISIONS.md (2026-10-15, B04 rows).

## Why

- The dashboard only shows what you look at. An alert brings the urgent cases to you: mostly KEV additions, which have a remediation due date.
- For the course, the live update behind it is an optional task on its own: "real-time data updates" (medium). Run on a schedule, it is "automated knowledge base updates" (hard). The alert is a small step on top.

## Decisions to confirm

1. **Alert triggers:** a new CVE for a watched product at or above a minimum severity (default: high); a CVE added to KEV (always); a CVE later scored critical.
2. **Channels:** desktop (the OS's own notifications), email (SMTP) and ntfy (phone). Pick any mix on the settings page. Built 2026-10-13.
3. **Schedule: every 6 hours,** run outside the app (cron or a systemd timer), plus a "Check now" button on the dashboard.
4. **Unscored CVEs on watched products:** alert as "new, not yet scored", or wait for the score? Suggest: alert, with a lower priority.
5. **Products matched by description text** (not NVD's product data): alert, labelled "possible match".

## The flow

```text
cron / "Check now"
  → refresh: NVD CVEs modified since last_checked + the KEV feed
  → match products, map CWE → OWASP, join KEV       (same code as build_fixtures.py)
  → write data/live/  → the server reloads its knowledge and index
  → diff against the last run → alert rules → de-duplicate (state.json)
  → notifier: one push, or one digest if there are many
  → tap → the dashboard row, or the chat via "Ask about this"
```

## Design

### Live data (`CveSource`)

- `LiveCveSource` keeps the fixture shape, so the dashboard and tools don't change.
- NVD: query `lastModStartDate` / `lastModEndDate` from `last_checked` to now. Both are required and the range is at most 120 days (from third-party docs; our own fetch used the `pubStartDate` / `pubEndDate` pair with the same date format and it worked, checked 2026-10-13).
- Without an API key NVD allows about 5 requests per 30 seconds; a free key allows about 50 (third-party docs, unverified on NVD's site). One run for 12 products is a few requests.
- KEV: re-read the whole feed (about 1.8 MB, checked). Compare `dateAdded`, not the CVE's published date: KEV also adds old CVEs.
- Move `match_product` and the CWE → OWASP join from `scripts/build_fixtures.py` into an app module, so the snapshot build and the live refresh share one version.

### One writer, one reader

- A command, `uv run python -m app.refresh`, does the download, the diff and the alerts. It writes `data/live/cves.json`, `kev.json` and an alerts log.
- The server checks the files' modification time on each request and reloads when they change. Rebuilding the index takes about 0.1 s for ~1,700 chunks (measured 2026-10-13).
- Why not a background thread in the server: one process writes, one reads, and a crash in the refresh can't take the chat down. "Check now" runs the same function and holds the state lock.
- `AS_OF` becomes today in live mode. Snapshot mode keeps 2026-10-13 for the tests.

### State additions (`state.json`)

```json
{
  "watchlist": ["langchain", "langflow"],
  "statuses": {"CVE-2024-8309": "fixed"},
  "last_checked": "2026-10-13T18:00:00Z",
  "alert_settings": {"min_severity": "HIGH", "kev_always": true, "unscored": true},
  "alerted": {"CVE-2026-9198": ["new", "kev"]},
  "alerts_log": [{"at": "...", "cve": "...", "reason": "kev", "sent": true}]
}
```

- `alerted` makes each (CVE, reason) alert fire once, across reruns and restarts.
- If a refresh fails (NVD down, rate limit), `last_checked` doesn't move, so the next run covers the gap.

### Alert rules (a pure function, easy to test)

| Reason | Fires when | Skipped when | Priority |
| --- | --- | --- | --- |
| `kev` | A watched CVE appears in KEV | Marked "not affected" | 5 (urgent) |
| `kev_recheck` | A CVE marked "fixed" appears in KEV | — | 3: "check your fix" |
| `new` | A new CVE for a watched product, at or above `min_severity` | — | 4 if critical, else 3 |
| `new_unscored` | A new CVE with no severity yet | `unscored` is off | 2 |
| `now_critical` | A known open CVE gets scored critical | Already alerted `new` as critical | 4 |

- More than 5 alerts in one run → one digest ("7 new CVEs for your watchlist, 2 in KEV") instead of 7 pushes.
- Text-matched products get "possible match" in the message.

### Notifier (a new seam, like `LLM`)

```python
class Notifier(Protocol):
    def send(self, title: str, body: str, priority: int, tags: list[str], click: str | None) -> None: ...
```

- `FakeNotifier` records messages for tests.
- `NtfyNotifier` POSTs the body to `https://ntfy.sh/<topic>` (or a self-hosted server) with the headers `Title`, `Priority` (1–5), `Tags` and `Click` (checked in ntfy's docs, 2026-10-13).
- Settings: `NOTIFIER=fake|ntfy`, `NTFY_URL`, `NTFY_TOPIC`, optional `NTFY_TOKEN`. In `.env.example`, never committed.

### The message

- Built from structured fields only: id, product, severity, CVSS, the reason, your due date. Example: **Title** "In CISA KEV: Langflow", **body** "CVE-2026-9198 · critical 9.8 · due 2026-08-07" (your due date from the policy; "decide by" when there is no fix yet, as on the dashboard).
- **No CVE description text.** It is untrusted, it can be long, and a lock screen shows it to anyone holding the phone.
- The click link opens the app at `#cve=CVE-…`: the dashboard row, with "Ask about this" one tap away.

### UI changes

- Dashboard: a "New since last check" badge on table rows; an alerts panel (last 20, with reason and whether it was sent); alert settings next to the watchlist; a "Check now" button with a spinner.
- Data freshness shows `last_checked` and "live" instead of the snapshot date.

## Security and privacy

- **The ntfy topic is a secret.** ntfy's docs say a topic name on ntfy.sh is "essentially a password". Anyone who knows it can read your alerts and learn which products you run. Use a long random topic, or a self-hosted server with an access token.
- The watchlist is sensitive in itself: it is a map of your stack. Alerts should say no more than needed.
- The refresh makes outbound calls to NVD, CISA and ntfy only. No user input reaches those URLs.
- "Check now" must not be callable in a loop: one refresh at a time (the state lock) and at most one every few minutes.

## Tests (new checks)

| ID | Check |
| --- | --- |
| N1 | Two fake snapshots (day 1, day 2): the diff finds exactly the new, KEV-added and newly critical CVEs |
| N2 | Each rule in the table fires and skips as stated, including statuses |
| N3 | A rerun sends nothing new (de-duplication survives a restart) |
| N4 | More than 5 alerts → one digest |
| N5 | A failed refresh leaves `last_checked` unchanged; the next run covers the gap |
| N6 | The message has no description text, and text matches say "possible match" |
| N7 | The server reloads after the live files change; the chat finds a new CVE |
| N8 | `NtfyNotifier` sends the right URL and headers (against a local test server, not ntfy.sh) |

## Build order

1. Move product matching and the OWASP join into `app/`. The snapshot build still gives the same fixtures (compare the files).
2. Alert rules as a pure function, with the fake snapshots. N1–N4.
3. State additions and de-duplication. N3, N5.
4. `FakeNotifier`, then `NtfyNotifier`. N6, N8. **Done 2026-10-13 (ahead of the worker):** `app/notify.py` has desktop, email and ntfy notifiers plus a preview, all tested against fakes; one real desktop notification was sent and arrived. The settings page sends test alerts per channel. What's left is the worker that decides when to send.
5. `LiveCveSource` and `app.refresh`, then reload-on-change in the server. N7.
6. Dashboard: badge, alerts panel, settings, "Check now". Extend `e2e/check_ui.py`.
7. One real run: a cron entry, a real ntfy topic, a phone. Log what arrived and how long it took.

## What this will hide or get wrong

- **NVD's backlog.** In the 90-day sample (feasibility check), only 32% of new CVEs had product data and 38% were deferred. So fresh CVEs mostly match by description text, the least checked path. Expect some false alerts at first.
- **Late scores.** Many CVEs arrive without a severity. The `new_unscored` and `now_critical` rules exist for this.
- **Gaps over 120 days** (if the refresh doesn't run for months) need a full rebuild, not a modified-since query.
- **KEV due dates are for US federal agencies.** They are a useful urgency signal, not a deadline for you.

## Update 2026-10-13: two new steps from the shortlist

The tools shortlist (process map, Flow 5) changes this flow. Not built yet; recorded so the build includes them.

- **Trigger:** besides cron and "Check now", Patch gets a `check_updates` chat tool ("anything new since Monday?"). Same refresh, same lock, same rate limit.
- **Fetch:** also EPSS scores for the watched CVEs (likelihood of exploitation; API terms unverified).
- **Am I affected?** (after match and link): each watched product gets how you use it (self-hosted app, library, transitive dependency, hosted service) and your version. OSV.dev gives the affected ranges and the fixed version (coverage of our 12 products unverified). Result: affected yes / no / unknown, and who acts. A "no" is suggested, the user confirms.
- **Prioritise** (a pure function, like the rules): KEV, EPSS, affected, internet-facing → a priority. Due date from your own policy (for example: KEV by CISA's date, critical in 7 days, high in 30). The policy can adopt KEV dates, but per the note above they are a signal, not your deadline, unless you choose so.
- **Rules:** `kev` and `new` skip CVEs the version check says you're not affected by. Two new reasons:

| Reason | Fires when | Skipped when | Priority |
| --- | --- | --- | --- |
| `due_soon` | An open, affected CVE is 3 days from its due date | Fixed or not affected | 4 |
| `overdue` | An open, affected CVE passes its due date; repeats once a week | Fixed or not affected | 5 |

- **Message:** may add two structured fields, "Affected: yes" and "you act: upgrade". Still no description text.
- **Tap:** built. `#cve=…` opens the app with a banner; "Explain it" asks Patch. Answering at the user's explain level comes with the shortlist.
- **New tests:** affected yes / no / unknown against a fake OSV; priority and due dates as a table-driven pure-function test; `due_soon` and `overdue` fire and skip as stated.

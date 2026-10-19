// The freshness panel's words (B02, DESIGN.md §5.10): when the data was last checked, and the one line Check now
// leaves behind. Plain functions, so `npm test` checks the words without a browser.
import type { AlertCounts, CheckReply, DataStatus, Feeds, RefreshCounts, RefreshResult } from './api.ts'
import { viewToSearch } from './cveView.ts'

const two = (n: number) => String(n).padStart(2, '0')

/** "2026-10-15 09:05 UTC". UTC, like the backend's messages and the run log, so every place says the same time. */
export function utcTime(iso: string): string {
  const d = new Date(iso)
  return `${d.getUTCFullYear()}-${two(d.getUTCMonth() + 1)}-${two(d.getUTCDate())} ${two(d.getUTCHours())}:${two(d.getUTCMinutes())} UTC`
}

/** The line under the panel's title. `asOf`: the as-of date (/dashboard), shown for the snapshot. */
export function checkedLine(data: DataStatus, asOf: string): string {
  if (data.mode === 'snapshot') return `A frozen snapshot, as of ${asOf}.`
  if (data.last_checked) return `Last checked ${utcTime(data.last_checked)}.`
  // B20: last_checked moves only when every feed answered, but a partial run did write what answered
  return data.last_result?.status === 'partial' ? 'Not checked in full yet: some sources updated (below).'
    : 'Not checked yet: the live data is still the snapshot.'
}

// The counts in the order they are said; a zero is left out ("2 new CVEs, 1 added to KEV").
const COUNT_WORDS: [keyof RefreshCounts, (n: number) => string][] = [
  ['new', (n) => `${n} new CVE${n === 1 ? '' : 's'}`],
  ['updated', (n) => `${n} updated`],
  ['kev_added', (n) => `${n} added to KEV`],
  ['rescored', (n) => `${n} rescored`],
]

export const SOURCE_NAME: Record<string, string> = { nvd: 'NVD', kev: 'CISA KEV', epss: 'EPSS', osv: 'OSV' }

export type Tone = 'ok' | 'warn' | 'error'

const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`

// B34: what happened to the alerts, in this order. "Recorded only" says "not sent", so a dry run (NOTIFY_DRY_RUN)
// never reads as alerts that went out.
const ALERT_WORDS: [keyof AlertCounts, string][] = [
  ['sent', 'sent'],
  ['recorded', 'recorded only (not sent)'],
  ['failed', 'failed'],
  ['held', 'held for quiet hours'],
]

/** "1 alert sent", "275 alerts recorded only (not sent)", …; a zero is left out. The dashboard's line and the
 *  refresh runs list say the same words. `owner` false (B50, #95): anyone else's alerts are only ever in Patch, so
 *  "recorded only (not sent)" would read as a fault: theirs say "3 alerts in Patch". */
export function alertWords(c: AlertCounts, owner = true): string[] {
  return ALERT_WORDS.filter(([k]) => c[k] > 0).map(([k, words]) =>
    `${plural(c[k], 'alert')} ${!owner && k === 'recorded' ? 'in Patch' : words}`)
}

/** The line after Check now: what the run found, why it failed, or when the next check is allowed. */
export function replyLine(reply: CheckReply, owner = true): { tone: Tone; text: string } {
  if (reply.refusal) {
    const at = utcTime(reply.refusal.next_allowed).slice(11) // "09:05 UTC"
    return {
      tone: 'warn',
      text: reply.refusal.reason === 'running'
        ? `A check is running already. The next one is allowed at ${at}.`
        : `Checked less than 5 minutes ago. The next check is allowed at ${at}.`,
    }
  }
  const r = reply.result
  if (!r || !r.ok) {
    const why = r?.errors.map((e) => `${SOURCE_NAME[e.source] ?? e.source}: ${e.message}`).join('; ')
    return { tone: 'error', text: `The check failed${why ? ` (${why})` : ''}. The data is unchanged.` }
  }
  const parts = COUNT_WORDS.filter(([key]) => r.counts[key] > 0).map(([key, words]) => words(r.counts[key]))
  const alerts = reply.alerts_for_you ? alertWords(reply.alerts_for_you, owner) : []
  const then = alerts.length ? ` ${alerts.join(', ')}.` : '' // B34: your alerts, by what happened
  if (r.status === 'partial') // B20: never "Done" for a run where a feed failed; the banner says which
    return { tone: 'warn', text: (parts.length ? `Done in part: ${parts.join(', ')}.` : 'Done in part: nothing new from the sources that answered.') + then }
  const tone = reply.alerts_for_you?.failed ? 'warn' : 'ok' // an alert that failed needs a look at Recent alerts
  return { tone, text: (parts.length ? `Done: ${parts.join(', ')}.` : 'Done: nothing new since the last check.') + then }
}

const GAP_MS = 5 * 60 * 1000 // at most one run per 5 minutes, counted from the last run's start (app/refresh.py)

/** "NVD", "CISA KEV and EPSS", "NVD, CISA KEV, OSV and EPSS". */
function names(sources: string[]): string {
  const n = sources.map((s) => SOURCE_NAME[s] ?? s)
  return n.length < 2 ? n.join('') : `${n.slice(0, -1).join(', ')} and ${n.at(-1)}`
}

/** B20: the banner for a last run where a feed failed (partial or failed), or null when every feed answered.
 *  What updated, what didn't, and when Retry may run (the 5-minute rule); `details`: each failed feed's reason. */
export function runBanner(r: RefreshResult | null | undefined): { tone: Tone; text: string; details: string[] } | null {
  if (!r || r.status === 'ok') return null
  const failed = r.feeds.length ? r.feeds.filter((f) => !f.ok).map((f) => ({ source: f.source, message: f.message ?? '' }))
    : r.errors // a run logged before B20 has no feed steps
  const at = utcTime(r.started).slice(11)
  const next = utcTime(new Date(new Date(r.started).getTime() + GAP_MS).toISOString()).slice(11)
  const updated = r.feeds.filter((f) => f.ok).length
  const head = r.status === 'partial' ? `${updated} of ${r.feeds.length} sources updated at ${at}` : `No source updated at ${at}`
  const parts = [head, `${names(failed.map((f) => f.source))} didn't answer`,
    ...(r.status === 'failed' ? ['the data is unchanged'] : []), `next try ${next}`]
  return {
    tone: r.status === 'partial' ? 'warn' : 'error',
    text: parts.join(' · '),
    details: failed.map((f) => `${SOURCE_NAME[f.source] ?? f.source}: ${f.message}`),
  }
}

// B28: where live data comes from. The real feeds by name; the fake ones as a warning, so live mode on made-up CVEs
// never looks like the real thing (the owner's B07 run got phone alerts about CVE-2026-99101).
const FEEDS_TEXT: Record<Feeds, string> = {
  real: 'Live: NVD, CISA KEV, EPSS and OSV.dev',
  fake: 'Live: the made-up test data, not the real feeds',
}

/** The Data card's first line: all six sources the app reads (B50, #95: it named four, leaving out OSV.dev and EPSS
 *  in snapshot mode). In live mode the CVE data is refreshed; OWASP and ATLAS stay the snapshot's (GLOSSARY.md). */
export function dataSources(mode: 'live' | 'snapshot'): string {
  return mode === 'live'
    ? 'Live CVE data from NVD, CISA KEV, EPSS and OSV.dev; OWASP and MITRE ATLAS from the snapshot.'
    : 'A snapshot of OWASP, MITRE ATLAS, NVD, CISA KEV, EPSS and OSV.dev.'
}

/** The Data card's line (the owner's): ok for the real feeds, warn for the fake ones. */
export function feedsLine(feeds: Feeds): { tone: 'ok' | 'warn'; text: string } {
  return { tone: feeds === 'real' ? 'ok' : 'warn', text: FEEDS_TEXT[feeds] }
}

/** The freshness card's warning: only in live mode on the fake feeds, and only for the owner (`feeds` is set). */
export function freshnessFeedsWarning(data: DataStatus): string | null {
  return data.mode === 'live' && data.feeds === 'fake' ? FEEDS_TEXT.fake : null
}

/** B43: "See the 2 new CVEs" → the CVEs list of the new CVEs you haven't seen yet (B40), any status, so the list
 *  shows the same number even after you closed one from the list; with the dashboard's product filter, as the tiles.
 *  Null when nothing is new. */
export function newCvesLink(count: number, filter: string[]): { text: string; href: string } | null {
  if (count <= 0) return null
  const href = `/cves${viewToSearch({ status: 'all', new: true, product: filter.join(',') || undefined })}`
  return { text: count === 1 ? 'See the new CVE' : `See the ${count} new CVEs`, href }
}

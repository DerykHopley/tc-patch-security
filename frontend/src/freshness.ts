// The freshness panel's words (B02, DESIGN.md §5.10): when the data was last checked, and the one line Check now
// leaves behind. Plain functions, so `npm test` checks the words without a browser.
import type { CheckReply, DataStatus, RefreshCounts, RefreshResult } from './api.ts'

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

/** The line after Check now: what the run found, why it failed, or when the next check is allowed. */
export function replyLine(reply: CheckReply): { tone: Tone; text: string } {
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
  if (r.status === 'partial') // B20: never "Done" for a run where a feed failed; the banner says which
    return { tone: 'warn', text: parts.length ? `Done in part: ${parts.join(', ')}.` : 'Done in part: nothing new from the sources that answered.' }
  return { tone: 'ok', text: parts.length ? `Done: ${parts.join(', ')}.` : 'Done: nothing new since the last check.' }
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

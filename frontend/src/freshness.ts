// The freshness panel's words (B02, DESIGN.md §5.10): when the data was last checked, and the one line Check now
// leaves behind. Plain functions, so `npm test` checks the words without a browser.
import type { CheckReply, DataStatus, RefreshCounts } from './api.ts'

const two = (n: number) => String(n).padStart(2, '0')

/** "2026-10-15 09:05 UTC". UTC, like the backend's messages and the run log, so every place says the same time. */
export function utcTime(iso: string): string {
  const d = new Date(iso)
  return `${d.getUTCFullYear()}-${two(d.getUTCMonth() + 1)}-${two(d.getUTCDate())} ${two(d.getUTCHours())}:${two(d.getUTCMinutes())} UTC`
}

/** The line under the panel's title. `asOf`: the as-of date (/dashboard), shown for the snapshot. */
export function checkedLine(data: DataStatus, asOf: string): string {
  if (data.mode === 'snapshot') return `A frozen snapshot, as of ${asOf}.`
  return data.last_checked ? `Last checked ${utcTime(data.last_checked)}.` : 'Not checked yet: the live data is still the snapshot.'
}

// The counts in the order they are said; a zero is left out ("2 new CVEs, 1 added to KEV").
const COUNT_WORDS: [keyof RefreshCounts, (n: number) => string][] = [
  ['new', (n) => `${n} new CVE${n === 1 ? '' : 's'}`],
  ['updated', (n) => `${n} updated`],
  ['kev_added', (n) => `${n} added to KEV`],
  ['rescored', (n) => `${n} rescored`],
]

const SOURCE_NAME: Record<string, string> = { nvd: 'NVD', kev: 'CISA KEV', epss: 'EPSS', osv: 'OSV' }

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
  return { tone: 'ok', text: parts.length ? `Done: ${parts.join(', ')}.` : 'Done: nothing new since the last check.' }
}

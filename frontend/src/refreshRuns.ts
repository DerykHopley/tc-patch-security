// The "Refresh runs" card's words and the schedule line (B19, DESIGN.md §5.12). Plain functions, so `npm test`
// checks the words without a browser.
import type { DataMode, FeedResult, RefreshCounts, RunRow, RunTrigger, ScheduleStatus } from './api.ts'
import { alertWords, SOURCE_NAME, utcTime, type Tone } from './freshness.ts'

const TRIGGER_NAME: Record<RunTrigger, string> = {
  button: 'Check now',
  chat: 'Patch', // check_updates in the chat
  schedule: 'Schedule',
  cli: 'Command line',
}

export const triggerName = (t: RunTrigger): string => TRIGGER_NAME[t] ?? t

/** The result chip: its words (the colour is never the only cue) and its tone. */
export function runResult(r: RunRow): { text: string; tone: Tone | 'muted' } {
  if (r.result === 'skipped') return { text: r.reason === 'running' ? 'Skipped: one was running' : 'Skipped: too soon', tone: 'muted' }
  if (r.result === 'partial') return { text: 'Partial', tone: 'warn' }
  if (r.result === 'failed') return { text: 'Failed', tone: 'error' }
  return { text: 'OK', tone: 'ok' }
}

/** "2026-10-15 09:00 UTC · 2.4 s": when it started, and how long it took (a skip took no time). */
export function runWhen(r: RunRow): string {
  return r.duration_s === null ? utcTime(r.started) : `${utcTime(r.started)} · ${r.duration_s.toFixed(1)} s`
}

// The counts in the order they are said; a zero is left out. Short, for one line under each run.
const COUNTS: [keyof RefreshCounts, (n: number) => string][] = [
  ['new', (n) => `${n} new`],
  ['updated', (n) => `${n} updated`],
  ['kev_added', (n) => `${n} added to KEV`],
  ['rescored', (n) => `${n} rescored`],
]

/** The line under a run: what it found and the alerts it sent you, or, for a skip, when the next run may start. */
export function runCounts(r: RunRow): string {
  if (r.result === 'skipped') {
    const at = r.next_allowed ? `Next allowed ${utcTime(r.next_allowed).slice(11)}` : 'Refused'
    return r.times > 1 ? `${at} · asked ${r.times} times` : at
  }
  const c = r.counts
  const parts = c ? COUNTS.filter(([k]) => c[k] > 0).map(([k, words]) => words(c[k])) : []
  // B34: what happened to your alerts (the server counts them again from each run's log, older runs too)
  parts.push(...alertWords({ sent: r.alerts_sent, recorded: r.alerts_recorded, failed: r.alerts_failed, held: r.alerts_held }))
  if (parts.length) return parts.join(' · ')
  return r.result === 'failed' ? 'Nothing written' : 'Nothing new'
}

/** One feed's step in a run's details: "NVD: answered", or "NVD: didn't answer (why)". */
export function feedLine(f: FeedResult): string {
  const name = SOURCE_NAME[f.source] ?? f.source
  return f.ok ? `${name}: answered` : `${name}: didn't answer${f.message ? ` (${f.message})` : ''}`
}

const every = (hours: number) => (hours === 1 ? 'Every hour' : `Every ${hours} hours`)

/** The schedule for anyone but the owner (B09: the refresh is shared, so the owner's schedule runs it): read-only,
 *  in place of the select and Pause on Settings. */
export function ownersSchedule(s: ScheduleStatus): string {
  return `The owner's schedule: ${every(s.hours).toLowerCase()}${s.paused ? ', paused' : ''}. Only the owner can change or pause it.`
}

/** The schedule in one line, on Settings and (paused) on the dashboard's freshness card. */
export function scheduleLine(s: ScheduleStatus, mode: DataMode): string {
  if (mode === 'snapshot') return `${every(s.hours)}, in live mode. The snapshot never changes.`
  if (s.paused) return 'Schedule paused: no scheduled check starts. Check now and Patch still check.'
  return s.next_due ? `${every(s.hours)} · next scheduled check from ${utcTime(s.next_due)}.`
    : `${every(s.hours)} · the next scheduled check runs at the next tick.`
}

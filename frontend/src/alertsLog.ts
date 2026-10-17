// The alerts log's words (B04, DESIGN.md §5.11): what each entry was for, and what each channel did with it.
// Plain functions, so `npm test` checks the words without a browser.
import type { AlertLogEntry, AlertReason, ChannelResult } from './api.ts'

export const REASON_WORDS: Record<AlertReason, string> = {
  kev: 'In CISA KEV',
  kev_recheck: 'Check your fix',
  new: 'New CVE',
  new_unscored: 'New, not scored yet',
  now_critical: 'Now critical',
  due_soon: 'Due in 3 days',
  overdue: 'Overdue',
}

/** "In CISA KEV", "Digest", "Test alert", "Overdue, held for quiet hours". */
export function entryReason(e: AlertLogEntry): string {
  if (e.kind === 'test') return 'Test alert'
  if (e.kind === 'digest') return 'Digest' // the title already counts them
  const words = e.reason ? REASON_WORDS[e.reason] : 'Alert'
  return e.kind === 'held' ? `${words}, held for quiet hours` : words
}

export type ResultTone = 'ok' | 'muted' | 'error'

/** One channel's result, by the channel's id as Settings names it: "ntfy: sent", "desktop: recorded only",
 * "email: not set up", "ntfy: failed (…)". */
export function channelResult(c: ChannelResult): { tone: ResultTone; text: string } {
  const name = c.channel
  if (c.error_code === 'not_configured') return { tone: 'error', text: `${name}: not set up` }
  if (c.error) return { tone: 'error', text: `${name}: failed (${c.error})` }
  return c.sent ? { tone: 'ok', text: `${name}: sent` } : { tone: 'muted', text: `${name}: recorded only` }
}

/** When an entry has no channel results: no channel was picked in Settings. */
export const NO_CHANNELS = 'No channel picked: recorded only'

/** Why an entry has no channel results: held for quiet hours, another user's (B09: only the owner's alerts go to
 * the channels, which are the owner's), or no channel picked. */
export function noChannels(e: AlertLogEntry): string {
  if (e.kind === 'held') return 'Held: sent when quiet hours end'
  if (e.in_app_only) return 'In the app only: alerts go to the owner’s channels'
  return NO_CHANNELS
}

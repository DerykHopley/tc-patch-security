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
 * "email: not set up", "ntfy: failed (…)". A retried send (B41) says its tries: "ntfy: failed (network down), trying
 * again at the next check (1 of 3 tries)", "ntfy: sent (2 tries)", "ntfy: failed (3 tries)" (the error in the
 * title then), or "ntfy: failed, not tried again: no longer needed". */
export function channelResult(c: ChannelResult): { tone: ResultTone; text: string } {
  const name = c.channel
  const tries = c.tries ?? 1
  if (c.error_code === 'not_configured') return { tone: 'error', text: `${name}: not set up` }
  if (c.dropped) return { tone: 'muted', text: `${name}: failed, not tried again: no longer needed` }
  if (c.error && c.retry) {
    return { tone: 'error',
      text: `${name}: failed (${c.error}), trying again at the next check (${tries} of ${MAX_TRIES} tries)` }
  }
  if (c.error) return { tone: 'error', text: `${name}: failed (${tries > 1 ? `${tries} tries` : c.error})` }
  if (!c.sent) return { tone: 'muted', text: `${name}: recorded only` }
  return { tone: 'ok', text: tries > 1 ? `${name}: sent (${tries} tries)` : `${name}: sent` }
}

/** B41: a failed send's tries in all (app.alerts.MAX_TRIES). */
export const MAX_TRIES = 3

/** When an entry has no channel results: no channel was picked in Settings. */
export const NO_CHANNELS = 'No channel picked: recorded only'

/** Why an entry has no channel results: held for quiet hours, another user's (B09: only the owner's alerts go to
 * the channels, which are the owner's), or no channel picked. */
export function noChannels(e: AlertLogEntry): string {
  if (e.kind === 'held') return 'Held: sent when quiet hours end'
  if (e.in_app_only) return 'In the app only: alerts go to the owner’s channels'
  return NO_CHANNELS
}

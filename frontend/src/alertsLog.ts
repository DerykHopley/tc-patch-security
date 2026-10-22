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

/** The Recent alerts card with nothing in it. Anyone but the owner (B50, #95) can't send a test alert (the channels
 *  are the owner's), and a check only records theirs in Patch. */
export function emptyAlerts(mode: 'live' | 'snapshot', owner: boolean): string {
  if (mode === 'live') {
    return owner ? 'No alerts yet. A check sends them when something on your watchlist needs you.'
      : 'No alerts yet. A check shows them here when something on your watchlist needs you.'
  }
  const none = 'No alerts yet. The snapshot never changes, so no check finds any.'
  return owner ? `${none} Test alerts show in Settings.` : none // #144: the dashboard lists real alerts only
}

/** #144: the dashboard's card, a glance at what needs you: the last 5 real alerts, no test alerts (delivery
 *  housekeeping, listed in Settings). */
export const DASHBOARD_SHOWN = 5
/** #144: Settings has the full log: Delivery for the owner (test alerts and every channel's result), the Alerts card
 *  for anyone else. The API sends the last 20. The first 5 show, the rest behind "Show all" (the owner's choice, so
 *  Delivery stays short). */
export const SETTINGS_SHOWN = 20
export const SETTINGS_FIRST = 5

export const dashboardAlerts = (log: AlertLogEntry[]) => log.filter((e) => e.kind !== 'test').slice(0, DASHBOARD_SHOWN)
export const settingsAlerts = (log: AlertLogEntry[], all = false) => log.slice(0, all ? SETTINGS_SHOWN : SETTINGS_FIRST)
export const SHOW_FEWER = `Show the last ${SETTINGS_FIRST}`
/** The toggle that shows the rest, with how many there are: null when nothing would be hidden. */
export function showAllLabel(log: AlertLogEntry[]): string | null {
  const n = Math.min(log.length, SETTINGS_SHOWN)
  return n > SETTINGS_FIRST ? `Show all ${n}` : null
}

/** The dashboard card's link to the full log (#144): the owner's is Delivery, with the channels' results; anyone
 *  else's is their own Alerts card (they have no channels, B48). */
export function alertsLink(owner: boolean): { text: string; href: string } {
  return owner ? { text: 'Alerts and delivery in Settings', href: '/settings#delivery' }
    : { text: 'All your alerts in Settings', href: '/settings#alerts' }
}

/** Why an entry has no channel results: held for quiet hours, another user's (B09: only the owner's alerts go to
 * the channels; B50: "In Patch only", as their Alerts card's note says), or no channel picked. */
export function noChannels(e: AlertLogEntry): string {
  if (e.kind === 'held') return 'Held: sent when quiet hours end'
  if (e.in_app_only) return 'In Patch only'
  return NO_CHANNELS
}

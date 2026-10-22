// The alerts log's words (B04): what an entry was for, and each channel's result. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { AlertLogEntry } from './api.ts'
import {
  alertsLink, channelResult, dashboardAlerts, emptyAlerts, entryReason, noChannels, settingsAlerts,
} from './alertsLog.ts'

const entry = (over: Partial<AlertLogEntry> = {}): AlertLogEntry => ({
  at: '2026-10-15T09:00:00+00:00',
  kind: 'alert',
  cve: 'CVE-2024-37014',
  reason: 'kev',
  alerts: [{ cve: 'CVE-2024-37014', reason: 'kev', priority: 5 }],
  title: 'In CISA KEV: Langflow',
  body: 'CVE-2024-37014 · critical 9.8 · due 2026-11-05',
  priority: 5,
  tags: ['kev', 'langflow'],
  click: 'http://localhost:5173/#cve=CVE-2024-37014',
  channels: [],
  ...over,
})

test('B04.11 each entry says what it was for', () => {
  assert.equal(entryReason(entry()), 'In CISA KEV')
  assert.equal(entryReason(entry({ reason: 'overdue' })), 'Overdue')
  assert.equal(entryReason(entry({ kind: 'held', reason: 'due_soon' })), 'Due in 3 days, held for quiet hours')
  const three = [1, 2, 3].map((i) => ({ cve: `CVE-2026-${i}0000`, reason: 'new' as const, priority: 3 }))
  assert.equal(entryReason(entry({ kind: 'digest', cve: null, reason: null, alerts: three })), 'Digest')
  assert.equal(entryReason(entry({ kind: 'test', cve: null, reason: null, alerts: [] })), 'Test alert')
})

test('B09.9 an entry with no channel says why: none picked, held, or another user (the owner gets the channels)', () => {
  assert.equal(noChannels(entry()), 'No channel picked: recorded only')
  assert.equal(noChannels(entry({ kind: 'held' })), 'Held: sent when quiet hours end')
  assert.equal(noChannels(entry({ in_app_only: true })), 'In Patch only')
})

test('B50.9 an empty Recent alerts card: anyone but the owner has no test alerts and no channels', () => {
  // F144.4: test alerts no longer show on the dashboard, so the owner's words point to Settings
  assert.equal(emptyAlerts('snapshot', true),
    'No alerts yet. The snapshot never changes, so no check finds any. Test alerts show in Settings.')
  assert.equal(emptyAlerts('snapshot', false), 'No alerts yet. The snapshot never changes, so no check finds any.')
  assert.equal(emptyAlerts('live', true), 'No alerts yet. A check sends them when something on your watchlist needs you.')
  assert.equal(emptyAlerts('live', false),
    'No alerts yet. A check shows them here when something on your watchlist needs you.')
  for (const words of [emptyAlerts('snapshot', false), emptyAlerts('live', false)]) {
    assert.doesNotMatch(words, /test alert|sends/)
  }
})

test('B04.11 each channel says sent, recorded only, not set up or failed', () => {
  const base = { error: null, error_code: null } as const
  assert.deepEqual(channelResult({ channel: 'ntfy', sent: true, ...base }), { tone: 'ok', text: 'ntfy: sent' })
  assert.deepEqual(channelResult({ channel: 'desktop', sent: false, ...base }),
    { tone: 'muted', text: 'desktop: recorded only' })
  assert.deepEqual(channelResult({ channel: 'email', sent: false, error: 'Set SMTP_HOST…', error_code: 'not_configured' }),
    { tone: 'error', text: 'email: not set up' })
  assert.deepEqual(channelResult({ channel: 'ntfy', sent: false, error: 'network down', error_code: 'notify_failed' }),
    { tone: 'error', text: 'ntfy: failed (network down)' })
})

test('B41.7 a retried channel says its tries', () => {
  const failed = { channel: 'ntfy', sent: false, error: 'network down', error_code: 'notify_failed' } as const
  assert.deepEqual(channelResult({ ...failed, tries: 1, retry: true }),
    { tone: 'error', text: 'ntfy: failed (network down), trying again at the next check (1 of 3 tries)' })
  assert.deepEqual(channelResult({ ...failed, tries: 3, retry: false }),
    { tone: 'error', text: 'ntfy: failed (3 tries)' })
  assert.deepEqual(channelResult({ channel: 'ntfy', sent: true, error: null, error_code: null, tries: 2, retry: false }),
    { tone: 'ok', text: 'ntfy: sent (2 tries)' })
  assert.deepEqual(channelResult({ ...failed, error: 'Not tried again: no longer needed.', tries: 1, retry: false,
    dropped: true }), { tone: 'muted', text: 'ntfy: failed, not tried again: no longer needed' })
  // a first try that went through, as before B41
  assert.deepEqual(channelResult({ channel: 'desktop', sent: true, error: null, error_code: null }),
    { tone: 'ok', text: 'desktop: sent' })
})

// --- F144 (#144): the dashboard's short list of real alerts; the full log in Settings ----------------------------

const day = (i: number) => `2026-10-${String(22 - (i % 20)).padStart(2, '0')}T09:00:00+00:00`
const testAlert = (i: number) => entry({ at: day(i), kind: 'test', cve: null, reason: null, title: `Test ${i}` })
const realAlert = (i: number) => entry({ at: day(i), title: `Real ${i}` })

test('F144.1 the dashboard shows the last 5 real alerts, never a test alert', () => {
  const log = [testAlert(0), realAlert(1), testAlert(2), realAlert(2), realAlert(3), testAlert(4), realAlert(4),
    realAlert(5), realAlert(6), realAlert(7)]
  assert.deepEqual(dashboardAlerts(log).map((e) => e.title), ['Real 1', 'Real 2', 'Real 3', 'Real 4', 'Real 5'])
  assert.deepEqual(dashboardAlerts([testAlert(0), testAlert(1)]), []) // only test alerts: the card's empty state
  const digestAndHeld = [entry({ kind: 'digest', cve: null }), entry({ kind: 'held' })]
  assert.equal(dashboardAlerts(digestAndHeld).length, 2) // a digest and a held alert are real ones
})

test('F144.2 Settings shows the last 20, test alerts included', () => {
  const log = Array.from({ length: 25 }, (_, i) => (i % 2 ? realAlert(i) : testAlert(i)))
  const shown = settingsAlerts(log)
  assert.equal(shown.length, 20)
  assert.equal(shown[0].title, 'Test 0')
  assert.equal(shown[19].title, 'Real 19')
})

test('F144.3 the dashboard card links the owner to Delivery and anyone else to their Alerts card', () => {
  assert.deepEqual(alertsLink(true), { text: 'Alerts and delivery in Settings', href: '/settings#delivery' })
  assert.deepEqual(alertsLink(false), { text: 'All your alerts in Settings', href: '/settings#alerts' })
})

// The alerts log's words (B04): what an entry was for, and each channel's result. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { AlertLogEntry } from './api.ts'
import { channelResult, entryReason } from './alertsLog.ts'

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

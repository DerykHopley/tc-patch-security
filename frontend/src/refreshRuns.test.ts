// The "Refresh runs" card's words and the schedule line (B19). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { RunRow } from './api.ts'
import { feedLine, ownersSchedule, runCounts, runResult, runWhen, scheduleLine, triggerName } from './refreshRuns.ts'

const row = (over: Partial<RunRow> = {}): RunRow => ({
  trigger: 'schedule',
  started: '2026-10-15T09:00:00+00:00',
  finished: '2026-10-15T09:00:02+00:00',
  result: 'ok',
  duration_s: 2.4,
  counts: { new: 2, updated: 3, kev_added: 1, rescored: 0 },
  new_cves: ['CVE-2026-99102', 'CVE-2026-99101'],
  version: 3,
  feeds: [],
  errors: [],
  alerts_sent: 4,
  alerts_held: 0,
  reason: null,
  next_allowed: null,
  times: 1,
  ...over,
})

test('B19.4 each trigger by the name the app uses for it', () => {
  assert.deepEqual((['button', 'chat', 'schedule', 'cli'] as const).map(triggerName),
    ['Check now', 'Patch', 'Schedule', 'Command line'])
})

test('B19.4 the result in words, with its tone', () => {
  assert.deepEqual(runResult(row()), { text: 'OK', tone: 'ok' })
  assert.deepEqual(runResult(row({ result: 'partial' })), { text: 'Partial', tone: 'warn' })
  assert.deepEqual(runResult(row({ result: 'failed' })), { text: 'Failed', tone: 'error' })
  assert.deepEqual(runResult(row({ result: 'skipped', reason: 'too_soon' })), { text: 'Skipped: too soon', tone: 'muted' })
})

test('B19.4 when and how long, in UTC', () => {
  assert.equal(runWhen(row()), '2026-10-15 09:00 UTC · 2.4 s')
  assert.equal(runWhen(row({ result: 'skipped', duration_s: null })), '2026-10-15 09:00 UTC')
})

test('B19.4 the counts: zero counts left out, alerts sent last', () => {
  assert.equal(runCounts(row()), '2 new · 3 updated · 1 added to KEV · 4 alerts sent')
  assert.equal(runCounts(row({ counts: { new: 0, updated: 0, kev_added: 0, rescored: 1 }, alerts_sent: 1 })),
    '1 rescored · 1 alert sent')
  assert.equal(runCounts(row({ counts: { new: 0, updated: 0, kev_added: 0, rescored: 0 }, alerts_sent: 0 })),
    'Nothing new')
  assert.equal(runCounts(row({ alerts_sent: 0, alerts_held: 2 })), '2 new · 3 updated · 1 added to KEV · 2 alerts held')
  assert.equal(runCounts(row({ result: 'failed', counts: { new: 0, updated: 0, kev_added: 0, rescored: 0 }, alerts_sent: 0 })),
    'Nothing written')
  assert.equal(runCounts(row({ result: 'skipped', counts: null, reason: 'too_soon', next_allowed: '2026-10-15T09:05:00+00:00', times: 3 })),
    'Next allowed 09:05 UTC · asked 3 times')
})

test('B19.4 each feed\'s step in words', () => {
  assert.equal(feedLine({ source: 'nvd', ok: false, message: 'NVD timed out after 30 s.' }), "NVD: didn't answer (NVD timed out after 30 s.)")
  assert.equal(feedLine({ source: 'kev', ok: true, message: null }), 'CISA KEV: answered')
})

test('B19.5 the schedule line: paused, next due, or in live mode only', () => {
  assert.equal(scheduleLine({ hours: 6, paused: true, next_due: null }, 'live'),
    'Schedule paused: no scheduled check starts. Check now and Patch still check.')
  assert.equal(scheduleLine({ hours: 6, paused: false, next_due: '2026-10-15T14:50:00+00:00' }, 'live'),
    'Every 6 hours · next scheduled check from 2026-10-15 14:50 UTC.')
  assert.equal(scheduleLine({ hours: 1, paused: false, next_due: null }, 'live'),
    'Every hour · the next scheduled check runs at the next tick.')
  assert.equal(scheduleLine({ hours: 6, paused: false, next_due: null }, 'snapshot'),
    'Every 6 hours, in live mode. The snapshot never changes.')
})

test('BR.9 another user sees the owner\'s schedule, read-only', () => {
  assert.equal(ownersSchedule({ hours: 6, paused: false, next_due: null }),
    "The owner's schedule: every 6 hours. Only the owner can change or pause it.")
  assert.equal(ownersSchedule({ hours: 1, paused: true, next_due: null }),
    "The owner's schedule: every hour, paused. Only the owner can change or pause it.")
})

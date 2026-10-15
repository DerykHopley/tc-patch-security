// The freshness panel's words (B02): when the data was last checked, and the line after Check now. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CheckReply, RefreshResult } from './api.ts'
import { checkedLine, replyLine, utcTime } from './freshness.ts'

const run = (over: Partial<RefreshResult> = {}): RefreshResult => ({
  trigger: 'button',
  started: '2026-10-15T09:00:00+00:00',
  finished: '2026-10-15T09:00:02+00:00',
  ok: true,
  counts: { new: 2, updated: 1, kev_added: 1, rescored: 0 },
  new_cves: ['CVE-2026-99102', 'CVE-2026-99101'],
  version: 2,
  errors: [],
  ...over,
})

const ran = (result: RefreshResult): CheckReply => ({ ran: true, result, refusal: null })

test('B02.8 a time in UTC, the way the backend writes its messages', () => {
  assert.equal(utcTime('2026-10-15T09:05:00+00:00'), '2026-10-15 09:05 UTC')
  assert.equal(utcTime('2026-10-15T11:05:00+02:00'), '2026-10-15 09:05 UTC')
})

test('B02.8 the last-checked line by mode', () => {
  assert.equal(checkedLine({ mode: 'live', last_checked: '2026-10-15T09:00:00+00:00' }, '2026-10-15'),
    'Last checked 2026-10-15 09:00 UTC.')
  assert.equal(checkedLine({ mode: 'live', last_checked: null }, '2026-10-15'),
    'Not checked yet: the live data is still the snapshot.')
  assert.equal(checkedLine({ mode: 'snapshot', last_checked: null }, '2026-10-13'),
    'A frozen snapshot, as of 2026-10-13.')
})

test('B02.8 the line after Check now: counts, nothing new, a failed feed, a refusal', () => {
  assert.deepEqual(replyLine(ran(run())), { tone: 'ok', text: 'Done: 2 new CVEs, 1 updated, 1 added to KEV.' })
  assert.deepEqual(replyLine(ran(run({ counts: { new: 1, updated: 0, kev_added: 0, rescored: 1 } }))),
    { tone: 'ok', text: 'Done: 1 new CVE, 1 rescored.' })
  assert.deepEqual(replyLine(ran(run({ counts: { new: 0, updated: 0, kev_added: 0, rescored: 0 }, new_cves: [] }))),
    { tone: 'ok', text: 'Done: nothing new since the last check.' })
  assert.deepEqual(replyLine(ran(run({ ok: false, errors: [{ source: 'epss', message: 'timed out' }] }))),
    { tone: 'error', text: 'The check failed (EPSS: timed out). The data is unchanged.' })
  const refused: CheckReply = {
    ran: false,
    result: run(),
    refusal: { reason: 'too_soon', next_allowed: '2026-10-15T09:05:00+00:00', message: '…' },
  }
  assert.deepEqual(replyLine(refused),
    { tone: 'warn', text: 'Checked less than 5 minutes ago. The next check is allowed at 09:05 UTC.' })
  assert.deepEqual(replyLine({ ...refused, refusal: { ...refused.refusal!, reason: 'running' } }),
    { tone: 'warn', text: 'A check is running already. The next one is allowed at 09:05 UTC.' })
})

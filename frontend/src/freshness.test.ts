// The freshness panel's words (B02): when the data was last checked, and the line after Check now. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CheckReply, RefreshResult } from './api.ts'
import { checkedLine, replyLine, runBanner, utcTime } from './freshness.ts'

const run = (over: Partial<RefreshResult> = {}): RefreshResult => ({
  trigger: 'button',
  started: '2026-10-15T09:00:00+00:00',
  finished: '2026-10-15T09:00:02+00:00',
  ok: true,
  counts: { new: 2, updated: 1, kev_added: 1, rescored: 0 },
  new_cves: ['CVE-2026-99102', 'CVE-2026-99101'],
  version: 2,
  errors: [],
  status: 'ok',
  feeds: [],
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
  assert.deepEqual(replyLine(ran(run({ ok: false, status: 'failed', errors: [{ source: 'epss', message: 'timed out' }] }))),
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

// B20: a run where some feeds failed. Each feed is a step; the ones that answered were written.
const feeds = (...failed: string[]) =>
  ['nvd', 'kev', 'osv', 'epss'].map((source) =>
    failed.includes(source) ? { source, ok: false, message: `${source} timed out` } : { source, ok: true, message: null })
const partial = run({
  status: 'partial',
  counts: { new: 0, updated: 1, kev_added: 1, rescored: 0 },
  feeds: feeds('nvd'),
  errors: [{ source: 'nvd', message: 'nvd timed out' }],
})

test('B20.10 never checked in full, but a partial run wrote data: the line does not say "still the snapshot"', () => {
  assert.equal(checkedLine({ mode: 'live', last_checked: null, last_result: partial }, '2026-10-15'),
    'Not checked in full yet: some sources updated (below).')
  assert.equal(checkedLine({ mode: 'live', last_checked: null, last_result: run({ ok: false, status: 'failed' }) }, '2026-10-15'),
    'Not checked yet: the live data is still the snapshot.')
})

test('B20.10 the line after a partial check says it was done in part', () => {
  assert.deepEqual(replyLine(ran(partial)), { tone: 'warn', text: 'Done in part: 1 updated, 1 added to KEV.' })
})

test('B20.10 the banner for a partial or failed last run: what updated, what did not, the next try', () => {
  assert.equal(runBanner(null), null)
  assert.equal(runBanner(run()), null) // every feed answered: no banner
  assert.deepEqual(runBanner(partial), {
    tone: 'warn',
    text: "3 of 4 sources updated at 09:00 UTC · NVD didn't answer · next try 09:05 UTC",
    details: ['NVD: nvd timed out'],
  })
  const two = run({ status: 'partial', feeds: feeds('kev', 'epss') })
  assert.equal(runBanner(two)?.text, "2 of 4 sources updated at 09:00 UTC · CISA KEV and EPSS didn't answer · next try 09:05 UTC")
  const none = run({ ok: false, status: 'failed', version: null, feeds: feeds('nvd', 'kev', 'osv', 'epss') })
  assert.deepEqual(runBanner(none), {
    tone: 'error',
    text: "No source updated at 09:00 UTC · NVD, CISA KEV, OSV and EPSS didn't answer · the data is unchanged · next try 09:05 UTC",
    details: ['NVD: nvd timed out', 'CISA KEV: kev timed out', 'OSV: osv timed out', 'EPSS: epss timed out'],
  })
  // a failed run logged before B20 has no feed steps: its errors say which feed stopped it
  const old = run({ ok: false, status: 'failed', feeds: [], errors: [{ source: 'epss', message: 'down' }] })
  assert.equal(runBanner(old)?.text, "No source updated at 09:00 UTC · EPSS didn't answer · the data is unchanged · next try 09:05 UTC")
})

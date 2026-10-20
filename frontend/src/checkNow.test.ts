// Check now's one piece of logic (B59, #103), shared by the dashboard's Data freshness card and Settings' Refresh
// runs card: ask the server, let the views on screen load again after a good run, and say the line. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CheckReply, RefreshResult } from './api.ts'
import { runCheck } from './checkNow.ts'

const result = (over: Partial<RefreshResult> = {}): RefreshResult => ({
  trigger: 'button',
  started: '2026-10-20T09:00:00+00:00',
  finished: '2026-10-20T09:00:02+00:00',
  ok: true,
  counts: { new: 2, updated: 1, kev_added: 1, rescored: 0 },
  new_cves: ['CVE-2026-99102', 'CVE-2026-99101'],
  version: 2,
  errors: [],
  status: 'ok',
  feeds: [],
  ...over,
})

/** A fake server and a record of what happened, in order. */
function fakes(reply: CheckReply | Error) {
  const calls: string[] = []
  return {
    calls,
    deps: {
      checkNow: async () => {
        calls.push('check')
        if (reply instanceof Error) throw reply
        return reply
      },
      announce: async () => {
        calls.push('announce')
      },
    },
  }
}

test('B59.1 a run that wrote data: the views load again first, then the line says what it found', async () => {
  const { calls, deps } = fakes({ ran: true, result: result(), refusal: null })
  const out = await runCheck(deps)
  assert.deepEqual(calls, ['check', 'announce'])
  assert.deepEqual(out.line, { tone: 'ok', text: 'Done: 2 new CVEs, 1 updated, 1 added to KEV.' })
  assert.equal(out.ran, true)
  assert.equal(out.result?.version, 2)
})

test('B59.1 a refusal: the 5-minute line, nothing loads again, not a run', async () => {
  const { calls, deps } = fakes({
    ran: false,
    result: result(),
    refusal: { reason: 'too_soon', next_allowed: '2026-10-20T09:05:00+00:00', message: 'too soon' },
  })
  const out = await runCheck(deps)
  assert.deepEqual(calls, ['check'])
  assert.deepEqual(out.line, { tone: 'warn', text: 'Checked less than 5 minutes ago. The next check is allowed at 09:05 UTC.' })
  assert.equal(out.ran, false)
})

test('B59.1 a run that failed: the error line, nothing loads again (nothing was written)', async () => {
  const failed = result({ ok: false, status: 'failed', version: null, errors: [{ source: 'epss', message: 'timed out' }] })
  const { calls, deps } = fakes({ ran: true, result: failed, refusal: null })
  const out = await runCheck(deps)
  assert.deepEqual(calls, ['check'])
  assert.deepEqual(out.line, { tone: 'error', text: 'The check failed (EPSS: timed out). The data is unchanged.' })
  assert.equal(out.ran, true) // a run all the same: the dashboard's banner shows it
})

test('B59.1 the server unreachable: its message as an error line, never a throw', async () => {
  const { deps } = fakes(new Error('Network down.'))
  const out = await runCheck(deps)
  assert.deepEqual(out.line, { tone: 'error', text: 'Network down.' })
  assert.equal(out.ran, false)
})

test('B59.1 anyone but the owner: their alerts are in Patch, the same words as the dashboard (B50)', async () => {
  const reply: CheckReply = { ran: true, result: result(), refusal: null,
    alerts_for_you: { sent: 0, recorded: 3, failed: 0, held: 0 } }
  assert.equal((await runCheck(fakes(reply).deps, false)).line.text,
    'Done: 2 new CVEs, 1 updated, 1 added to KEV. 3 alerts in Patch.')
  assert.equal((await runCheck(fakes(reply).deps)).line.text,
    'Done: 2 new CVEs, 1 updated, 1 added to KEV. 3 alerts recorded only (not sent).')
})

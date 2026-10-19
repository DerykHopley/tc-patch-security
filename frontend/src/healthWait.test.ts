// The wait for /health before the app's first paint (#69): the loading screen, the timeout, the retries with
// backoff. A fake clock (node:test's mock timers) stands in for time. `npm test`.
import assert from 'node:assert/strict'
import { afterEach, beforeEach, mock, test } from 'node:test'
import type { Health } from './api.ts'
import { waitForHealth, type HealthResult, type HealthWait } from './healthWait.ts'

const HEALTH = { status: 'ok', auth: { on: false, publishable_key: null } } as Health

/** A /health the test answers by hand: each call is one attempt, aborted by the wait's signal. */
function fakeHealth() {
  const calls: { signal: AbortSignal; answer: (h: Health) => void; fail: (e: Error) => void }[] = []
  const fetchHealth = (signal: AbortSignal) =>
    new Promise<Health>((answer, fail) => {
      calls.push({ signal, answer, fail })
      signal.addEventListener('abort', () => fail(new DOMException('aborted', 'AbortError')))
    })
  return { calls, fetchHealth }
}

function start(fetchHealth: (signal: AbortSignal) => Promise<Health>) {
  const states: HealthWait[] = []
  const results: HealthResult[] = []
  const wait = waitForHealth({ fetchHealth, onChange: (s) => states.push(s), onDone: (r) => results.push(r) })
  return { states, results, wait }
}

const flush = () => new Promise<void>((resolve) => setImmediate(resolve)) // let settled promises run their .then

beforeEach(() => mock.timers.enable({ apis: ['setTimeout', 'Date'], now: 0 }))
afterEach(() => mock.timers.reset())

test('B69.1 /health answering in time hands its answer on, and the screen only ever said it was starting', async () => {
  const api = fakeHealth()
  const { states, results } = start(api.fetchHealth)
  mock.timers.tick(14_000)
  api.calls[0].answer(HEALTH)
  await flush()
  assert.deepEqual(results, [{ ok: true, health: HEALTH }])
  assert.deepEqual(states, [])
  assert.equal(api.calls.length, 1)
})

test('B69.2 no answer in 15 s: the attempt is dropped and the screen says offline, retrying in 2 s', async () => {
  const api = fakeHealth()
  const { states, results } = start(api.fetchHealth)
  mock.timers.tick(14_999)
  assert.deepEqual(states, [])
  mock.timers.tick(1)
  await flush()
  assert.equal(api.calls[0].signal.aborted, true)
  assert.deepEqual(states, [{ state: 'retrying', trying: false, nextTryAt: 17_000 }])
  assert.deepEqual(results, []) // a timeout is not the end: the app still waits
})

test('B69.3 it tries again by itself, waiting 2, 4, 8, 16 s, then every 30 s, and recovers when /health answers', async () => {
  const api = fakeHealth()
  const { states, results } = start(api.fetchHealth)
  const waits: number[] = []
  for (let i = 0; i < 6; i++) {
    mock.timers.tick(15_000) // this attempt times out
    await flush()
    const offline = states.at(-1)!
    assert.equal(offline.trying, false)
    waits.push(offline.nextTryAt! - Date.now())
    mock.timers.tick(offline.nextTryAt! - Date.now())
    assert.deepEqual(states.at(-1), { state: 'retrying', trying: true, nextTryAt: null })
    assert.equal(api.calls.length, i + 2) // the next attempt has started
  }
  assert.deepEqual(waits, [2_000, 4_000, 8_000, 16_000, 30_000, 30_000])
  api.calls.at(-1)!.answer(HEALTH)
  await flush()
  assert.deepEqual(results, [{ ok: true, health: HEALTH }])
  mock.timers.tick(60_000)
  assert.equal(api.calls.length, 7) // and stops asking
})

test('B69.4 Retry tries at once instead of waiting; pressed while a try is on its way, it does nothing', async () => {
  const api = fakeHealth()
  const { states, wait } = start(api.fetchHealth)
  mock.timers.tick(15_000)
  await flush()
  wait.retryNow()
  assert.equal(api.calls.length, 2)
  assert.deepEqual(states.at(-1), { state: 'retrying', trying: true, nextTryAt: null })
  wait.retryNow()
  assert.equal(api.calls.length, 2) // no second request beside the first
  mock.timers.tick(2_000) // the automatic try it replaced doesn't start as well
  assert.equal(api.calls.length, 2)
  mock.timers.tick(13_000) // this try times out in turn: the backoff goes on (4 s)
  await flush()
  assert.equal(states.at(-1)!.nextTryAt! - Date.now(), 4_000)
})

test('B69.5 an outright failure at first is a miss too (B46): the offline screen and its backoff, never the app', async () => {
  // Before B46 the wait ended and the app showed "Backend offline". Without /health nobody knows whether sign-in is
  // on, so the app showed its shell to anyone, signed out or not approved (#81).
  const api = fakeHealth()
  const { states, results } = start(api.fetchHealth)
  api.calls[0].fail(new Error("Can't reach the backend"))
  await flush()
  assert.deepEqual(results, [])
  assert.equal(states.at(-1)!.nextTryAt! - Date.now(), 2_000)
  mock.timers.tick(2_000)
  assert.equal(api.calls.length, 2)
})

test('B69.5 a failure while already retrying is one more miss: the backoff goes on, the screen stays', async () => {
  const api = fakeHealth()
  const { states, results } = start(api.fetchHealth)
  mock.timers.tick(15_000)
  await flush()
  mock.timers.tick(2_000)
  api.calls[1].fail(new Error("Can't reach the backend")) // a cold start can refuse before it answers
  await flush()
  assert.deepEqual(results, [])
  assert.deepEqual(states.at(-1), { state: 'retrying', trying: false, nextTryAt: Date.now() + 4_000 })
  mock.timers.tick(15_000) // the failed try's timeout doesn't count as another miss
  assert.equal(api.calls.length, 3)
  assert.deepEqual(states.at(-1), { state: 'retrying', trying: true, nextTryAt: null })
})

test('B69.6 stop() drops the try on its way and every timer: nothing more is asked or reported', async () => {
  const api = fakeHealth()
  const { states, results, wait } = start(api.fetchHealth)
  wait.stop()
  assert.equal(api.calls[0].signal.aborted, true)
  mock.timers.tick(120_000)
  await flush()
  assert.deepEqual([states, results, api.calls.length], [[], [], 1])
})

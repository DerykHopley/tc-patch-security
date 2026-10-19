// The wait for /health before the app's first paint (#69). /health says whether sign-in is on, so nothing of the
// app can show before it answers; meanwhile the loading screen does. Pure of React, so a fake clock tests it.
import type { Health } from './api.ts'

/** How long one /health attempt may take before the screen says the backend is offline. A Cloud Run cold start
 * answers within this, we expect (its time is unverified, #45). */
export const HEALTH_TIMEOUT_MS = 15_000

/** The waits between attempts after a timeout: doubling from 2 s, then every 30 s. */
export const RETRY_DELAYS_MS = [2_000, 4_000, 8_000, 16_000, 30_000]

/** The loading screen once an attempt has timed out: offline, retrying. `trying`: an attempt is on its way;
 * otherwise `nextTryAt` (ms since the epoch) is when the next one starts. Before the first timeout there is no
 * state: the screen just says Patch is starting. */
export type HealthWait = { state: 'retrying'; trying: boolean; nextTryAt: number | null }

/** How the wait ended: /health answered. (Until B46 it could also fail outright, `ok: false`; now that retries.) */
export type HealthResult = { ok: true; health: Health }

export interface WaitOptions {
  fetchHealth: (signal: AbortSignal) => Promise<Health>
  onChange: (wait: HealthWait) => void
  onDone: (result: HealthResult) => void
}

export function waitForHealth({ fetchHealth, onChange, onDone }: WaitOptions): {
  retryNow: () => void
  stop: () => void
} {
  let attempt: AbortController | null = null
  let timer: ReturnType<typeof setTimeout> | undefined
  let failures = 0

  // One try missed (timed out, or failed after an earlier timeout): wait, longer each time, then try again.
  function miss(controller: AbortController) {
    clearTimeout(timer)
    controller.abort()
    failures += 1
    const delay = RETRY_DELAYS_MS[Math.min(failures, RETRY_DELAYS_MS.length) - 1]
    onChange({ state: 'retrying', trying: false, nextTryAt: Date.now() + delay })
    timer = setTimeout(tryOnce, delay)
  }

  function tryOnce() {
    const controller = new AbortController()
    attempt = controller
    if (failures > 0) onChange({ state: 'retrying', trying: true, nextTryAt: null })
    timer = setTimeout(() => miss(controller), HEALTH_TIMEOUT_MS)
    fetchHealth(controller.signal).then(
      (health) => {
        if (controller.signal.aborted) return // a try we gave up on (timed out, replaced, or stopped)
        clearTimeout(timer)
        onDone({ ok: true, health })
      },
      () => {
        // An outright failure (refused, an error status) is a miss like a timeout (B46, #81). It used to end the
        // wait and show the app saying "Backend offline"; but without /health nobody knows whether sign-in is on,
        // so that showed the app's shell to anyone, signed out or not approved.
        if (!controller.signal.aborted) miss(controller)
      },
    )
  }

  tryOnce()
  return {
    retryNow: () => {
      if (attempt && !attempt.signal.aborted) return // a try is on its way
      clearTimeout(timer) // instead of the automatic one
      tryOnce()
    },
    stop: () => {
      clearTimeout(timer)
      attempt?.abort()
    },
  }
}

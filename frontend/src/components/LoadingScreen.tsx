import { useEffect, useState } from 'react'
import type { HealthWait } from '../healthWait.ts'
import { pickPose } from './patchPose.ts'
import { Robot } from './Robot.tsx'
import { ShieldIcon } from './Icons.tsx'

// The loading screen (#69, DESIGN.md §5.14): what shows until /health answers. It knows nothing of sign-in (that's
// what /health says), so it's the same for everyone: one Playful card, Patch idling over its top edge, the brand,
// and a status line. `wait` null: still starting. Otherwise /health timed out: "Backend offline — retrying", when
// the next try is, and Retry.

export function LoadingScreen({ wait, onRetry }: { wait: HealthWait | null; onRetry: () => void }) {
  const [pose] = useState(() => pickPose('idle', Math.random)) // no mood here: idle, picked once (DESIGN.md §8.3)
  return (
    <div className="loading-page">
      <main className="loading-card" aria-labelledby="loading-status">
        <Robot size={110} variant={pose.variant} />
        <div className="brand loading-brand">
          <span className="brand-mark">
            <ShieldIcon />
          </span>
          <span className="brand-name">
            <span>LLM Security</span>
            <small>assistant</small>
          </span>
        </div>
        <output id="loading-status" className="loading-status">
          {wait ? 'Backend offline — retrying' : 'Waking Patch up…'}
        </output>
        {wait ? (
          <div className="loading-offline">
            <p>
              <NextTry key={wait.nextTryAt ?? 'trying'} wait={wait} />
            </p>
            {/* never disabled: a disabled button drops the keyboard focus; a press mid-try does nothing */}
            <button type="button" onClick={onRetry}>
              Retry
            </button>
          </div>
        ) : (
          <p className="loading-lead">The server can take a few seconds to start after a quiet spell.</p>
        )}
      </main>
    </div>
  )
}

/** When the next try is: "Trying again…" while one is on its way, else "Next try in 8 s.", counting down. Keyed by
 * the next try's time, so each wait starts its count from a fresh clock. */
function NextTry({ wait }: { wait: HealthWait }) {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (wait.nextTryAt === null) return
    const tick = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(tick)
  }, [wait.nextTryAt])
  if (wait.trying || wait.nextTryAt === null) return <>Patch's server didn't answer. Trying again…</>
  const seconds = Math.max(1, Math.ceil((wait.nextTryAt - now) / 1000))
  return <>Patch's server didn't answer. Next try in {seconds} s.</>
}

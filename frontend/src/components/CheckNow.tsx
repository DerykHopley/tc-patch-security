import { useState } from 'react'
import { checkNow } from '../api.ts'
import { runCheck, type CheckOutcome } from '../checkNow.ts'
import type { Tone } from '../freshness.ts'
import { announceWatchlistChanged } from '../watchlistEvents.ts'
import '../styles/checkNow.css'

// Check now in two places (B59, #103): the dashboard's Data freshness card (§5.10) and Settings' Refresh runs card
// (§5.12). One hook, one button and one line, so both say the same words, wait the same way and look the same.

type Line = { tone: Tone; text: string } | null

/** The busy state and the line. `onDone` runs after every press (a run, a refusal or no answer), once the line is
 *  set: the dashboard keeps the run for its banner, Settings loads the run list again. `setLine` lets a card put its
 *  own words in the same line (the dashboard's Resume). */
export function useCheckNow({ owner = true, onDone }: { owner?: boolean; onDone?: (o: CheckOutcome) => void } = {}) {
  const [checking, setChecking] = useState(false)
  const [line, setLine] = useState<Line>(null)
  const check = () => {
    setChecking(true)
    setLine(null)
    void runCheck({ checkNow, announce: announceWatchlistChanged }, owner).then((out) => {
      setLine(out.line)
      setChecking(false)
      onDone?.(out)
    })
  }
  return { checking, line, setLine, check }
}

/** The pill: "Check now", or "Checking…" with the spinner, disabled and aria-busy, at full strength. */
export function CheckNowButton({ checking, onCheck }: { checking: boolean; onCheck: () => void }) {
  return (
    <div className="check-now-row">
      <button type="button" className="check-now" onClick={onCheck} disabled={checking} aria-busy={checking}>
        {checking && <span className="spinner" aria-hidden="true" />}
        {checking ? 'Checking…' : 'Check now'}
      </button>
    </div>
  )
}

/** The line the check leaves. An <output> is a status region; it is always in the page, so a screen reader hears
 *  the line when it appears. */
export function CheckLine({ line }: { line: Line }) {
  return <output className={`check-line${line ? ` ${line.tone}` : ''}`}>{line?.text}</output>
}

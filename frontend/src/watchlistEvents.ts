import { useEffect, useRef } from 'react'
import type { ChatReply } from './api.ts'

// One truth (A15b): the watchlist lives in the backend's state, which the Settings card and Patch's update_watchlist
// both change (Patch's only once you approve its proposal, B21). Whoever changes it announces it here, and every
// view of it that is on screen (the dashboard, the Settings card) loads it again, so a change shows at once.
// The announcement resolves once every view has loaded again: Check now waits for it before it says "Done", so the
// cards above its button have their new size by then and a quick second click lands on the button (#67).
type Listener = () => unknown
const listeners = new Set<Listener>()

/** Tells every view on screen to load again; resolves once they all have (a failed load counts as done). */
export function announceWatchlistChanged(): Promise<void> {
  const loads = [...listeners].map((l) => new Promise((done) => done(l()))) // a listener that throws is done too
  return Promise.allSettled(loads).then(() => undefined)
}

/** A chat answer whose check_updates ran a good check (B06): the CVE data changed, as after Check now, so the
 *  views on screen load again (the same event). A refused or failed check changed nothing. */
export function checkedFromChat(reply: ChatReply): boolean {
  return reply.tool_calls.some((c) => c.name === 'check_updates' && !!c.result?.ran && c.result.ok === true)
}

/** Calls `onChange` after every announced change (the latest `onChange`, without re-subscribing). Return the load's
 *  promise, so the announcement waits for it. */
export function useWatchlistChanged(onChange: () => unknown) {
  const latest = useRef(onChange)
  useEffect(() => {
    latest.current = onChange
  })
  useEffect(() => {
    const listener = () => latest.current()
    listeners.add(listener)
    return () => {
      listeners.delete(listener)
    }
  }, [])
}

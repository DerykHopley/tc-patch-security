import { useEffect, useRef } from 'react'
import type { ChatReply } from './api.ts'

// One truth (A15b): the watchlist lives in the backend's state, which the Settings card and Patch's update_watchlist
// both change (Patch's only once you approve its proposal, B21). Whoever changes it announces it here, and every
// view of it that is on screen (the dashboard, the Settings card) loads it again, so a change shows at once.
const EVENT = 'patch:watchlist-changed'

export function announceWatchlistChanged() {
  window.dispatchEvent(new Event(EVENT))
}

/** A chat answer whose check_updates ran a good check (B06): the CVE data changed, as after Check now, so the
 *  views on screen load again (the same event). A refused or failed check changed nothing. */
export function checkedFromChat(reply: ChatReply): boolean {
  return reply.tool_calls.some((c) => c.name === 'check_updates' && !!c.result?.ran && c.result.ok === true)
}

/** Calls `onChange` after every announced change (the latest `onChange`, without re-subscribing). */
export function useWatchlistChanged(onChange: () => void) {
  const latest = useRef(onChange)
  useEffect(() => {
    latest.current = onChange
  })
  useEffect(() => {
    const handler = () => latest.current()
    window.addEventListener(EVENT, handler)
    return () => window.removeEventListener(EVENT, handler)
  }, [])
}

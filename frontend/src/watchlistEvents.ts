import { useEffect, useRef } from 'react'
import type { ChatReply } from './api.ts'

// One truth (A15b): the watchlist lives in the backend's state, which the Settings card and Patch's update_watchlist
// both change. Whoever changes it announces it here, and every view of it that is on screen (the dashboard, the
// Settings card) loads it again, so a change shows at once wherever you are.
const EVENT = 'patch:watchlist-changed'

export function announceWatchlistChanged() {
  window.dispatchEvent(new Event(EVENT))
}

/** A chat reply in which Patch changed the watchlist, a product's fields or a CVE's status. */
export function changedWatchlist(reply: ChatReply): boolean {
  return reply.tool_calls.some((c) => c.name === 'update_watchlist' && c.status === 'ok')
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

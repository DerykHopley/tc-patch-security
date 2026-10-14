import { useEffect, useState } from 'react'
import { getSettings, type ExplainLevel } from '../api.ts'

// The saved explain level (A19), for the chat header's switch. Loaded when the chat opens; the Settings page
// announces every load and save, so a pinned chat beside it follows a new choice at once.
const EVENT = 'patch:explain-level'

export function announceSavedLevel(level: ExplainLevel) {
  window.dispatchEvent(new CustomEvent<ExplainLevel>(EVENT, { detail: level }))
}

/** The saved level; "normal" (the backend's default) until it has loaded or when the backend can't be reached. */
export function useSavedLevel(): ExplainLevel {
  const [level, setLevel] = useState<ExplainLevel>('normal')
  useEffect(() => {
    let live = true
    getSettings().then(
      (r) => live && setLevel(r.settings.explain_level),
      () => {},
    )
    const onSaved = (e: Event) => setLevel((e as CustomEvent<ExplainLevel>).detail)
    window.addEventListener(EVENT, onSaved)
    return () => {
      live = false
      window.removeEventListener(EVENT, onSaved)
    }
  }, [])
  return level
}

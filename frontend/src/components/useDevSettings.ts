import { useCallback, useEffect, useState } from 'react'
import {
  backToOwnersDevSettings, getDevSettings, saveDevSettings, type DevSettings, type DevSettingsReply,
} from '../api.ts'

// The Dev page's choices: load, edit a draft, then save or discard (the same flow as useSettings, for /dev/settings).
// The chat and the playground read the saved values on the backend, so a save applies on the next call.
export function useDevSettings(onSaved?: () => void) {
  const [reply, setReply] = useState<DevSettingsReply | null>(null)
  const [draft, setDraft] = useState<DevSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // One load fills the form. A load whose effect was cleaned up is dropped: in development React runs the effect
  // twice, and the late answer reset whatever the user had typed since the first (CI run 38847853994).
  useEffect(() => {
    let live = true
    getDevSettings().then(
      (r) => {
        if (!live) return
        setReply(r)
        setDraft(r.settings)
      },
      (e: Error) => live && setError(e.message),
    )
    return () => {
      live = false
    }
  }, [])

  const dirty = !!reply && !!draft && JSON.stringify(reply.settings) !== JSON.stringify(draft)

  const save = useCallback(async () => {
    if (!draft || !reply) return
    setSaving(true)
    setError(null)
    try {
      const r = await saveDevSettings(draft)
      setReply({ ...reply, ...r }) // B45: a reviewer's first save makes their own copy (own_copy)
      setDraft(r.settings)
      setSaved(true)
      onSaved?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }, [draft, reply, onSaved])

  function set(values: Partial<DevSettings>) {
    setDraft((d) => (d ? { ...d, ...values } : d))
    setSaved(false)
  }

  function discard() {
    if (reply) setDraft(reply.settings)
    setError(null)
  }

  /** B45: a reviewer drops their own copy; the form shows the owner's settings again, saved. */
  const backToOwners = useCallback(async () => {
    setSaving(true)
    setError(null)
    try {
      const r = await backToOwnersDevSettings()
      setReply(r)
      setDraft(r.settings)
      setSaved(true)
      onSaved?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }, [onSaved])

  return { reply, draft, dirty, saving, saved, error, save, discard, set, backToOwners }
}

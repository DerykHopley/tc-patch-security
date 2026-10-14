import { useCallback, useEffect, useState } from 'react'
import { getSettings, saveSettings, type AppSettings, type SettingsReply } from '../api.ts'

// Load the saved settings, edit a draft, then save or discard. Shared by Settings and (later) the Dev panel.
export function useSettings() {
  const [reply, setReply] = useState<SettingsReply | null>(null)
  const [draft, setDraft] = useState<AppSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(() => {
    getSettings().then(
      (r) => {
        setReply(r)
        setDraft(r.settings)
        setError(null)
      },
      (e: Error) => setError(e.message),
    )
  }, [])
  useEffect(load, [load])

  const dirty = !!reply && !!draft && JSON.stringify(reply.settings) !== JSON.stringify(draft)

  async function save() {
    if (!draft || !reply) return
    setSaving(true)
    setError(null)
    try {
      const r = await saveSettings(draft)
      setReply({ ...reply, settings: r.settings })
      setDraft(r.settings)
      setSaved(true)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  function patch<K extends keyof AppSettings>(part: K, values: Partial<AppSettings[K]>) {
    setDraft((d) => (d ? { ...d, [part]: { ...d[part], ...values } } : d))
    setSaved(false)
  }

  function discard() {
    if (reply) setDraft(reply.settings)
    setError(null)
  }

  return { reply, draft, dirty, saving, saved, error, save, discard, patch, reload: load }
}

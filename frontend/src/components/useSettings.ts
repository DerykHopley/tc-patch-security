import { useCallback, useEffect, useState } from 'react'
import { getSettings, saveSettings, type AppSettings, type ServerReply, type SettingsReply } from '../api.ts'
import { announceSavedLevel } from '../chat/savedLevel.ts'

// The settings that are groups of values (alerts; later policy), as opposed to single values (explain_level).
type Part = { [K in keyof AppSettings]: AppSettings[K] extends object ? K : never }[keyof AppSettings]

// Load the saved settings, edit a draft, then save or discard. Shared by Settings and (later) the Dev panel.
export function useSettings() {
  const [reply, setReply] = useState<SettingsReply | null>(null)
  const [draft, setDraft] = useState<AppSettings | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  /** Loads the saved settings into the form. `current`: false once this load is out of date, so it's dropped. */
  const load = useCallback((current: () => boolean = () => true) => {
    getSettings().then(
      (r) => {
        if (!current()) return
        setReply(r)
        setDraft(r.settings)
        setError(null)
        announceSavedLevel(r.settings.explain_level) // e.g. after a reset
      },
      (e: Error) => current() && setError(e.message),
    )
  }, [])
  // The first load drops its answer once its effect is cleaned up: in development React runs the effect twice, and
  // the late answer reset whatever the user had changed since the first (the Dev page's race, CI run 38847853994).
  useEffect(() => {
    let live = true
    load(() => live)
    return () => {
      live = false
    }
  }, [load])

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
      announceSavedLevel(r.settings.explain_level) // the chat header's switch follows (A19)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  function patch<K extends Part>(part: K, values: Partial<AppSettings[K]>) {
    setDraft((d) => (d ? { ...d, [part]: { ...d[part], ...values } } : d))
    setSaved(false)
  }

  // A part that is a single value, like the explain level.
  function setValue<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setDraft((d) => (d ? { ...d, [key]: value } : d))
    setSaved(false)
  }

  /** B20: whether a part has unsaved edits, so a failed save can show its error in that part's card. `only` or
   *  `except` narrow a group to some of its keys (the Delivery card is alerts' `channels`). */
  function changed(part: keyof AppSettings, keys: { only?: string[]; except?: string[] } = {}): boolean {
    if (!reply || !draft) return false
    const before = reply.settings[part]
    const edited = draft[part]
    if (typeof before !== 'object' || typeof edited !== 'object') return before !== edited
    const a = before as unknown as Record<string, unknown>
    const b = edited as unknown as Record<string, unknown>
    return Object.keys({ ...a, ...b })
      .filter((k) => (!keys.only || keys.only.includes(k)) && !keys.except?.includes(k))
      .some((k) => JSON.stringify(a[k]) !== JSON.stringify(b[k]))
  }

  function discard() {
    if (reply) setDraft(reply.settings)
    setError(null)
  }

  /** B26: the owner's server settings were saved: their new state, the channels and the time zone. The draft of the
   *  other settings stays as it is. */
  function setServer(r: ServerReply) {
    setReply((old) => (old ? { ...old, server: r.server, channels: r.channels, alert_tz: r.alert_tz } : old))
  }

  return {
    reply, draft, dirty, saving, saved, error, save, discard, patch, setValue, changed, setServer, reload: () => load(),
  }
}

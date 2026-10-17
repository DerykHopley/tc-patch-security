import { useState } from 'react'
import { saveServerSettings, type SecretName, type ServerFields, type ServerReply, type ServerStatus } from '../api.ts'
import { baselineOf, browserZone, serverChanges, type SecretEdits } from '../serverSettings.ts'

// B26: the owner's server settings as a draft next to the other settings, saved by the same save bar. `status` is
// null for anyone but the owner: then there is nothing to edit. `quietSaved`: quiet hours are saved (their zone
// stays the server's until the owner picks one). `onSaved` gets the reply: the new status, channels and time zone.
export function useServerSettings(status: ServerStatus | null | undefined, quietSaved: boolean,
  onSaved: (r: ServerReply) => void) {
  const base = status ? baselineOf(status, browserZone(), quietSaved) : null
  const key = JSON.stringify(base)
  const [draft, setDraft] = useState<ServerFields | null>(base)
  const [secrets, setSecrets] = useState<SecretEdits>({})
  const [loadedFrom, setLoadedFrom] = useState(key)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [justSaved, setJustSaved] = useState(false) // says "Changes saved" until the next edit
  // A new status (the first load, a save, a reset): the form starts again from it
  if (key !== loadedFrom) {
    setLoadedFrom(key)
    setDraft(base)
    setSecrets({})
    setError(null)
  }

  const typed = Object.values(secrets).some((v) => v === null || (v ?? '').trim() !== '')
  const dirty = !!base && !!draft && (JSON.stringify(base) !== JSON.stringify(draft) || typed)

  function set(v: Partial<ServerFields>) {
    setDraft((d) => (d ? { ...d, ...v } : d))
    setJustSaved(false)
  }

  function setSecret(k: SecretName, v: string | null | undefined) {
    setJustSaved(false)
    setSecrets((s) => {
      const next = { ...s }
      if (v === undefined) delete next[k]
      else next[k] = v
      return next
    })
  }

  /** Whether any of these has an unsaved edit, so a failed save shows its error in that card (B20). */
  function changed(keys: readonly (keyof ServerFields | SecretName)[]): boolean {
    if (!base || !draft) return false
    return keys.some((k) => (k in draft ? draft[k as keyof ServerFields] !== base[k as keyof ServerFields] :
      secrets[k as SecretName] !== undefined))
  }

  /** Save what changed. `quietSet`: the other settings being saved have quiet hours. Throws nothing: an error stays
   *  in `error` and the edits stay. Returns the error too, so the page can show the fields it names. */
  async function save(quietSet: boolean): Promise<string | null> {
    if (!status || !base || !draft) return null
    const change = serverChanges(status, base, draft, secrets, quietSet)
    if (Object.keys(change).length === 0) return null
    setSaving(true)
    setError(null)
    try {
      onSaved(await saveServerSettings(change))
      setSecrets({}) // saved: the boxes empty again (a secret is never shown back)
      setJustSaved(true)
      return null
    } catch (e) {
      setError((e as Error).message)
      return (e as Error).message
    } finally {
      setSaving(false)
    }
  }

  function discard() {
    setDraft(base)
    setSecrets({})
    setError(null)
  }

  return {
    status: status ?? null, draft, secrets, dirty, saving, justSaved, error, set, setSecret, changed, save, discard,
  }
}

export type ServerSettingsForm = ReturnType<typeof useServerSettings>

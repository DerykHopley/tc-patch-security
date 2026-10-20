import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { getProfile, saveProfile } from '../api.ts'
import { cleanName, nameProblem, NAME_MAX } from '../profile.ts'
import { Card } from './StatusCard.tsx'

// Your profile (B48, #97; the decisions of #77, DESIGN.md §5.7): anonymous by default. The optional display name is
// the user's own, kept in their state on the server, never taken from Clerk. The app loads it once (App.tsx) and
// shares it here, so the user menu and the Profile card always say the same.

export interface ProfileState {
  name: string | null
  loaded: boolean
  setName: (name: string | null) => void
}

export const ProfileContext = createContext<ProfileState>({ name: null, loaded: false, setName: () => {} })

/** The app's copy of the profile: loaded once, changed by the Profile card. A failed load leaves it anonymous. */
export function useProfileState(): ProfileState {
  const [name, setName] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)
  useEffect(() => {
    getProfile().then((r) => setName(r.name), () => setName(null)).finally(() => setLoaded(true))
  }, [])
  return { name, loaded, setName }
}

/** The name box's edit, saved by the page's save bar. `draft` null: untouched, the saved name shows. */
export function useProfileDraft() {
  const profile = useContext(ProfileContext)
  const [draft, setDraft] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [justSaved, setJustSaved] = useState(false)
  const shown = draft ?? profile.name ?? ''
  const dirty = draft !== null && cleanName(draft) !== profile.name
  const problem = nameProblem(shown)

  const put = useCallback(async (name: string | null) => {
    setSaving(true)
    setError(null)
    try {
      const r = await saveProfile(name)
      profile.setName(r.name)
      setDraft(null)
      return true
    } catch (e) {
      setError((e as Error).message)
      return false
    } finally {
      setSaving(false)
    }
  }, [profile])

  return {
    shown, dirty, problem, saving, error, justSaved, saved: profile.name,
    edit: (v: string) => {
      setDraft(v)
      setJustSaved(false)
    },
    // With the save bar: "Changes saved" there. A name that's too long stays unsaved, its message in the card
    save: async () => {
      if (!dirty || problem) return !problem
      const ok = await put(cleanName(draft ?? ''))
      setJustSaved(ok)
      return ok
    },
    discard: () => {
      setDraft(null)
      setError(null)
    },
    remove: () => put(null), // at once, outside the save bar: the card says so itself
  }
}

export type ProfileDraft = ReturnType<typeof useProfileDraft>

export function ProfileCard({ p }: { p: ProfileDraft }) {
  const [removed, setRemoved] = useState(false)
  return (
    <Card title="Profile" anchor="profile">
      <p className="meta">
        Patch knows you only by your account. A display name is optional: only your user menu shows it. Nobody else
        sees it.
      </p>
      <div className="field-row profile-row">
        <label htmlFor="profile-name">Display name (optional)</label>
        <input id="profile-name" value={p.shown} autoComplete="off" spellCheck={false}
          aria-describedby="profile-name-why" aria-invalid={p.problem ? true : undefined}
          onChange={(e) => {
            p.edit(e.target.value)
            setRemoved(false)
          }} />
      </div>
      <p id="profile-name-why" className="meta">
        Without one, the menu says "Your account". Decision records always say "you". At most {NAME_MAX} characters.
      </p>
      {p.problem && <p role="alert" className="form-error">{p.problem}</p>}
      {p.error && (
        <p role="alert" className="form-error">
          Not saved: {p.error} Your changes are still here; Save changes tries again.
        </p>
      )}
      {p.saved && !p.dirty && (
        <button type="button" className="link-btn" disabled={p.saving}
          onClick={async () => setRemoved(await p.remove())}>
          Remove my name
        </button>
      )}
      <output className="meta profile-done">
        {removed ? 'Name removed: your user menu says "Your account".' : null}
      </output>
    </Card>
  )
}

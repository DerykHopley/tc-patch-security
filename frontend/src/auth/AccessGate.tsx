import {
  createContext,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  type FormEvent,
  type ReactNode,
} from 'react'
import { accessScreen, noteLeft, NOTE_MAX, type Access } from '../access.ts'
import { getAccess, onNotApproved, requestAccess } from '../api.ts'
import { Landing } from '../landing/Landing.tsx'
import { followLink, openPath, PATHS } from '../route.ts'
import { ScreenCard } from './SignInScreen.tsx'
import { subscribeToAddress } from './useFrontDoor.ts'

const ABOUT_PATH = PATHS.about

// Sign-up requests (B38, #81, DESIGN.md §5.13): a signed-in person sees the app only once the owner approved them.
// Until then, one card on the sign-in screen's frame: ask (with an optional note), waiting, or refused. With sign-in
// off the app shows at once, as before (the one local user is the owner); /access is asked alongside, and the app
// gives way only if it says otherwise. No Clerk code here, so the app's main chunk can hold it.

/** The caller's access, for the pages that depend on it (the owner's Requests card). null until /access answers. */
export const AccessContext = createContext<Access | null>(null)

export function AccessGate({ signIn, onSignOut, children }: {
  signIn: boolean
  onSignOut?: () => Promise<void> | void
  children: ReactNode
}) {
  const [access, setAccess] = useState<Access | null>(null)
  const [failed, setFailed] = useState<string | null>(null)
  const load = useCallback(() => {
    setFailed(null)
    return getAccess().then(setAccess, (e: Error) => setFailed(e.message))
  }, [])
  useEffect(() => {
    getAccess().then(setAccess, (e: Error) => setFailed(e.message))
  }, [])
  // B46 (#81): the owner can remove or refuse someone while their tab shows the app. Two ways the tab learns it:
  // any call the backend refuses with 403 not_approved swaps the app for the access card at once (then /access fills
  // in the rest, such as their note), and coming back to the tab (focus, or the tab shown again) asks /access again,
  // which also moves a waiting screen on by itself. A failed quiet check changes nothing.
  useEffect(() => {
    const quiet = () => void getAccess().then(setAccess, () => {})
    onNotApproved((status) => {
      setAccess((a) => (a ? { ...a, status } : { status, owner: false, role: 'viewer', sign_in: true, note: null, at: null }))
      quiet()
    })
    const back = () => {
      if (document.visibilityState !== 'hidden') quiet()
    }
    window.addEventListener('focus', back)
    document.addEventListener('visibilitychange', back)
    return () => {
      onNotApproved(null)
      window.removeEventListener('focus', back)
      document.removeEventListener('visibilitychange', back)
    }
  }, [])
  const path = useSyncExternalStore(subscribeToAddress, () => window.location.pathname)

  if (access?.status === 'approved' || (!signIn && (access === null || failed))) {
    return <AccessContext.Provider value={access}>{children}</AccessContext.Provider>
  }
  // Not approved: nothing of the app (no shell, no page names), at any address. The landing page's content stays
  // theirs at /about (DESIGN.md §5.13, §5.16), its next step back to their request.
  if (access !== null && path.replace(/\/+$/, '') === ABOUT_PATH) return <Landing place="access" />
  if (access === null) {
    return (
      <ScreenCard title="Opening Patch" lead="Checking that this account may use Patch.">
        {failed ? (
          <div className="signin-note signin-failed" role="alert">
            <p>Patch didn't answer: {failed}</p>
            <button type="button" onClick={() => void load()}>Try again</button>
          </div>
        ) : (
          <output className="signin-note">Checking…</output>
        )}
      </ScreenCard>
    )
  }
  return <AccessScreen access={access} onChange={setAccess} onCheck={load} onSignOut={onSignOut} />
}

/** Ask, waiting, or refused: what a signed-in person who isn't approved sees. */
export function AccessScreen({ access, onChange, onCheck, onSignOut }: {
  access: Access
  onChange: (a: Access) => void
  onCheck: () => Promise<void>
  onSignOut?: () => Promise<void> | void
}) {
  const status = access.status === 'approved' ? 'waiting' : access.status
  const { title, lead, form } = accessScreen(status)
  const [note, setNote] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [checked, setChecked] = useState(false)
  const noteId = useId()
  const countId = useId()
  const errorId = useId()
  const shown = useRef(status)

  // A new step (sent, refused) moves the focus to its heading, so a screen reader says where they are now
  useEffect(() => {
    if (shown.current === status) return
    shown.current = status
    document.getElementById('signin-title')?.focus()
  })

  async function send(e: FormEvent) {
    e.preventDefault()
    if (noteLeft(note) < 0) {
      setError(`The note can be at most ${NOTE_MAX} characters.`)
      return
    }
    setBusy(true)
    setError(null)
    try {
      onChange(await requestAccess(note))
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function checkAgain() {
    setBusy(true)
    await onCheck()
    setBusy(false)
    setChecked(true)
  }

  const left = noteLeft(note)
  const signOut = onSignOut && (
    <button type="button" className="access-signout" onClick={() => void onSignOut()}>Sign out</button>
  )
  return (
    <ScreenCard title={title} lead={lead}>
      <div className={`access-step access-${status}`}>
        {form ? (
          <form className="access-form" onSubmit={send} noValidate>
            <label htmlFor={noteId}>A note for the owner <span className="access-optional">(optional)</span></label>
            <textarea
              id={noteId}
              value={note}
              rows={3}
              onChange={(e) => setNote(e.target.value)}
              placeholder="Why you'd like to use Patch"
              aria-describedby={`${countId}${error ? ` ${errorId}` : ''}`}
              aria-invalid={left < 0 || undefined}
            />
            <p id={countId} className={`access-count${left < 0 ? ' over' : ''}`}>
              {left >= 0 ? `${left} characters left` : `${-left} characters too many`}. Only the owner sees it.
            </p>
            {error && <p id={errorId} role="alert" className="form-error">{error}</p>}
            <div className="access-actions">
              <button type="submit" disabled={busy}>{busy ? 'Sending…' : 'Send request'}</button>
              {signOut}
            </div>
          </form>
        ) : (
          <>
            {status === 'waiting' && access.note && (
              <div className="access-mine">
                <span className="access-mine-label">Your note</span>
                <p>{access.note}</p>
              </div>
            )}
            {status === 'waiting' && checked && !busy && (
              <output className="signin-note">Still waiting. The owner hasn't decided yet.</output>
            )}
            <div className="access-actions">
              {status === 'waiting' && (
                <button type="button" className="primary" onClick={() => void checkAgain()} disabled={busy}
                  aria-busy={busy || undefined}>
                  {busy ? 'Checking…' : 'Check again'}
                </button>
              )}
              {signOut}
            </div>
          </>
        )}
        {/* B46: what Patch is, without any of the app: the landing page's content (§5.16) */}
        <a className="access-about" href={ABOUT_PATH} onClick={(e) => followLink(e, openPath)}>What is Patch?</a>
      </div>
    </ScreenCard>
  )
}

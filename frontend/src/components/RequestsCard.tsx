import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import { requestActions, requestLine, type RequestAction, type RequestRow, type RequestsReply } from '../access.ts'
import { accessRequests, changeAccess, removeAccess } from '../api.ts'
import { AccessContext } from '../auth/AccessGate.tsx'
import { Card } from './StatusCard.tsx'

// The Requests card on Settings (B38, #81, DESIGN.md §5.7): the owner's only, with sign-in on. Everyone who asked to
// use Patch, newest first: waiting, approved and refused, with Approve, Refuse, Undo refusal and Remove. Names and
// emails come from Clerk when the card opens (Patch keeps neither); the note, a stranger's words, shows as plain
// text and only here. An alert about a new request opens /settings#requests: the card scrolls into view.

/** Scroll to `el`, and again while the cards above it finish loading (they grow and push it down), until the person
 * scrolls or types themselves, or 3 s pass. Returns the clean-up. */
function keepInView(el: HTMLElement | null, onDone: () => void): (() => void) | undefined {
  if (!el) return undefined
  const go = () => el.scrollIntoView({ block: 'start' })
  go()
  const watch = new ResizeObserver(go)
  watch.observe(document.body)
  const stop = () => {
    watch.disconnect()
    clearTimeout(timer)
    for (const e of ['wheel', 'touchstart', 'keydown', 'pointerdown']) window.removeEventListener(e, done)
  }
  const done = () => {
    stop()
    onDone()
  }
  const timer = setTimeout(done, 3000)
  for (const e of ['wheel', 'touchstart', 'keydown', 'pointerdown']) window.addEventListener(e, done, { once: true })
  return stop
}

const STATUS_WORD: Record<RequestRow['status'], string> = { waiting: 'Waiting', approved: 'Approved', refused: 'Refused' }

export function RequestsCard() {
  const access = useContext(AccessContext)
  const show = !!access?.owner && access.sign_in
  const [reply, setReply] = useState<RequestsReply | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const scrolled = useRef(false)

  const load = useCallback(() => accessRequests().then((r) => {
    setReply(r)
    setError(null)
  }, (e: Error) => setError(e.message)), [])
  useEffect(() => {
    if (show) void load()
  }, [show, load])
  useEffect(() => {
    if (!reply || scrolled.current || window.location.hash !== '#requests') return
    return keepInView(document.getElementById('requests'), () => (scrolled.current = true))
  }, [reply])

  if (!show) return null

  async function act(r: RequestRow, a: RequestAction) {
    const who = r.name ?? r.user_id
    setBusy(r.user_id)
    setError(null)
    setDone(null)
    try {
      if (a.to === 'remove') await removeAccess(r.user_id)
      else await changeAccess(r.user_id, a.to)
      setDone(a.to === 'remove' ? `${who} removed: they can ask again.`
        : a.to === 'approved' ? `${who} approved: Patch opens for them on their next visit.`
          : a.to === 'refused' ? `${who} refused.` : `${who} is waiting again.`)
      await load()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  const people = reply?.requests ?? []
  const waiting = people.filter((p) => p.status === 'waiting').length
  return (
    <Card title="Requests" kind="live" why="People who asked to use Patch; only you see this" anchor="requests">
      <p className="meta">
        {reply === null && !error ? 'Loading the requests…'
          : people.length === 0 ? 'No one has asked to use Patch yet. You get an alert when someone does.'
            : `${waiting === 0 ? 'Nobody' : waiting} waiting. Only you see this card and the notes.`}
      </p>
      {reply && !reply.names && people.length > 0 && (
        <p className="meta" role="note">
          Names and emails come from Clerk, which didn't answer (or the server has no CLERK_SECRET_KEY): user ids only.
        </p>
      )}
      {people.length > 0 && (
        <ul className="request-list">
          {people.map((r) => (
            <li key={r.user_id} className={`request-row request-${r.status}`}>
              <div className="request-who">
                <span className="request-name">{r.name ?? r.user_id}</span>
                {r.email && <span className="request-email">{r.email}</span>}
                <span className={`request-status ${r.status}`}>{STATUS_WORD[r.status]}</span>
              </div>
              <p className="request-line">{requestLine(r, reply?.you ?? null)}</p>
              {r.note && (
                <blockquote className="request-note" aria-label={`Note from ${r.name ?? r.user_id}`}>{r.note}</blockquote>
              )}
              <div className="request-actions">
                {requestActions(r.status).map((a) => (
                  <button key={a.to} type="button" className={a.primary ? 'primary' : undefined}
                    disabled={busy !== null} onClick={() => void act(r, a)}
                    aria-label={`${a.label}: ${r.name ?? r.user_id}`}>
                    {busy === r.user_id ? '…' : a.label}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      {error && <p role="alert" className="form-error">{error}</p>}
      <output className="meta request-done">{done}</output>
    </Card>
  )
}

import { useCallback, useContext, useEffect, useRef, useState } from 'react'
import {
  requestActions, requestLine, ROLE_CHOICES, roleDone, roleHint, type RequestAction, type RequestRow, type RequestsReply,
  type StoredRole,
} from '../access.ts'
import { accessRequests, changeAccess, removeAccess } from '../api.ts'
import { AccessContext } from '../auth/AccessGate.tsx'
import { keepInView } from '../keepInView.ts'
import { Card } from './StatusCard.tsx'

// The Requests card on Settings (B38, #81, DESIGN.md §5.7): the owner's only, with sign-in on. Everyone who asked to
// use Patch, newest first: waiting, approved and refused, with Approve, Refuse, Undo refusal and Remove. Names and
// emails come from Clerk when the card opens (Patch keeps neither); the note, a stranger's words, shows as plain
// text and only here. An alert about a new request opens /settings#requests: the card scrolls into view.
// B45 (#90): a role per person (Viewer, Trusted, Reviewer), picked before Approve or changed later with Save role.

const STATUS_WORD: Record<RequestRow['status'], string> = { waiting: 'Waiting', approved: 'Approved', refused: 'Refused' }

export function RequestsCard() {
  const access = useContext(AccessContext)
  const show = !!access?.owner && access.sign_in
  const [reply, setReply] = useState<RequestsReply | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [done, setDone] = useState<string | null>(null)
  const [picks, setPicks] = useState<Record<string, StoredRole>>({})
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

  /** B45: the role picked in a person's select (their saved one until changed). */
  const pick = (r: RequestRow): StoredRole => picks[r.user_id] ?? r.role

  async function run(r: RequestRow, call: () => Promise<unknown>, message: string) {
    setBusy(r.user_id)
    setError(null)
    setDone(null)
    try {
      await call()
      setDone(message)
      await load()
      setPicks((p) => {
        const next = { ...p }
        delete next[r.user_id] // the select shows the saved role again
        return next
      })
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(null)
    }
  }

  function act(r: RequestRow, a: RequestAction) {
    const who = r.name ?? r.user_id
    // Approving a waiting person gives them the role picked next to the button (B45); Viewer unless changed
    const role = a.to === 'approved' && r.status === 'waiting' ? pick(r) : undefined
    return run(r, () => (a.to === 'remove' ? removeAccess(r.user_id) : changeAccess(r.user_id, { status: a.to, role })),
      a.to === 'remove' ? `${who} removed: they can ask again.`
        : a.to === 'approved' ? `${who} approved: Patch opens for them on their next visit.`
          : a.to === 'refused' ? `${who} refused.` : `${who} is waiting again.`)
  }

  function saveRole(r: RequestRow) {
    const role = pick(r)
    return run(r, () => changeAccess(r.user_id, { role }), roleDone(r.name ?? r.user_id, role))
  }

  const people = reply?.requests ?? []
  const waiting = people.filter((p) => p.status === 'waiting').length
  return (
    <Card title="Requests" anchor="requests">
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
              {r.status !== 'refused' && (
                <div className="request-role">
                  <label htmlFor={`role-${r.user_id}`}>Role</label>
                  <select id={`role-${r.user_id}`} value={pick(r)} disabled={busy !== null}
                    aria-label={`Role for ${r.name ?? r.user_id}`} aria-describedby={`role-${r.user_id}-hint`}
                    onChange={(e) => setPicks((p) => ({ ...p, [r.user_id]: e.target.value as StoredRole }))}>
                    {ROLE_CHOICES.map((c) => <option key={c.value} value={c.value}>{c.label}</option>)}
                  </select>
                  <span id={`role-${r.user_id}-hint`} className="request-role-hint">{roleHint(pick(r))}</span>
                </div>
              )}
              <div className="request-actions">
                {r.status === 'approved' && pick(r) !== r.role && (
                  <button type="button" className="primary" disabled={busy !== null} onClick={() => void saveRole(r)}
                    aria-label={`Save role: ${r.name ?? r.user_id}`}>
                    {busy === r.user_id ? '…' : 'Save role'}
                  </button>
                )}
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

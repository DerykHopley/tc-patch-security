import { Fragment, useEffect, useId, useRef, useState, type FormEvent, type MouseEvent, type ReactNode } from 'react'
import {
  approveProposal,
  cancelProposal,
  editProposal,
  getProposal,
  type CveStatus,
  type ProductUsage,
  type ProposalEdit,
} from '../api.ts'
import { DecisionFields, readDecision } from '../components/Decision.tsx'
import { ExternalLink } from '../components/ExternalLink.tsx'
import { USAGE_LABEL, USAGES } from '../components/Verdict.tsx'
import { STATUS_LABEL } from '../cveView.ts'
import { openPath } from '../route.ts'
import { proposalAfter } from '../toolCalls.ts'
import type { Proposal } from '../toolResults.ts'
import { announceWatchlistChanged } from '../watchlistEvents.ts'
import '../styles/proposals.css'

// A change Patch proposes (B21, DESIGN.md §6.6): what, why, before → after, and Approve, Edit, Cancel. Nothing
// changes until you approve. The backend makes approving idempotent; the buttons are also off while a request runs,
// so a double click sends one.

// The latest state of each proposal on this page: the card is drawn again when the chat closes and opens, and must
// not go back to "proposed" after you approved it.
const latest = new Map<string, Proposal>()

/** A proposal as its card shows it now: approved or cancelled since the answer came (the chat's Export, F147). */
export const shownProposal = (p: Proposal): Proposal => latest.get(p.proposal_id) ?? p

const STATUSES: CveStatus[] = ['fixed', 'not_affected', 'open', 'accepted']
const utcTime = (iso: string) => `${iso.slice(11, 16)} UTC`

/** Where "Done" links to, by the proposal's `link_to` (B27): the CVE in the CVEs page (its product and its new
 *  status: a closed CVE sorts after every open one, B33, so "all" could put it pages away), or the watchlist in
 *  Settings. The backend names the kind; the page addresses live here. */
function doneLink(p: Proposal): { href: string; label: string } {
  if (p.link_to === 'cve' && p.cve_id && p.product) {
    const status = p.fields.status ?? 'all'
    return {
      href: `/cves?product=${encodeURIComponent(p.product)}&status=${status}`,
      label: `See ${p.cve_id} on the CVEs page`,
    }
  }
  return { href: '/settings', label: 'See your watchlist in Settings' }
}

/** A CVE's status and its decision record's fields, as the CVE decision dialog asks them. */
function StatusInput({ p }: { p: Proposal }) {
  const [status, setStatus] = useState<CveStatus>(p.fields.status ?? 'fixed')
  return (
    <>
      <label>
        Status
        <select name="status" value={status} onChange={(e) => setStatus(e.target.value as CveStatus)}>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {STATUS_LABEL[s]}
            </option>
          ))}
        </select>
      </label>
      {/* key: a new status starts its own fields */}
      <DecisionFields key={status} status={status} asOf={p.as_of} values={status === p.fields.status ? p.fields : null} />
    </>
  )
}

type Field = Proposal['editable'][number]
interface Input {
  draw: (p: Proposal, id: string) => ReactNode
  read: (form: HTMLFormElement) => ProposalEdit
}

// Each field the card can edit (the proposal's `editable`, B27), as its input and how to read it back. A new kind of
// proposal needs only its fields here. null: the decision record's fields, drawn with the status (DecisionFields).
const WITH_STATUS = null
const INPUTS: Record<Field, Input | null> = {
  status: {
    draw: (p) => <StatusInput key="status" p={p} />,
    read: (form) => readDecision(form, new FormData(form).get('status') as CveStatus),
  },
  justification: WITH_STATUS,
  note: WITH_STATUS,
  reason: WITH_STATUS,
  review_date: WITH_STATUS,
  compensating_control: WITH_STATUS,
  usage: {
    draw: (p) => (
      <label key="usage">
        Usage
        <select name="usage" defaultValue={p.fields.usage ?? 'self_hosted'}>
          {USAGES.map((u) => (
            <option key={u} value={u}>
              {USAGE_LABEL[u]}
            </option>
          ))}
        </select>
      </label>
    ),
    read: (form) => ({ usage: new FormData(form).get('usage') as ProductUsage }),
  },
  version: {
    draw: (p, id) => (
      <Fragment key="version">
        <label>
          Version
          <input name="version" maxLength={40} defaultValue={p.fields.version ?? ''} aria-describedby={`${id}-v`} />
        </label>
        <span id={`${id}-v`} className="meta">
          Leave it empty if you don't know it.
        </span>
      </Fragment>
    ),
    // empty clears it, as in Settings
    read: (form) => ({ version: String(new FormData(form).get('version') ?? '').trim() }),
  },
  internet_facing: {
    draw: (p) => (
      <label key="internet_facing" className="check">
        <input type="checkbox" name="internet_facing" defaultChecked={!!p.fields.internet_facing} />
        Internet-facing
      </label>
    ),
    read: (form) => ({ internet_facing: new FormData(form).get('internet_facing') === 'on' }),
  },
}

function inApp(e: MouseEvent<HTMLAnchorElement>) {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return // a new tab: the browser's
  e.preventDefault()
  openPath(e.currentTarget.getAttribute('href') ?? '/')
}

function EditForm({ p, onSave, onBack, busy }: {
  p: Proposal
  onSave: (body: ProposalEdit) => void
  onBack: () => void
  busy: boolean
}) {
  const id = useId()
  const ref = useRef<HTMLFormElement>(null)
  const inputs = p.editable.flatMap((f) => INPUTS[f] ?? [])

  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('select, input, textarea')?.focus()
  }, [])

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const form = e.currentTarget
    onSave(Object.assign({}, ...inputs.map((i) => i.read(form))) as ProposalEdit)
  }

  return (
    <form ref={ref} className="proposal-edit" onSubmit={submit} aria-label={`Edit: ${p.title}`}>
      {inputs.map((i) => i.draw(p, id))}
      <div className="proposal-buttons">
        <button type="submit" disabled={busy}>
          Save changes
        </button>
        <button type="button" onClick={onBack} disabled={busy}>
          Back
        </button>
      </div>
    </form>
  )
}

/** What a proposed decision rests on (B22): each cited source with its number, a link, and where it's from. A web
 *  source always says "Web result, unverified", as it does in the answer's sources. */
function ProposalSources({ p }: { p: Proposal }) {
  if (p.sources.length === 0) return null
  return (
    <div className="proposal-sources">
      <p className="meta">It rests on:</p>
      <ul>
        {p.sources.map((s) => (
          <li key={s.n}>
            <span className="source-n">{s.n}</span>{' '}
            <ExternalLink href={s.url}>{s.title}</ExternalLink>{' '}
            {s.kind === 'web' ? (
              <span className="chip web-unverified">Web result, unverified</span>
            ) : (
              <span className="chip source-kb">Knowledge base</span>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}

/** `restored`: the answer was read back after a reload (B49 C5): the proposal may have been approved, cancelled or
 *  expired since, so the card asks the server once for its state. */
export function ProposalCard({ proposal, restored = false }: { proposal: Proposal; restored?: boolean }) {
  const titleId = useId()
  const [p, setP] = useState<Proposal>(() => shownProposal(proposal))
  const [busy, setBusy] = useState<'approve' | 'cancel' | 'save' | null>(null)
  const [editing, setEditing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const approveRef = useRef<HTMLButtonElement>(null)
  const id = p.proposal_id

  useEffect(() => {
    if (!restored || latest.has(id)) return
    // Only while nothing was done on this card meanwhile: an older answer never undoes a newer state
    getProposal(id).then((next) => latest.has(id) || keep(next), () => {})
  }, [restored, id])

  function keep(next: Proposal) {
    latest.set(next.proposal_id, next)
    setP(next)
  }

  async function act(kind: 'approve' | 'cancel' | 'save', run: () => Promise<Proposal>) {
    if (busy) return // a second click while the first runs sends nothing
    setBusy(kind)
    setError(null)
    try {
      const next = await run()
      keep(next)
      if (kind === 'approve') announceWatchlistChanged() // the dashboard, CVEs page and Settings load it again
      if (kind === 'save') setEditing(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Try again.')
      if (kind !== 'save') getProposal(id).then(keep, () => {}) // expired or cancelled elsewhere: show it
    } finally {
      setBusy(null)
    }
  }

  // Back from Edit (or saved): focus goes to Approve, the next step, instead of being lost with the form.
  const wasEditing = useRef(false)
  useEffect(() => {
    if (wasEditing.current && !editing) approveRef.current?.focus()
    wasEditing.current = editing
  }, [editing])

  const open = p.state === 'proposed'
  const editable = p.editable.length > 0
  const link = doneLink(p)
  const after = proposalAfter(p) // B49 C3: "Accepted, review 2026-11-17", the reason on its own line
  return (
    <section className={`proposal-card ${p.state}`} aria-labelledby={titleId}>
      <p className="proposal-kicker">
        <span className={`chip proposal-state ${p.state}`}>
          {{ proposed: 'Proposed', approved: 'Done', cancelled: 'Cancelled', expired: 'Expired' }[p.state]}
        </span>
        <span className="meta">Patch proposes a change</span>
      </p>
      <p id={titleId} className="result-title">
        {p.title}
      </p>
      {p.why && <p className="meta">Why: {p.why}</p>}
      <p className="before-after">
        <span className="before">
          <span className="visually-hidden">Before: </span>
          {p.before}
        </span>
        <span className="arrow" aria-hidden="true">
          →
        </span>
        <span className="after">
          <span className="visually-hidden">After: </span>
          {after.after}
        </span>
      </p>
      {after.lines.map((line) => (
        <p key={line} className="after-line">
          {line}
        </p>
      ))}
      {/* B73 (#134): what to check before approving, right under the control's line. Words from the backend. An
          answer kept in the tab from before B73 has none (`?? []`). */}
      {(p.warnings ?? []).map((w) => (
        <p key={w} className="proposal-line warn proposal-warning">
          <span className="visually-hidden">Warning: </span>
          {w}
        </p>
      ))}
      <ProposalSources p={p} />
      {open && !editing && (
        <p className="meta">Nothing has changed yet. Approve it by {utcTime(p.expires_at)}, or ask Patch again later.</p>
      )}
      {open && editing && (
        <EditForm
          p={p}
          busy={busy !== null}
          onBack={() => {
            setEditing(false)
            setError(null)
          }}
          onSave={(body) => act('save', () => editProposal(id, body))}
        />
      )}
      {error && (
        <p className="proposal-line error" role="alert">
          {error}
        </p>
      )}
      {open && !editing && (
        <div className="proposal-buttons">
          <button
            ref={approveRef}
            type="button"
            className="primary"
            disabled={busy !== null}
            aria-busy={busy === 'approve' || undefined}
            onClick={() => act('approve', () => approveProposal(id))}
          >
            {busy === 'approve' ? 'Approving…' : 'Approve'}
          </button>
          {editable && (
            <button type="button" disabled={busy !== null} onClick={() => setEditing(true)}>
              Edit
            </button>
          )}
          <button type="button" disabled={busy !== null} onClick={() => act('cancel', () => cancelProposal(id))}>
            Cancel
          </button>
        </div>
      )}
      <output className={`proposal-line ${p.state === 'approved' ? 'ok' : p.state === 'proposed' ? '' : 'warn'}`}>
        {p.state === 'approved' && (
          <>
            Done: {p.message}{' '}
            <a href={link.href} onClick={inApp}>
              {link.label}
            </a>
          </>
        )}
        {p.state === 'cancelled' && 'Cancelled: nothing was changed.'}
        {p.state === 'expired' && 'Expired: nothing was changed. Ask Patch to propose it again.'}
      </output>
    </section>
  )
}

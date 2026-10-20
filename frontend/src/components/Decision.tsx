import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent } from 'react'
import type { CveRow, CveStatus, Decision, DecisionInput, Justification } from '../api.ts'
import { JUSTIFICATION_LABEL, STATUS_LABEL } from '../cveView.ts'
import type { DecisionRequest } from '../cveActions.ts'
import { whoDecided } from '../decisionWho.ts'

// Decision records (A16b, DESIGN.md §5.9): the dialog every status change goes through, the current decision under
// the status, the append-only history, and the "No fix yet" mark. Only the user decides: nothing here is clicked for
// them, and Patch can't accept a risk at all.

export const JUSTIFICATIONS: Justification[] = [
  'component_not_present',
  'vulnerable_code_not_present',
  'vulnerable_code_not_in_execute_path',
  'vulnerable_code_cannot_be_controlled_by_adversary',
  'inline_mitigations_already_exist',
]

const REVIEW_DAYS = 90 // the default review date: the as-of date + 90 days

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + days)
  return d.toISOString().slice(0, 10)
}

/** What the dialog asks for. `preset`: "Mark not affected?" pre-selects a justification and the verdict's reason. */
export type { DecisionRequest } // defined in cveActions.ts, so `npm test` can check the actions that build one

const TITLE: Record<CveStatus, (cve: string, again?: boolean) => string> = {
  accepted: (cve, again) => (again ? `Accept the risk of ${cve} again` : `Accept the risk of ${cve}`),
  not_affected: (cve) => `Mark ${cve} not affected`,
  fixed: (cve) => `Mark ${cve} fixed`,
  open: (cve) => `Reopen ${cve}`,
}
const SUBMIT: Record<CveStatus, string> = {
  accepted: 'Accept the risk',
  not_affected: 'Mark not affected',
  fixed: 'Mark fixed',
  open: 'Reopen',
}
const NOTE_HINT: Partial<Record<CveStatus, string>> = {
  fixed: 'For example the version you upgraded to.',
  open: 'For example why it came back.',
  not_affected: 'What you checked.',
}

const FOCUSABLE = 'button, input, select, textarea, a[href], [tabindex]:not([tabindex="-1"])'

/** A status's decision record fields as the form sends them: blank ones left out. */
export function readDecision(formEl: HTMLFormElement, status: CveStatus): DecisionInput {
  const form = new FormData(formEl)
  const text = (name: string) => {
    const v = form.get(name)
    return typeof v === 'string' && v.trim() ? v.trim() : undefined
  }
  const body: DecisionInput = { status }
  if (status === 'accepted') {
    body.reason = text('reason')
    body.review_date = text('review_date')
    body.compensating_control = text('compensating_control')
  } else {
    body.note = text('note')
    if (status === 'not_affected') body.justification = text('justification') as Justification | undefined
  }
  return body
}

/** The fields a status's decision record takes, with the same limits everywhere: the CVEs page's dialog and the
 *  chat's proposal card when you edit it (B21). `values`: what to start from. The first field has data-autofocus. */
export function DecisionFields({ status, asOf, values }: {
  status: CveStatus
  asOf: string
  values?: Partial<Pick<Decision, 'justification' | 'reason' | 'note' | 'review_date' | 'compensating_control'>> | null
}) {
  if (status === 'accepted') {
    return (
      <>
        <p className="meta">
          It leaves the open list and the counts until its review date. Then it comes back as "review due".
        </p>
        <label>
          Reason (required)
          <input
            name="reason"
            required
            maxLength={300}
            data-autofocus
            defaultValue={values?.reason ?? undefined}
            placeholder="Why the risk is acceptable for now"
          />
        </label>
        <label>
          Review date (required)
          <input
            name="review_date"
            type="date"
            required
            min={addDays(asOf, 1)}
            defaultValue={values?.review_date ?? addDays(asOf, REVIEW_DAYS)}
          />
        </label>
        <label>
          Compensating control (optional)
          <input
            name="compensating_control"
            maxLength={300}
            defaultValue={values?.compensating_control ?? undefined}
            placeholder='For example "behind auth", "WAF rule"'
          />
        </label>
      </>
    )
  }
  return (
    <>
      {status === 'not_affected' && (
        <fieldset className="justifications">
          <legend>Why isn't it affected? (required)</legend>
          {JUSTIFICATIONS.map((j, i) => (
            <label key={j}>
              <input
                type="radio"
                name="justification"
                value={j}
                required
                defaultChecked={values?.justification === j}
                data-autofocus={(values?.justification ? values.justification === j : i === 0) || undefined}
              />
              {JUSTIFICATION_LABEL[j]}
            </label>
          ))}
        </fieldset>
      )}
      <label>
        Note (optional)
        <textarea
          name="note"
          rows={2}
          maxLength={500}
          defaultValue={values?.note ?? undefined}
          placeholder={NOTE_HINT[status]}
          data-autofocus={status === 'fixed' || status === 'open' || undefined}
        />
      </label>
    </>
  )
}

/** A modal dialog: focus stays inside (Tab wraps), Esc closes it, focus goes back to the button that opened it. */
export function DecisionDialog({ request, asOf, onSubmit, onClose }: {
  request: DecisionRequest
  asOf: string
  onSubmit: (body: DecisionInput) => Promise<void>
  onClose: () => void
}) {
  const ref = useRef<HTMLDialogElement>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const { cve, status, again, preset } = request

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    const dialog = ref.current
    if (dialog && !dialog.open) dialog.showModal()
    dialog?.querySelector<HTMLElement>('[data-autofocus]')?.focus()
    return () => {
      dialog?.close()
      opener?.focus()
    }
  }, [])

  function trap(e: KeyboardEvent<HTMLDialogElement>) {
    if (e.key !== 'Tab' || !ref.current) return
    const items = [...ref.current.querySelectorAll<HTMLElement>(FOCUSABLE)].filter((el) => !el.hasAttribute('disabled'))
    if (items.length === 0) return
    const first = items[0]
    const last = items[items.length - 1]
    if (e.shiftKey && document.activeElement === first) {
      e.preventDefault()
      last.focus()
    } else if (!e.shiftKey && document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }

  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    const body = readDecision(e.currentTarget, status)
    setBusy(true)
    try {
      await onSubmit(body)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong. Try again.')
      setBusy(false)
    }
  }

  const titleId = `decision-title-${cve}`
  return (
    <dialog
      ref={ref}
      className="decision-dialog"
      aria-labelledby={titleId}
      onKeyDown={trap}
      onCancel={(e) => {
        e.preventDefault() // Esc: close through React, so focus goes back to the opener
        onClose()
      }}
    >
      <form method="dialog" onSubmit={submit}>
        <h2 id={titleId}>{TITLE[status](cve, again)}</h2>
        <DecisionFields status={status} asOf={asOf} values={preset} />
        {error && (
          <p className="dialog-error" role="alert">
            {error}
          </p>
        )}
        <div className="dialog-buttons">
          <button type="button" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" disabled={busy}>
            {SUBMIT[status]}
          </button>
        </div>
      </form>
    </dialog>
  )
}

/** "No fix yet · open N days": OSV lists no fixed version, so it isn't overdue; the due date says "decide by". */
export function NoFixMark({ days }: { days: number }) {
  return (
    <span className="chip no-fix" title="OSV lists no fixed version: accept, mitigate or replace by the decide-by date">
      No fix yet · open {days} days
    </span>
  )
}

function when(d: Decision): string {
  return d.decided_at ? `${d.decided_at.slice(0, 16).replace('T', ' ')} UTC` : 'date not recorded'
}

/** The facts a record adds to its status, in one line. */
function facts(d: Decision): string[] {
  return [
    d.justification ? JUSTIFICATION_LABEL[d.justification] : null,
    d.reason,
    d.compensating_control ? `Control: ${d.compensating_control}` : null,
    d.review_date ? `review ${d.review_date}` : null,
    d.note,
    // what a decision Patch proposed rested on (B22); a web source stays marked unverified
    d.sources?.length
      ? `Sources: ${d.sources.map((s) => `[${s.n}] ${s.title}${s.kind === 'web' ? ' (web result, unverified)' : ''}`).join('; ')}`
      : null,
  ].filter((x): x is string => !!x)
}

/** The current decision under the status: the acceptance (reason, review date, control) or the justification and
 *  note. Nothing for a CVE nobody has decided on. */
export function DecisionSummary({ row }: { row: CveRow }) {
  const d = row.decision
  if (!d || d.status !== row.status) return null
  return (
    <div className="decision">
      {row.status === 'accepted' && (
        <span className="review-date">
          {d.review_date ? `${row.review_due ? 'Review was due' : 'Review on'} ${d.review_date}` : 'No review date'}
        </span>
      )}
      {facts({ ...d, review_date: null }).map((f) => (
        <span key={f} className="decision-fact">
          {f}
        </span>
      ))}
    </div>
  )
}

/** The append-only history, oldest first, behind a disclosure so the row stays short. */
export function DecisionHistory({ row }: { row: CveRow }) {
  if (row.history.length === 0) return null
  return (
    <details className="history">
      <summary aria-label={`History of ${row.id}: ${row.history.length} decisions`}>
        History ({row.history.length})
      </summary>
      <HistoryList history={row.history} />
    </details>
  )
}

/** The decision records, oldest first: when (UTC), the status, its facts, and who decided where. The CVEs list shows
 *  it behind a disclosure; the page for one CVE (B35) shows it open. */
export function HistoryList({ history }: { history: Decision[] }) {
  return (
    <ol>
      {history.map((h, i) => (
        <li key={i}>
          <span className="history-when num">{when(h)}</span>
          <strong>{STATUS_LABEL[h.status]}</strong>
          {facts(h).length > 0 && <span> · {facts(h).join(' · ')}</span>}
          <span className="history-who">
            {' '}
            · {whoDecided(h)}
          </span>
        </li>
      ))}
    </ol>
  )
}

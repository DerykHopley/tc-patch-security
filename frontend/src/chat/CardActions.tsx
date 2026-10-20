import { createContext, useContext, useEffect, useId, useRef, useState, type FormEvent } from 'react'
import { ApiError, cardAction, type CardAction, type PageContext, type RefineFilter } from '../api.ts'
import { refineButtons, type ChangeButton } from '../cardActions.ts'
import { DecisionFields, readDecision } from '../components/Decision.tsx'
import type { Proposal } from '../toolResults.ts'
import { ProposalCard } from './ProposalCard.tsx'
import type { RefinedResult } from './useChat.ts'
import '../styles/cardActions.css'
import '../styles/checkNow.css' // the spinner on a busy button, shared with Check now (§5.10)

// Buttons on tool cards (B24, DESIGN.md §6.7): the next step is a click, sent as a structured action.
// - A change (Watch this product, Set my version…, Mark not affected…, Mark accepted…) only proposes: its card shows
//   right here, and nothing changes until you approve it (B21). "…" buttons first ask for what the change needs.
// - A refine (Show only CVEs, Only critical) runs the search again at once; the result is a new message at the end
//   of the chat, with chips saying what was applied.
// - Ask about this asks Patch about that CVE, with the CVE in the page context (A18), as on the CVEs page.

/** What the buttons need from the chat. Outside a chat (none provided) they do nothing. */
export interface CardActionsHandle {
  ask: (cve: string, page: PageContext) => void
  addRefined: (r: RefinedResult) => void
  pending: boolean // a reply is on its way: the chat takes no new question
  asOf: string | null // the data's as-of date: an accepted risk's review date must be after it
}

export const CardActionsContext = createContext<CardActionsHandle>({
  ask: () => {},
  addRefined: () => {},
  pending: false,
  asOf: null,
})

// B11: refusals that aren't faults, shown as a quiet line
const QUIET = new Set(['rate_limited', 'spending_cap'])

const today = () => new Date().toISOString().slice(0, 10)

type ProposeBody = Extract<CardAction, { action: 'propose' }>
type FormFields = Omit<ProposeBody, 'action' | 'change'>
type FormKind = 'set_version' | 'not_affected' | 'accepted'
const LABEL: Record<ChangeButton | 'accepted', string> = {
  watch: 'Watch this product',
  set_version: 'Set my version…',
  not_affected: 'Mark not affected…',
  accepted: 'Mark accepted…',
}

/** What a change button made: its proposals (newest last), or the line saying it's already so. Kept per card for the
 *  page's lifetime, so switching the details' tabs or closing the chat doesn't lose them. */
interface Made {
  proposals: Proposal[]
  message: string | null
}
const made = new WeakMap<object, Map<string, Made>>()

function ProposeForm({ kind, product, asOf, busy, onSubmit, onBack }: {
  kind: FormKind
  product: string
  asOf: string
  busy: boolean
  onSubmit: (fields: FormFields) => void
  onBack: () => void
}) {
  const id = useId()
  const ref = useRef<HTMLFormElement>(null)
  useEffect(() => {
    ref.current?.querySelector<HTMLElement>('input, select, textarea')?.focus()
  }, [])

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault()
    if (kind === 'set_version') {
      const v = new FormData(e.currentTarget).get('version')
      onSubmit({ version: typeof v === 'string' ? v.trim() : '' })
    } else {
      onSubmit(readDecision(e.currentTarget, kind) as FormFields) // status is the form's own kind
    }
  }

  return (
    <form ref={ref} className="proposal-edit card-action-form" onSubmit={submit} aria-label={LABEL[kind].slice(0, -1)}>
      {kind === 'set_version' ? (
        <>
          <label>
            Your version of {product}
            <input name="version" maxLength={40} aria-describedby={`${id}-v`} />
          </label>
          <span id={`${id}-v`} className="meta">
            As in Settings, for example 1.4.2. Leave it empty if you don't know it.
          </span>
        </>
      ) : (
        <DecisionFields status={kind} asOf={asOf} />
      )}
      <p className="meta">Patch proposes it next; nothing changes until you approve.</p>
      <div className="proposal-buttons">
        <button type="submit" className="primary" disabled={busy} aria-busy={busy || undefined}>
          {busy ? 'Proposing…' : 'Propose'}
        </button>
        <button type="button" onClick={onBack} disabled={busy}>
          Back
        </button>
      </div>
    </form>
  )
}

/** A card's change buttons for one CVE or one product. `owner` (the tool result) and `keyId` (the CVE or product in
 *  it) keep its proposals across re-renders. */
export function ChangeActions({ owner, keyId, cve, product, buttons }: {
  owner: object
  keyId: string
  cve?: string
  product: string
  buttons: (ChangeButton | 'accepted')[]
}) {
  const { asOf } = useContext(CardActionsContext)
  const [state, setState] = useState<Made>(() => made.get(owner)?.get(keyId) ?? { proposals: [], message: null })
  const [form, setForm] = useState<FormKind | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const listRef = useRef<HTMLDivElement>(null)
  const opener = useRef<HTMLButtonElement | null>(null)
  const focusNew = useRef(false)

  useEffect(() => {
    // A new proposal: focus goes to its Approve, the next step
    if (!focusNew.current) return
    focusNew.current = false
    const cards = listRef.current?.querySelectorAll<HTMLElement>('.proposal-card')
    cards?.[cards.length - 1]?.querySelector<HTMLElement>('.proposal-buttons button')?.focus()
  })

  function keep(next: Made) {
    if (!made.has(owner)) made.set(owner, new Map())
    made.get(owner)?.set(keyId, next)
    setState(next)
  }

  async function propose(change: ProposeBody) {
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      const r = await cardAction(change)
      setForm(null)
      if (r.proposal) {
        focusNew.current = true
        keep({ proposals: [...state.proposals, r.proposal], message: null })
      } else {
        keep({ ...state, message: r.message })
        opener.current?.focus()
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Something went wrong. Try again.')
    } finally {
      setBusy(false)
    }
  }

  function click(b: ChangeButton | 'accepted', el: HTMLButtonElement) {
    opener.current = el
    setError(null)
    if (b === 'watch') void propose({ action: 'propose', change: 'watch', product })
    else setForm(form === b ? null : b) // a "…" button opens its form, and closes it again
  }

  function submitForm(fields: FormFields) {
    if (form === 'set_version') void propose({ action: 'propose', change: 'set_details', product, ...fields })
    else void propose({ action: 'propose', change: 'set_status', cve_id: cve, ...fields })
  }

  const what = cve ?? product
  return (
    <div className="card-actions">
      <div className="card-action-row">
        {buttons.map((b) => (
          <button
            key={b}
            type="button"
            aria-label={`${LABEL[b]} ${b === 'watch' || b === 'set_version' ? product : what}`}
            aria-expanded={b === 'watch' ? undefined : form === b}
            disabled={busy}
            aria-busy={(busy && b === 'watch') || undefined}
            onClick={(e) => click(b, e.currentTarget)}
          >
            {LABEL[b]}
          </button>
        ))}
      </div>
      {form && (
        <ProposeForm
          key={form}
          kind={form}
          product={product}
          asOf={asOf ?? today()}
          busy={busy}
          onSubmit={submitForm}
          onBack={() => {
            setForm(null)
            setError(null)
            opener.current?.focus()
          }}
        />
      )}
      {error && (
        <p className="proposal-line error" role="alert">
          {error}
        </p>
      )}
      <output className="card-action-note">{state.message}</output>
      <div ref={listRef}>
        {state.proposals.map((p) => (
          <ProposalCard key={p.proposal_id} proposal={p} />
        ))}
      </div>
    </div>
  )
}

/** "Ask about this" on a fix-first row: Patch is asked about that CVE, with it in the answer's page context. */
export function AskButton({ cve, page }: { cve: string; page: PageContext }) {
  const { ask, pending } = useContext(CardActionsContext)
  return (
    <button type="button" aria-label={`Ask about this: ${cve}`} disabled={pending} onClick={() => ask(cve, { ...page, cve })}>
      Ask about this
    </button>
  )
}

/** The search card's refine buttons: run the same search again with that filter, at once. */
export function RefineActions({ query, applied, page }: { query: string; applied: RefineFilter[]; page: PageContext }) {
  const { addRefined } = useContext(CardActionsContext)
  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [limit, setLimit] = useState<string | null>(null)
  const buttons = refineButtons(applied)
  if (buttons.length === 0) return null

  async function refine(filters: RefineFilter[], label: string) {
    if (busy) return
    setBusy(label)
    setError(null)
    setLimit(null)
    try {
      const r = await cardAction({ action: 'refine', tool: 'search_security', query, filters, page })
      addRefined({ ...r, filters, page })
    } catch (e) {
      const text = e instanceof Error ? e.message : 'Something went wrong. Try again.'
      // B11: a chat limit (a refine counts as a message) or the spending cap is a quiet line, not an error
      if (e instanceof ApiError && QUIET.has(e.code ?? '')) setLimit(text)
      else setError(text)
    } finally {
      setBusy(null)
    }
  }

  return (
    <div className="card-actions">
      <div className="card-action-row">
        {buttons.map((b) => (
          <button
            key={b.label}
            type="button"
            disabled={busy !== null}
            aria-busy={busy === b.label || undefined}
            onClick={() => void refine(b.filters, b.label)}
          >
            {busy === b.label && <span className="spinner" aria-hidden="true" />}
            {b.label}
          </button>
        ))}
        <span className="meta">Searches again with that filter.</span>
      </div>
      <output className="meta card-action-limit">{limit}</output>
      {error && (
        <p className="proposal-line error" role="alert">
          {error}
        </p>
      )}
    </div>
  )
}

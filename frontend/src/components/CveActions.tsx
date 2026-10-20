import { useState } from 'react'
import type { CveRow, DecisionInput } from '../api.ts'
import { DecisionDialog, type DecisionRequest } from './Decision.tsx'
import { statusActions, type StatusAction } from '../cveActions.ts'

// A CVE's actions (A16b, B35): the status changes, each through the decision dialog, and "Ask Patch". The CVEs list
// shows one in each row and the rest under "More" (B36, #86: cveActions.ts `rowActions`); the page for one CVE shows
// all of them (CveActions), with its own dialog.

/** The status actions a CVE offers (A16b; which ones by status: cveActions.ts), each a button that opens the decision
 *  dialog. Undefined `onDecide` (the as-of date not known yet): disabled. */
export function StatusActions({ row, onDecide }: { row: CveRow; onDecide?: (req: DecisionRequest) => void }) {
  return <ActionButtons actions={statusActions(row)} onDecide={onDecide} />
}

export function ActionButtons({ actions, onDecide }: {
  actions: StatusAction[]
  onDecide?: (req: DecisionRequest) => void
}) {
  return actions.map((a) => (
    <button key={a.name} type="button" disabled={!onDecide} aria-label={a.name} onClick={() => onDecide?.(a.request)}>
      {a.label}
    </button>
  ))
}

/** "Mark not affected?": the version check's suggestion on an open CVE it finds not affected. A suggestion only:
 *  the user's click is the decision (A15). */
export function SuggestNotAffected({ row: r, onDecide }: { row: CveRow; onDecide?: (req: DecisionRequest) => void }) {
  if (r.verdict !== 'not_affected' || r.status !== 'open') return null
  return (
    <button
      type="button"
      className="suggest"
      disabled={!onDecide}
      aria-label={`Mark ${r.id} not affected? Suggested by the version check`}
      onClick={() =>
        onDecide?.({
          cve: r.id,
          status: 'not_affected',
          preset: { justification: 'vulnerable_code_not_present', note: r.verdict_reason },
        })
      }
    >
      Mark not affected?
    </button>
  )
}

/** Every action on one CVE, with its own decision dialog: the suggestion, the status actions and "Ask Patch".
 *  `onDecide` saves the decision (errors show in the dialog); `asOf` sets the dialog's default review date. */
export function CveActions({ row, asOf, onDecide, onAsk }: {
  row: CveRow
  asOf: string | null
  onDecide: (cve: string, body: DecisionInput) => Promise<void>
  onAsk: (cve: string) => void
}) {
  const [deciding, setDeciding] = useState<DecisionRequest | null>(null)
  const open = asOf ? setDeciding : undefined
  return (
    <div className="actions cve-actions">
      <SuggestNotAffected row={row} onDecide={open} />
      <StatusActions row={row} onDecide={open} />
      <button type="button" aria-label={`Ask Patch about ${row.id}`} onClick={() => onAsk(row.id)}>
        Ask Patch
      </button>
      {deciding && asOf && (
        <DecisionDialog
          key={`${deciding.cve}-${deciding.status}`}
          request={deciding}
          asOf={asOf}
          onSubmit={(body) => onDecide(deciding.cve, body)}
          onClose={() => setDeciding(null)}
        />
      )}
    </div>
  )
}

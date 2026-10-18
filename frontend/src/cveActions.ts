import type { CveRow, CveStatus, Justification } from './api.ts'

// A CVE's status actions (A16b), kept apart from the buttons so `npm test` checks them. The page for one CVE shows
// them all (components/CveActions.tsx); a row of the CVEs list shows the first and keeps the rest under "More"
// (B36, #86), so a row stays short enough to see a dozen at once.

/** What the decision dialog (components/Decision.tsx) opens with. */
export interface DecisionRequest {
  cve: string
  status: CveStatus
  again?: boolean // re-accepting: a new review date for an accepted CVE
  preset?: { justification: Justification; note: string }
}

export interface StatusAction {
  label: string // the button's word
  name: string // its accessible name: the word and the CVE id
  request: DecisionRequest // what the decision dialog opens with
}

/** The status actions a CVE offers, the likeliest first (A16b). Open: fixed, not affected (unless the verdict
 *  suggests it: then "Mark not affected?" stands in for it), accept. Accepted with its review due: accept again,
 *  fixed, not affected, reopen. Accepted: fixed, reopen. Fixed or not affected: reopen. */
export function statusActions(r: CveRow): StatusAction[] {
  const action = (label: string, name: string, req: Omit<DecisionRequest, 'cve'>): StatusAction =>
    ({ label, name, request: { cve: r.id, ...req } })
  const fixed = action('Mark fixed', `Mark ${r.id} fixed`, { status: 'fixed' })
  const notAffected = action('Not affected', `Mark ${r.id} not affected`, { status: 'not_affected' })
  const reopen = action('Reopen', `Reopen ${r.id}`, { status: 'open' })
  if (r.status === 'open') {
    const accept = action('Accept risk', `Accept the risk of ${r.id}`, { status: 'accepted' })
    return r.verdict === 'not_affected' ? [fixed, accept] : [fixed, notAffected, accept]
  }
  if (r.status === 'accepted') {
    if (!r.review_due) return [fixed, reopen]
    const again = action('Accept again', `Accept the risk of ${r.id} again`, { status: 'accepted', again: true })
    return [again, fixed, notAffected, reopen]
  }
  return [reopen]
}

/** A row's one main action, and the rest for its "More" (B36). The main one is the likeliest: Mark fixed on an open
 *  or accepted CVE, Accept again when the review is due (the "Review due" chip asks for it), Reopen once closed. */
export function rowActions(r: CveRow): { main: StatusAction; more: StatusAction[] } {
  const [main, ...more] = statusActions(r)
  return { main, more }
}

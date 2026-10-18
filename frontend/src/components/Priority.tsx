import type { PriorityLevel } from '../api.ts'
import { NoFixMark } from './Decision.tsx'
import { WarningIcon } from './Icons.tsx'

// Priority by rules (A16): the level, its reasons and your due date, shown the same way on the CVEs page, the
// dashboard's Top 5 and Patch's cards. Rules decide; nothing here re-orders anything. Never colour alone: the chip
// carries the word, and "Overdue" is written out next to its icon.

export const PRIORITY_LABEL: Record<PriorityLevel, string> = {
  urgent: 'Urgent',
  high: 'High',
  normal: 'Normal',
  low: 'Low',
}

/** A closed CVE (fixed, not affected, accepted before its review: B33) has no priority and no due date: a muted dash,
 *  with the reason for screen readers and on hover. The backend decides "closed" (app.status.is_closed); null is how
 *  it says so. */
function Closed({ what }: { what: string }) {
  return (
    <span className="no-priority" title={`Closed: no ${what}. Priority and due dates are for open CVEs.`}>
      <span aria-hidden="true">—</span>
      <span className="visually-hidden">No {what}: closed</span>
    </span>
  )
}

export function PriorityChip({ level }: { level: PriorityLevel | null }) {
  if (level === null) return <Closed what="priority" />
  return <span className={`chip priority ${level}`}>{PRIORITY_LABEL[level]}</span>
}

/** The reasons, joined the way the spec writes them: "in KEV · EPSS 99th percentile · internet-facing". */
export function PriorityReasons({ reasons }: { reasons: string[] }) {
  return <span className="priority-reasons">{reasons.join(' · ')}</span>
}

export function OverdueMark() {
  return (
    <span className="overdue">
      <WarningIcon />
      Overdue
    </span>
  )
}

/** Your due date (with where it came from), the overdue mark, and CISA's KEV deadline as a separate fact. An open
 *  CVE with no fix yet (A16b) shows "No fix yet · open N days" instead, and its due date is the "decide by" date:
 *  accept, mitigate or replace. */
export function DueFacts({ due, from, overdue, kevDeadline, noFix = null }: {
  due: string | null // null: a closed CVE (B33), no due date; CISA's KEV deadline still shows
  from: string | null
  overdue: boolean
  kevDeadline: string | null
  noFix?: { days: number } | null
}) {
  if (due === null)
    return (
      <>
        <Closed what="due date" />
        <KevDeadline date={kevDeadline} />
      </>
    )
  return (
    <>
      {noFix && <span className="due-label">Decide by</span>}
      <span className="due-date num" title={`Your due date, from your policy: ${from}`}>
        {due}
      </span>
      {overdue && <OverdueMark />}
      {noFix && <NoFixMark days={noFix.days} />}
      <span className="due-from">
        {noFix ? 'accept, mitigate or replace · ' : ''}by your policy: {from}
      </span>
      <KevDeadline date={kevDeadline} />
    </>
  )
}

function KevDeadline({ date }: { date: string | null }) {
  if (!date) return null
  return (
    <span className="kev-deadline" title="CISA's remediation date for US federal agencies: a fact, not your due date">
      CISA KEV deadline <span className="nowrap">{date}</span>
    </span>
  )
}

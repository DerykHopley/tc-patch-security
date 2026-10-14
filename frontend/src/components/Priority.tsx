import type { PriorityLevel } from '../api.ts'
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

export function PriorityChip({ level }: { level: PriorityLevel }) {
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

/** Your due date (with where it came from), the overdue mark, and CISA's KEV deadline as a separate fact. */
export function DueFacts({ due, from, overdue, kevDeadline }: {
  due: string
  from: string
  overdue: boolean
  kevDeadline: string | null
}) {
  return (
    <>
      <span className="due-date num" title={`Your due date, from your policy: ${from}`}>
        {due}
      </span>
      {overdue && <OverdueMark />}
      <span className="due-from">by your policy: {from}</span>
      {kevDeadline && (
        <span className="kev-deadline" title="CISA's remediation date for US federal agencies: a fact, not your due date">
          CISA KEV deadline <span className="nowrap">{kevDeadline}</span>
        </span>
      )}
    </>
  )
}

// The due facts (A16, components/Priority.tsx DueFacts), kept apart so `npm test` checks them.

/** CISA's KEV deadline as its own line under your due date, or null when there is nothing to add: not in KEV, or the
 *  same date as your due date (your policy adopted the KEV deadline, and "by your policy: KEV deadline" says so).
 *  Showing it twice made every KEV row two lines taller (B36, #86). */
export function kevDeadlineLine(due: string, kevDeadline: string | null): string | null {
  return kevDeadline && kevDeadline !== due ? kevDeadline : null
}

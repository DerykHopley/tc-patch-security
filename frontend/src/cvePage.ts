import type { AffectedPackage, CveRow } from './api.ts'

// The words on the page for one CVE (B35, pages/CvePage.tsx), kept apart so `npm test` checks them.

/** One OSV range in words. `introduced` "0" means from the first version. */
export function rangeWords({ introduced, fixed, last_affected }: AffectedPackage['ranges'][number]): string {
  const from = introduced && introduced !== '0' ? introduced : null
  if (fixed) return from ? `from ${from}, before ${fixed}` : `every version before ${fixed}`
  if (last_affected) return `${from ? `from ${from}` : 'every version'} up to ${last_affected} (no fix listed)`
  return from ? `from ${from} on (no fix listed)` : 'every version (no fix listed)'
}

/** Priority and due date belong to open CVEs (GLOSSARY.md). The backend's one rule (B33, `app.status.is_closed`)
 *  decides: a closed CVE (fixed, not affected, accepted before its review) comes with no priority. */
export function showsPriority(row: CveRow): boolean {
  return row.priority !== null
}

/** B40: opening the page is seeing the CVE, so it leaves "New". Only a CVE that is new for you is marked: one write
 *  when it matters, not one per page view (each is a state write, in Cloud Storage when deployed). */
export function marksSeen(detail: { row: CveRow | null }): boolean {
  return detail.row?.new === true
}

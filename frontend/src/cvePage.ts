import type { AffectedPackage, CveRow } from './api.ts'

// The words on the page for one CVE (B35, pages/CvePage.tsx), kept apart so `npm test` checks them.

/** One OSV range in words. `introduced` "0" means from the first version. */
export function rangeWords({ introduced, fixed, last_affected }: AffectedPackage['ranges'][number]): string {
  const from = introduced && introduced !== '0' ? introduced : null
  if (fixed) return from ? `from ${from}, before ${fixed}` : `every version before ${fixed}`
  if (last_affected) return `${from ? `from ${from}` : 'every version'} up to ${last_affected} (no fix listed)`
  return from ? `from ${from} on (no fix listed)` : 'every version (no fix listed)'
}

/** Priority and due date belong to open CVEs (GLOSSARY.md): open, or accepted with its review due.
 *  Seam for B33 (#83): when its shared "is closed" rule lands, call it here. */
export function showsPriority(row: CveRow): boolean {
  return row.open
}

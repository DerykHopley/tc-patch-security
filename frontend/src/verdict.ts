import type { Verdict } from './api.ts'
import type { PackageFix } from './toolResults.ts'

// The version check's verdicts and their words (A15). Plain TypeScript, so the page context can use them under
// node --test; components/Verdict.tsx re-exports them next to the chip.
export const VERDICTS: Verdict[] = ['affected', 'not_affected', 'unknown']
export const VERDICT_LABEL: Record<Verdict, string> = {
  affected: 'Affected',
  not_affected: 'Not affected',
  unknown: 'Unknown',
}

/** "Fixed in …" under the verdict (B67, #109). One package (no list): the fix, as before. More than one: each
 *  package with its fix, in OSV's order, the same whatever your version; a package OSV gives no fix for is named. */
export function fixedIn(fixed: string | null, fixes: PackageFix[]): string | null {
  if (fixes.length === 0) return fixed ? `Fixed in ${fixed}` : null
  const withFix = fixes.filter((f) => f.fixed_version).map((f) => `${f.package} ${f.fixed_version}`)
  const without = fixes.filter((f) => !f.fixed_version).map((f) => f.package)
  if (withFix.length === 0) return `No fix listed for ${without.join(', ')}`
  return `Fixed in ${withFix.join(', ')}` + (without.length ? `; ${without.join(', ')}: no fix listed` : '')
}

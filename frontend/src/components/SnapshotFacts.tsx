import type { Epss } from '../api.ts'
import { Tip } from './Tip.tsx'

// Facts frozen into the snapshot (A14), shown the same way on the dashboard and in Patch's tool cards.

export const EPSS_URL = 'https://www.first.org/epss'
// B44 L7: what "matched on text" means, in words a reader can check: not NVD's product id (CPE), not OSV's packages.
export const POSSIBLE_MATCH_TITLE =
  "Possible match: Patch matched the product on the description's text, not on NVD's product id (CPE), and " +
  "OSV.dev's package data doesn't confirm it. Check before acting."

/** EPSS score as a percentage: "13.7%", or "<0.1%" for the long tail. */
export function epssScore(e: Epss): string {
  return e.score < 0.001 ? '<0.1%' : `${(e.score * 100).toFixed(1)}%`
}

/** EPSS percentile as an ordinal: 0.96438 -> "96th percentile". */
export function epssPercentile(e: Epss): string {
  const n = Math.floor(e.percentile * 100)
  const suffix = n % 100 >= 11 && n % 100 <= 13 ? 'th' : (['th', 'st', 'nd', 'rd'][n % 10] ?? 'th')
  return `${n}${suffix} percentile`
}

/** A small "Possible match" chip; its tooltip (mouse, keyboard, touch: B44) says why. Never colour alone: it carries
 *  the words. */
export function PossibleMatch() {
  return (
    <Tip text={POSSIBLE_MATCH_TITLE} className="chip possible" plain>
      Possible match
    </Tip>
  )
}

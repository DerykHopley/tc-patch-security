import type { Epss } from '../api.ts'

// Facts frozen into the snapshot (A14), shown the same way on the dashboard and in Patch's tool cards.

export const EPSS_URL = 'https://www.first.org/epss'
export const POSSIBLE_MATCH_TITLE =
  'Product guessed from the description; OSV package data does not confirm it. Check before acting.'

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

/** A small "Possible match" chip; the title says why. Never colour alone: it carries the words. */
export function PossibleMatch() {
  return (
    <span className="chip possible" title={POSSIBLE_MATCH_TITLE}>
      Possible match
    </span>
  )
}

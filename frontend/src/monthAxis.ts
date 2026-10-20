// The CVEs-per-month chart's axis labels (B49, from B43's review; #96): the year where each one starts ("2026" at its
// January, from that column's middle rightwards) and the latest month at the end ("2026-10", ending at its column's
// middle). On a phone a month is about 6px wide, so the last January's year ran into the latest month's label. The
// latest month always stays (it says the year too); a year label that would come within 6px of the label after it
// is left out. Kept apart from charts.tsx, so `npm test` checks it.

export interface AxisLabel {
  i: number // the month's index
  text: string
  x: number // the column's middle: where the label starts (start) or ends (end)
  anchor: 'start' | 'end'
}

const CHAR = 6.6 // px per character of an 11px axis label (digits and the hyphen), a little over the real width
const CLEAR = 6 // px kept between two labels

const width = (l: AxisLabel) => l.text.length * CHAR
const startOf = (l: AxisLabel) => (l.anchor === 'end' ? l.x - width(l) : l.x)
const endOf = (l: AxisLabel) => (l.anchor === 'end' ? l.x : l.x + width(l))

/** `left`: the plot's left edge; `slot`: one month's width. */
export function monthAxis(months: string[], { left, slot }: { left: number; slot: number }): AxisLabel[] {
  const last = months.length - 1
  const centre = (i: number) => left + i * slot + slot / 2
  const labels: AxisLabel[] = []
  months.forEach((m, i) => {
    if (i === last) labels.push({ i, text: m, x: centre(i), anchor: 'end' })
    else if (m.endsWith('-01')) labels.push({ i, text: m.slice(0, 4), x: centre(i), anchor: 'start' })
  })
  // From the right: the latest month first, then each year that keeps clear of the label kept after it
  const kept: AxisLabel[] = []
  for (const l of labels.toReversed()) {
    if (kept.length === 0 || endOf(l) + CLEAR <= startOf(kept[0])) kept.unshift(l)
  }
  return kept
}

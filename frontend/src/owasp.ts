// The dashboard's OWASP chart (B43, #93, #25): the axis shows the code only ("A05"), so no label is cut off, even on
// a phone; the tooltip (and the bar's accessible name) gives the category in full. The table view keeps the titles.

/** One bar of the chart, from the dashboard's `by_owasp` row (`title` is OWASP's "A05:2025 Injection"). */
export function owaspBar(o: { code: string; title: string; count: number }): { label: string; tip: string; count: number } {
  const name = o.title.replace(/^[^ ]*:2025\s*/, '')
  return { label: o.code, tip: `${o.code} ${name}: ${o.count} open CVE${o.count === 1 ? '' : 's'}`, count: o.count }
}

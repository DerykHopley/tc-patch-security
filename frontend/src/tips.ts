// Tooltips by mouse, keyboard and touch (B44, #94; DESIGN.md §5.18): the bubble's place and the CVE list's tip texts,
// kept apart from components/Tip.tsx so `npm test` checks them.

export interface Box {
  left: number
  top: number
  right: number
  bottom: number
}

const GAP = 8 // between the anchor and the bubble
const MARGIN = 8 // the bubble never comes closer to the window's edge

/** Where a tip's bubble goes (fixed position, px): centred above its anchor, below it when there's no room above (a
 *  column heading at the top of the window), and never off the screen sideways (a phone's edge cells). */
export function placeTip(
  anchor: Box,
  tip: { width: number; height: number },
  view: { width: number; height: number },
): { left: number; top: number; below: boolean } {
  const centre = (anchor.left + anchor.right) / 2
  const left = Math.max(MARGIN, Math.min(centre - tip.width / 2, view.width - MARGIN - tip.width))
  const above = anchor.top - GAP - tip.height
  if (above >= MARGIN) return { left, top: above, below: false }
  return { left, top: anchor.bottom + GAP, below: true }
}

/** The CVE list's column headings that need explaining (B44 L6); the others (CVE, Product, Severity, Published,
 *  Status) say what they are, so they get no tip and no underline. */
export const HEADER_TIPS = {
  priority: 'Set by fixed rules from CISA KEV, EPSS, severity, the verdict and internet-facing.',
  due: 'Your due date, from your policy (Settings → Priority and due dates).',
  owasp: 'The OWASP Top 10 category of the weakness (its CWE). Point at, focus or tap a code for its name and list.',
  epss: 'Exploit Prediction Scoring System: the chance of exploitation in the next 30 days, and its percentile.',
  verdict: "The version check's advice from your usage and version. Your status stays your decision.",
}

/** The OWASP cell's tip: the category's full name and the list it's from, since "A05" alone says neither (B44 L5). */
export function owaspTip(title: string | null, list: string | null): string | null {
  if (!title) return null
  return list ? `${title}, from the ${list}` : title
}

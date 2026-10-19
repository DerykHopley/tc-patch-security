// The embedding map's group labels (DESIGN.md §5.5): one per group, near its centre, never on top of another label
// and never cut by the map's edge. B50 (#95): with a real embedder (ollama/mxbai-embed-large) the OWASP and ATLAS
// centres sit about 35px apart at phone width, and the old nudge only compared each label with the one placed just
// before it, so a third label in between let two of them overlap.

export interface MapLabel {
  id: string
  text: string
  x: number // the label's centre (text-anchor: middle)
  y: number // its baseline
}

/** The label font: 12px bold (dev.css .emap-label). A generous average width per character, so the box is never
 *  smaller than the text; measured text would need a render first. */
export const CHAR_PX = 7.5
export const LINE_PX = 16 // a label's box height: 12px text with its 4px halo
const EDGE = 4 // room kept to the map's edge

const halfWidth = (l: MapLabel) => (l.text.length * CHAR_PX) / 2 + 2 // + the halo

function overlaps(a: MapLabel, b: MapLabel): boolean {
  return Math.abs(a.x - b.x) < halfWidth(a) + halfWidth(b) && Math.abs(a.y - b.y) < LINE_PX
}

/** Places the labels: each inside the map, then moved up or down by whole lines, nearest first, until it overlaps no
 *  label placed before it. The topmost centre is placed first. */
export function placeLabels(labels: MapLabel[], width: number, height: number): MapLabel[] {
  const top = LINE_PX // a baseline this low keeps the text inside the top edge
  const bottom = height - EDGE
  const clampY = (y: number) => Math.max(top, Math.min(bottom, y))
  const placed: MapLabel[] = []
  for (const l of labels.toSorted((a, b) => a.y - b.y)) {
    const half = halfWidth(l)
    const x = Math.max(half + EDGE, Math.min(width - half - EDGE, l.x))
    const y0 = clampY(l.y)
    let spot = { ...l, x, y: y0 }
    // 0, +1, -1, +2, -2 … lines: the nearest free place, inside the map
    for (let step = 1; placed.some((p) => overlaps(spot, p)) && step < 2 * (height / LINE_PX); step++) {
      const shift = Math.ceil(step / 2) * LINE_PX * (step % 2 ? 1 : -1)
      const y = y0 + shift
      if (y < top || y > bottom) continue
      spot = { ...l, x, y }
    }
    placed.push(spot)
  }
  return labels.map((l) => placed.find((p) => p.id === l.id)!)
}

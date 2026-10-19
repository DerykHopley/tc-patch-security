import assert from 'node:assert/strict'
import { test } from 'node:test'
import { CHAR_PX, LINE_PX, placeLabels, type MapLabel } from './mapLabels.ts'

const label = (id: string, text: string, x: number, y: number): MapLabel => ({ id, text, x, y })

const half = (l: MapLabel) => (l.text.length * CHAR_PX) / 2

function apart(a: MapLabel, b: MapLabel): boolean {
  return Math.abs(a.x - b.x) >= half(a) + half(b) || Math.abs(a.y - b.y) >= LINE_PX
}

function inside(l: MapLabel, width: number, height: number): boolean {
  return l.x - half(l) >= 0 && l.x + half(l) <= width && l.y - 12 >= 0 && l.y <= height
}

// The three group centres of the real index the owner uses (ollama/mxbai-embed-large, 1,680 chunks, PCA), on a map
// 310px wide (a 390px phone) and 300px high, measured 2026-10-19. The old nudge left OWASP and ATLAS on top of each
// other here: it compared ATLAS only with CVEs, placed between them.
const PHONE = [label('owasp', 'OWASP pages', 115, 94), label('atlas', 'MITRE ATLAS', 80, 110),
  label('cve', 'CVEs', 242, 104)]

test('B50.6 the real embedder\'s labels on a phone: none on another, all inside the map', () => {
  const out = placeLabels(PHONE, 310, 300)
  assert.deepEqual(out.map((l) => l.id), ['owasp', 'atlas', 'cve']) // the order given
  for (const [i, a] of out.entries()) {
    assert.ok(inside(a, 310, 300), a.id)
    for (const b of out.slice(i + 1)) assert.ok(apart(a, b), `${a.id} and ${b.id}`)
  }
  const atlas = out[1]
  assert.ok(Math.abs(atlas.y - 110) <= LINE_PX, 'moved by one line at most') // still near its group
})

test('B50.6 labels already apart stay where they are (1440px, the same index)', () => {
  const wide = [label('owasp', 'OWASP pages', 425, 153), label('atlas', 'MITRE ATLAS', 276, 179),
    label('cve', 'CVEs', 952, 169)]
  assert.deepEqual(placeLabels(wide, 1180, 480), wide)
})

test('B50.6 three labels on one spot: each a line apart', () => {
  const out = placeLabels([label('a', 'OWASP pages', 150, 150), label('b', 'MITRE ATLAS', 150, 150),
    label('c', 'CVEs', 150, 150)], 300, 300)
  const ys = out.map((l) => l.y).toSorted((p, q) => p - q)
  assert.deepEqual(ys, [134, 150, 166])
})

test('B50.6 a label at the edge moves inside the map', () => {
  const [l] = placeLabels([label('a', 'OWASP pages', 5, 2)], 300, 300)
  assert.ok(inside(l, 300, 300))
  const [r] = placeLabels([label('a', 'MITRE ATLAS', 299, 299)], 300, 300)
  assert.ok(inside(r, 300, 300))
})

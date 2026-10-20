// The CVEs-per-month chart's axis labels (B49, from B43; #96): the years and the latest month, never on top of each
// other, even on a phone. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { monthAxis } from './monthAxis.ts'

const months = (from: number, to: number) => {
  const out: string[] = []
  for (let y = 2024, m = 1; y * 12 + m <= to; m === 12 ? ((y += 1), (m = 1)) : (m += 1)) {
    if (y * 12 + m >= from) out.push(`${y}-${String(m).padStart(2, '0')}`)
  }
  return out
}
const JAN_2024 = 2024 * 12 + 1
const OCT_2026 = 2026 * 12 + 10
const texts = (labels: { text: string }[]) => labels.map((l) => l.text)

test('B49.7 wide: each year where it starts, and the latest month at the end', () => {
  const labels = monthAxis(months(JAN_2024, OCT_2026), { left: 32, slot: 30 })
  assert.deepEqual(texts(labels), ['2024', '2025', '2026', '2026-10'])
  assert.deepEqual(labels.at(-1), { i: 33, text: '2026-10', x: 32 + 33 * 30 + 15, anchor: 'end' })
  assert.deepEqual(labels[0], { i: 0, text: '2024', x: 32 + 15, anchor: 'start' })
})

test('B49.7 a phone (about 6px a month): the year that would touch the latest month is left out', () => {
  // At 390px "2026" (from Jan) and "2026-10" (ending at Oct) overlapped: 9 slots of 6px are 54px for 26 + 46px of text
  const labels = monthAxis(months(JAN_2024, OCT_2026), { left: 32, slot: 6.2 })
  assert.deepEqual(texts(labels), ['2024', '2025', '2026-10'])
  for (let k = 1; k < labels.length; k++) {
    const prevEnd = labels[k - 1].x + labels[k - 1].text.length * 6.6
    const start = labels[k].anchor === 'end' ? labels[k].x - labels[k].text.length * 6.6 : labels[k].x
    assert.ok(prevEnd + 6 <= start, `${labels[k - 1].text} touches ${labels[k].text}`)
  }
})

test('B49.7 the latest month is a January: one label, the month itself', () => {
  assert.deepEqual(texts(monthAxis(months(JAN_2024, 2025 * 12 + 1), { left: 0, slot: 30 })), ['2024', '2025-01'])
})

test('B49.7 no months, no labels', () => {
  assert.deepEqual(monthAxis([], { left: 0, slot: 10 }), [])
})

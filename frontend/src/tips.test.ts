// Tooltips by mouse, keyboard and touch (B44, #94): where the bubble goes, and what the CVE list's tips say.
// Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { owaspTip, placeTip } from './tips.ts'

const VIEW = { width: 390, height: 844 }

test('B44.2 a tip sits centred above its anchor, 8px clear', () => {
  const anchor = { left: 150, top: 300, right: 190, bottom: 320 } // 40px wide, centre x 170
  assert.deepEqual(placeTip(anchor, { width: 100, height: 30 }, VIEW), { left: 120, top: 262, below: false })
})

test('B44.2 a tip with no room above goes below its anchor', () => {
  const header = { left: 150, top: 20, right: 190, bottom: 40 }
  assert.deepEqual(placeTip(header, { width: 100, height: 30 }, VIEW), { left: 120, top: 48, below: true })
})

test('B44.2 a tip never leaves the screen sideways: 8px from either edge', () => {
  const nearLeft = { left: 2, top: 300, right: 22, bottom: 320 }
  assert.equal(placeTip(nearLeft, { width: 200, height: 30 }, VIEW).left, 8)
  const nearRight = { left: 370, top: 300, right: 388, bottom: 320 }
  assert.equal(placeTip(nearRight, { width: 200, height: 30 }, VIEW).left, 390 - 8 - 200)
})

test('B44.3 the OWASP tip names the category and its list', () => {
  assert.equal(
    owaspTip('A05:2025 Injection', 'OWASP Top 10 2025 (web applications)'),
    'A05:2025 Injection, from the OWASP Top 10 2025 (web applications)',
  )
  assert.equal(
    owaspTip('LLM01:2025 Prompt Injection', 'OWASP Top 10 for LLM Applications 2025'),
    'LLM01:2025 Prompt Injection, from the OWASP Top 10 for LLM Applications 2025',
  )
  assert.equal(owaspTip('A05:2025 Injection', null), 'A05:2025 Injection') // a list we don't know: the name alone
  assert.equal(owaspTip(null, null), null) // no category: no tip (the cell shows "—")
})

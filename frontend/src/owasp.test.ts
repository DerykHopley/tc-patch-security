// The OWASP chart's words (B43, #93, #25): the code on the axis, the full name in the tooltip. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { owaspBar } from './owasp.ts'

test('B43.4 an OWASP bar shows its code; the tooltip names the category in full', () => {
  assert.deepEqual(owaspBar({ code: 'A05', title: 'A05:2025 Injection', count: 128 }),
    { label: 'A05', tip: 'A05 Injection: 128 open CVEs', count: 128 })
  assert.deepEqual(owaspBar({ code: 'A10', title: 'A10:2025 Mishandling of Exceptional Conditions', count: 1 }),
    { label: 'A10', tip: 'A10 Mishandling of Exceptional Conditions: 1 open CVE', count: 1 })
})

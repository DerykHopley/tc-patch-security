// The due facts (A16), without repeating a date (B36, #86). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { kevDeadlineLine } from './due.ts'

test('B36.4 the KEV deadline gets its own line only when it is not already your due date', () => {
  // your policy adopts the KEV deadline: "by your policy: KEV deadline" under the date says it all
  assert.equal(kevDeadlineLine('2025-05-26', '2025-05-26'), null)
  // another due date: CISA's date is a separate fact
  assert.equal(kevDeadlineLine('2025-04-21', '2025-05-26'), '2025-05-26')
  assert.equal(kevDeadlineLine('2025-07-06', null), null) // not in KEV
})

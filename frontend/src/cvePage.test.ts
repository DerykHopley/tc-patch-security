// The words on the page for one CVE (B35, #85). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CveRow } from './api.ts'
import { marksSeen, rangeWords, showsPriority } from './cvePage.ts'

const range = (introduced: string | null, fixed: string | null, last_affected: string | null = null) =>
  ({ introduced, fixed, last_affected })

test('B35.7 an OSV range in words: which versions are affected', () => {
  assert.equal(rangeWords(range('0', '1.3.0')), 'every version before 1.3.0')
  assert.equal(rangeWords(range('1.0.0', '1.3.0')), 'from 1.0.0, before 1.3.0')
  assert.equal(rangeWords(range('0', null, '0.12.5')), 'every version up to 0.12.5 (no fix listed)')
  assert.equal(rangeWords(range('0.4.0', null, '0.12.5')), 'from 0.4.0 up to 0.12.5 (no fix listed)')
  assert.equal(rangeWords(range('0.4.0', null)), 'from 0.4.0 on (no fix listed)')
  assert.equal(rangeWords(range('0', null)), 'every version (no fix listed)')
  assert.equal(rangeWords(range(null, '2.0')), 'every version before 2.0')
})

// As the backend sends them (B33): a closed CVE comes with no priority
const row = (status: CveRow['status'], open: boolean) =>
  ({ status, open, priority: open ? 'urgent' : null }) as CveRow

test('B35.8 B33 priority and due date show for open CVEs only: the backend\'s closed rule decides', () => {
  assert.equal(showsPriority(row('open', true)), true)
  assert.equal(showsPriority(row('accepted', true)), true) // its review is due: open again
  assert.equal(showsPriority(row('accepted', false)), false)
  assert.equal(showsPriority(row('fixed', false)), false)
  assert.equal(showsPriority(row('not_affected', false)), false)
})

const shown = (r: Partial<CveRow> | null) => ({ row: r as CveRow | null })

test('B40.6 opening a CVE page marks it seen only when it is new for you: no write on every page view', () => {
  assert.equal(marksSeen(shown({ new: true })), true)
  assert.equal(marksSeen(shown({ new: false })), false)
  assert.equal(marksSeen(shown(null)), false) // off the watchlist: never in the New list
})

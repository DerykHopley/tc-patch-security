// The words on the page for one CVE (B35, #85). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CveRow } from './api.ts'
import { rangeWords, showsPriority } from './cvePage.ts'

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

const row = (status: CveRow['status'], open: boolean) => ({ status, open }) as CveRow

test('B35.8 priority and due date show for open CVEs only (GLOSSARY.md; the shared rule comes with B33, #83)', () => {
  assert.equal(showsPriority(row('open', true)), true)
  assert.equal(showsPriority(row('accepted', true)), true) // its review is due: open again
  assert.equal(showsPriority(row('accepted', false)), false)
  assert.equal(showsPriority(row('fixed', false)), false)
  assert.equal(showsPriority(row('not_affected', false)), false)
})

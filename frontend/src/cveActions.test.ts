// A CVE's status actions, and which one a row of the CVEs list shows (B36, #86). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { CveRow } from './api.ts'
import { rowActions, statusActions } from './cveActions.ts'

const row = (status: CveRow['status'], more: Partial<CveRow> = {}) =>
  ({ id: 'CVE-2025-3248', status, verdict: 'unknown', review_due: false, ...more }) as CveRow
const names = (actions: { name: string }[]) => actions.map((a) => a.name)

test('B36.1 the status actions by status, in A16b order (the first is the likeliest)', () => {
  assert.deepEqual(names(statusActions(row('open'))), [
    'Mark CVE-2025-3248 fixed', 'Mark CVE-2025-3248 not affected', 'Accept the risk of CVE-2025-3248',
  ])
  // the version check says not affected: its suggestion replaces the plain "Not affected" (A15)
  assert.deepEqual(names(statusActions(row('open', { verdict: 'not_affected' }))), [
    'Mark CVE-2025-3248 fixed', 'Accept the risk of CVE-2025-3248',
  ])
  assert.deepEqual(names(statusActions(row('accepted'))), ['Mark CVE-2025-3248 fixed', 'Reopen CVE-2025-3248'])
  assert.deepEqual(names(statusActions(row('accepted', { review_due: true }))), [
    'Accept the risk of CVE-2025-3248 again', 'Mark CVE-2025-3248 fixed', 'Mark CVE-2025-3248 not affected',
    'Reopen CVE-2025-3248',
  ])
  assert.deepEqual(names(statusActions(row('fixed'))), ['Reopen CVE-2025-3248'])
  assert.deepEqual(names(statusActions(row('not_affected'))), ['Reopen CVE-2025-3248'])
})

test('B36.2 each action names its decision for the dialog', () => {
  const [again] = statusActions(row('accepted', { review_due: true }))
  assert.equal(again.label, 'Accept again')
  assert.deepEqual(again.request, { cve: 'CVE-2025-3248', status: 'accepted', again: true })
  const [fixed] = statusActions(row('open'))
  assert.equal(fixed.label, 'Mark fixed')
  assert.deepEqual(fixed.request, { cve: 'CVE-2025-3248', status: 'fixed' })
})

test('B36.3 a row shows one main action; the rest wait under More', () => {
  const open = rowActions(row('open'))
  assert.equal(open.main.label, 'Mark fixed')
  assert.deepEqual(open.more.map((a) => a.label), ['Not affected', 'Accept risk'])
  const due = rowActions(row('accepted', { review_due: true }))
  assert.equal(due.main.label, 'Accept again')
  assert.deepEqual(due.more.map((a) => a.label), ['Mark fixed', 'Not affected', 'Reopen'])
  const fixed = rowActions(row('fixed'))
  assert.equal(fixed.main.label, 'Reopen')
  assert.deepEqual(fixed.more, [])
})

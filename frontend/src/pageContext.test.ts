// The page context's rules (A18, A15b): what Patch is told about the view under the chat. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { chipWords, currentContext, reducePageContext, startPageContext, type PageContextAction } from './pageContext.ts'
import type { Page } from './route.ts'

/** The state after these actions, from the first visit of `page`. */
function after(page: Page, ...actions: PageContextAction[]) {
  return actions.reduce(reducePageContext, startPageContext(page, 0))
}

const langflowHigh = { filters: { status: 'open' as const, product: 'langflow', severity: 'HIGH' as const }, productName: 'Langflow' }

test('a new visit clears the view: the next visit starts without the last one\'s filters', () => {
  const s = after('cves', { type: 'view', visit: 0, view: langflowHigh })
  assert.deepEqual(currentContext(s), { page: 'cves', product: 'langflow', severity: 'HIGH', status: 'open' })
  const next = reducePageContext(s, { type: 'visit', page: 'cves', visit: 1 })
  assert.deepEqual(currentContext(next), { page: 'cves' })
  assert.deepEqual(chipWords(next), [])
})

test('"Ask about this" selects the CVE: Patch is told which CVE "this" is, and the chip names it', () => {
  const s = after('cves', { type: 'view', visit: 0, view: langflowHigh }, { type: 'select', cve: 'CVE-2025-3248', pending: false })
  assert.equal(s.selected, 'CVE-2025-3248')
  assert.deepEqual(currentContext(s), { page: 'cves', product: 'langflow', severity: 'HIGH', status: 'open', cve: 'CVE-2025-3248' })
  assert.deepEqual(chipWords(s), ['Langflow', 'High or worse', 'CVE-2025-3248'])
})

test('a filter change clears the selection: "this" never means a CVE that may have left the view', () => {
  const selected = after('cves', { type: 'view', visit: 0, view: langflowHigh }, { type: 'select', cve: 'CVE-2025-3248', pending: false })
  const critical = { ...langflowHigh, filters: { ...langflowHigh.filters, severity: 'CRITICAL' as const } }
  const s = reducePageContext(selected, { type: 'view', visit: 0, view: critical })
  assert.equal(s.selected, null)
  assert.deepEqual(currentContext(s), { page: 'cves', product: 'langflow', severity: 'CRITICAL', status: 'open' })
})

test('selecting while a reply is pending does nothing: the chat takes no new question, so nothing is asked about', () => {
  const first = after('cves', { type: 'view', visit: 0, view: langflowHigh }, { type: 'select', cve: 'CVE-2025-3248', pending: false })
  const s = reducePageContext(first, { type: 'select', cve: 'CVE-2024-0001', pending: true })
  assert.equal(s, first)
  assert.equal(currentContext(s).cve, 'CVE-2025-3248')
})

test('only the CVEs page has a selected CVE', () => {
  const s = after('dashboard', { type: 'select', cve: 'CVE-2025-3248', pending: false })
  assert.equal(s.selected, null)
  assert.deepEqual(currentContext(s), { page: 'dashboard' })
})

test('a view reported for an earlier visit is ignored: it can\'t bring the last visit\'s filters back', () => {
  const s = after('cves', { type: 'visit', page: 'cves', visit: 1 }, { type: 'view', visit: 0, view: langflowHigh })
  assert.deepEqual(currentContext(s), { page: 'cves' })
})

test('the dashboard sends its product filter, several products in one, and nothing more', () => {
  const view = { filters: { status: 'open' as const, product: 'langflow,ollama' }, productName: 'Langflow + Ollama' }
  const s = after('dashboard', { type: 'view', visit: 0, view })
  assert.deepEqual(currentContext(s), { page: 'dashboard', product: 'langflow,ollama' })
  assert.deepEqual(chipWords(s), ['Langflow + Ollama'])
  const cleared = reducePageContext(s, { type: 'view', visit: 0, view: { filters: { status: 'open' }, productName: '' } })
  assert.deepEqual(currentContext(cleared), { page: 'dashboard' })
  assert.deepEqual(chipWords(cleared), [])
})

test('switching pages: each page starts bare, and coming back to the CVEs page brings neither filters nor selection', () => {
  let s = after('cves', { type: 'view', visit: 0, view: langflowHigh }, { type: 'select', cve: 'CVE-2025-3248', pending: false })
  s = reducePageContext(s, { type: 'visit', page: 'dashboard', visit: 1 })
  assert.deepEqual(currentContext(s), { page: 'dashboard' })
  s = reducePageContext(s, { type: 'view', visit: 1, view: { filters: { status: 'open', product: 'ollama' }, productName: 'Ollama' } })
  s = reducePageContext(s, { type: 'visit', page: 'settings', visit: 2 })
  assert.deepEqual(currentContext(s), { page: 'settings' })
  assert.deepEqual(chipWords(s), [])
  s = reducePageContext(s, { type: 'visit', page: 'cves', visit: 3 })
  assert.deepEqual(currentContext(s), { page: 'cves' })
  assert.equal(s.selected, null)
})

test('the same filters reported again (the product names loaded, a re-render) keep the selection', () => {
  const early = { ...langflowHigh, productName: 'langflow' } // before the product list arrives
  const selected = after('cves', { type: 'view', visit: 0, view: early }, { type: 'select', cve: 'CVE-2025-3248', pending: false })
  const s = reducePageContext(selected, { type: 'view', visit: 0, view: langflowHigh })
  assert.equal(s.selected, 'CVE-2025-3248')
  assert.deepEqual(chipWords(s), ['Langflow', 'High or worse', 'CVE-2025-3248'])
})

test('B35.6 on one CVE\'s page Patch is told that CVE, and only that: the list\'s filters don\'t apply there', () => {
  let s = after('cves', { type: 'view', visit: 0, view: langflowHigh })
  s = reducePageContext(s, { type: 'visit', page: 'cves', visit: 1, cve: 'CVE-2025-3248' })
  assert.deepEqual(currentContext(s), { page: 'cves', cve: 'CVE-2025-3248' })
  assert.deepEqual(chipWords(s), ['CVE-2025-3248'])
  // "Ask Patch" on the page asks about the same CVE: it stays the one Patch is told
  s = reducePageContext(s, { type: 'select', cve: 'CVE-2025-3248', pending: false })
  assert.deepEqual(currentContext(s), { page: 'cves', cve: 'CVE-2025-3248' })
  // Back to the list: no CVE, as on any new visit
  s = reducePageContext(s, { type: 'visit', page: 'cves', visit: 2 })
  assert.deepEqual(currentContext(s), { page: 'cves' })
})

test('B49.6 on "Page not found" Patch is told no page: it is no page of the app', () => {
  assert.deepEqual(currentContext(after('notFound')), {})
  assert.deepEqual(chipWords(after('notFound')), [])
})

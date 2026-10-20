// Tool calls on the chat's cards: which ones propose a change, and which links may be followed. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { ToolCallRecord } from './api.ts'
import { httpHref, proposalAfter, proposalOf } from './toolCalls.ts'
import type { ProposalFields } from './toolResults.ts'

const call = (name: string, result: unknown) => ({ id: 'c', name, args: {}, result }) as unknown as ToolCallRecord

test('BR.2 a link is followed only when it is http or https', () => {
  assert.equal(httpHref('https://nvd.nist.gov/vuln/detail/CVE-2025-3248'), 'https://nvd.nist.gov/vuln/detail/CVE-2025-3248')
  assert.equal(httpHref('http://example.org/a'), 'http://example.org/a')
  assert.equal(httpHref('HTTPS://Example.org/'), 'HTTPS://Example.org/')
  for (const bad of ['javascript:alert(1)', ' JavaScript:alert(1)', 'data:text/html,x', 'ftp://example.org/', '//example.org/a',
    '/cves', 'example.org', '', null, undefined]) {
    assert.equal(httpHref(bad), null, String(bad))
  }
})

test('BR.6 a tool call proposes a change when its result is a proposal, whatever the tool', () => {
  const proposal = { proposal_id: 'p1', title: 'Mark CVE-2024-8309 fixed' }
  assert.equal(proposalOf(call('update_watchlist', proposal))?.proposal_id, 'p1')
  assert.equal(proposalOf(call('propose_decision', proposal))?.proposal_id, 'p1')
  assert.equal(proposalOf(call('update_watchlist', { message: 'already so', watchlist: [] })), null) // nothing to change
  assert.equal(proposalOf(call('propose_decision', null)), null) // a failed step
  assert.equal(proposalOf(call('lookup_cve', { id: 'CVE-2024-8309' })), null)
})

const NO_FIELDS: ProposalFields = {
  status: null, justification: null, note: null, reason: null, review_date: null, compensating_control: null,
  usage: null, version: null, internet_facing: null,
}
const status = (fields: Partial<ProposalFields>, after = 'from the backend') =>
  proposalAfter({ action: 'set_status', after, fields: { ...NO_FIELDS, ...fields } })

test('B49.3 an accepted risk reads "Accepted, review <date>", the reason on its own line', () => {
  assert.deepEqual(status({ status: 'accepted', reason: 'No fix yet; we filter inputs', review_date: '2026-11-17' }), {
    after: 'Accepted, review 2026-11-17', lines: ['No fix yet; we filter inputs'],
  })
})

test('B49.3 a compensating control gets its own line after the reason', () => {
  assert.deepEqual(status({ status: 'accepted', reason: 'Internal only', review_date: '2026-11-17',
    compensating_control: 'WAF rule 12' }), {
    after: 'Accepted, review 2026-11-17', lines: ['Internal only', 'Control: WAF rule 12'],
  })
})

test('B49.3 not affected names its justification in the after value; the note on its own line', () => {
  assert.deepEqual(status({ status: 'not_affected', justification: 'vulnerable_code_not_present', note: 'We pin 1.3' }), {
    after: 'Not affected, vulnerable code not present', lines: ['We pin 1.3'],
  })
})

test('B49.3 a plain status is just its word', () => {
  assert.deepEqual(status({ status: 'fixed' }), { after: 'Fixed', lines: [] })
})

test("B49.3 other proposals keep the backend's after value", () => {
  assert.deepEqual(proposalAfter({ action: 'watch', after: 'Watched', fields: NO_FIELDS }), { after: 'Watched', lines: [] })
  const details = 'self-hosted app, version 1.2.0, internet-facing'
  assert.deepEqual(proposalAfter({ action: 'set_details', after: details, fields: NO_FIELDS }), { after: details, lines: [] })
})

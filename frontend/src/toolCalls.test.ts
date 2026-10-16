// Tool calls on the chat's cards: which ones propose a change, and which links may be followed. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { ToolCallRecord } from './api.ts'
import { httpHref, proposalOf } from './toolCalls.ts'

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

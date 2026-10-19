// Who decided, in a CVE's history (B44 D4, #94). Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { whoDecided } from './decisionWho.ts'

test('B44.4 your own decision says "by you", whatever name it was saved under', () => {
  // sign-in off: the one local user is saved as "owner"
  assert.equal(whoDecided({ decided_by: 'owner', via: 'page' }), 'by you, on the CVEs page')
  // sign-in on: the signed-in user's name
  assert.equal(whoDecided({ decided_by: 'Deryk Hopley', via: 'chat' }), 'by you, in the chat')
  assert.equal(whoDecided({ decided_by: 'owner', via: null }), 'by you')
})

test('B44.4 a status saved before decision records says nobody knows who', () => {
  assert.equal(whoDecided({ decided_by: null, via: null }), 'by unknown')
})

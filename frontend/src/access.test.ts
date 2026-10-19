// B38 (#81): the access screens' words and the Requests card's buttons and lines. `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { accessScreen, noteLeft, NOTE_MAX, requestActions, requestLine, type RequestRow } from './access.ts'

const row = (over: Partial<RequestRow>): RequestRow => ({
  user_id: 'user_alice', status: 'waiting', note: null, by: null, at: '2026-10-19T08:00:00+00:00',
  requested_at: '2026-10-19T08:00:00+00:00', migrated: false, name: 'Alice', email: 'alice@example.com', ...over,
})

test('B38.20: each status has its own screen, and only a new account gets the request form', () => {
  assert.equal(accessScreen('none').title, 'Ask to join Patch')
  assert.equal(accessScreen('none').form, true)
  assert.equal(accessScreen('waiting').title, 'Your request is waiting for the owner')
  assert.equal(accessScreen('waiting').form, false)
  assert.equal(accessScreen('refused').title, "Your request wasn't approved")
  assert.equal(accessScreen('refused').form, false)
  assert.match(accessScreen('refused').lead, /Thanks for asking/)
})

test('B38.21: the note counts down from 280 after trimming', () => {
  assert.equal(NOTE_MAX, 280)
  assert.equal(noteLeft(''), 280)
  assert.equal(noteLeft('  hi  '), 278)
  assert.equal(noteLeft('x'.repeat(290)), -10)
})

test('B38.22: the buttons per status: approve or refuse; remove; undo a refusal or approve', () => {
  assert.deepEqual(requestActions('waiting').map((a) => a.label), ['Approve', 'Refuse'])
  assert.deepEqual(requestActions('approved').map((a) => a.label), ['Remove'])
  assert.deepEqual(requestActions('refused').map((a) => a.label), ['Undo refusal', 'Approve'])
  assert.deepEqual(requestActions('refused').map((a) => a.to), ['waiting', 'approved'])
  assert.equal(requestActions('approved')[0].to, 'remove')
})

test('B38.23: the line under each person says when they asked and who decided', () => {
  assert.equal(requestLine(row({}), 'user_owner'), 'Asked 2026-10-19 08:00 UTC')
  assert.equal(requestLine(row({ status: 'approved', by: 'user_owner', at: '2026-10-19T09:30:00+00:00' }),
    'user_owner'), 'Asked 2026-10-19 08:00 UTC · Approved by you 2026-10-19 09:30 UTC')
  assert.equal(requestLine(row({ status: 'refused', by: 'user_other', at: '2026-10-19T09:30:00+00:00' }),
    'user_owner'), 'Asked 2026-10-19 08:00 UTC · Refused by user_other 2026-10-19 09:30 UTC')
  assert.equal(requestLine(row({ status: 'approved', migrated: true, requested_at: null }), 'user_owner'),
    'Approved before sign-up requests (they were invited)')
})

// B38 (#81): the access screens' words and the Requests card's buttons and lines. `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  accessScreen, devView, noteLeft, NOTE_MAX, requestActions, requestLine, requestWho, ROLE_CHOICES, roleDone, roleHint, roleOf,
  seesDev, seesUsage, type RequestRow,
} from './access.ts'

const row = (over: Partial<RequestRow>): RequestRow => ({
  user_id: 'user_alice', status: 'waiting', note: null, by: null, at: '2026-10-19T08:00:00+00:00',
  requested_at: '2026-10-19T08:00:00+00:00', migrated: false, name: 'Alice', email: 'alice@example.com',
  role: 'viewer', ...over,
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

// B45 (#90): roles

test('B45.20: the role choice offers Viewer, Trusted and Reviewer, Viewer first, each with what it allows', () => {
  assert.deepEqual(ROLE_CHOICES.map((c) => c.value), ['viewer', 'trusted', 'reviewer'])
  assert.deepEqual(ROLE_CHOICES.map((c) => c.label), ['Viewer', 'Trusted', 'Reviewer'])
  assert.equal(roleHint('viewer'), 'Dashboard, CVEs, chat and their own watchlist. No Dev page.')
  assert.equal(roleHint('trusted'), 'Also the Dev page, read-only, and the search playground.')
  assert.equal(roleHint('reviewer'), 'Also tries other Dev settings: their changes apply only to them.')
})

test('B45.21: a role change says when it applies', () => {
  assert.equal(roleDone('Alice', 'trusted'), 'Alice is now Trusted: it applies on their next page load.')
  assert.equal(roleDone('Alice', 'viewer'), 'Alice is now a Viewer: it applies on their next page load.')
})

test('B45.22: only Viewers miss the Dev page; with sign-in off the one local user is the owner', () => {
  assert.equal(seesDev('viewer'), false)
  for (const r of ['trusted', 'reviewer', 'owner'] as const) assert.equal(seesDev(r), true)
  assert.equal(roleOf(null), 'owner') // /access not answered yet, sign-in off: the app shows at once, as the owner
  assert.equal(roleOf({ status: 'approved', owner: false, role: 'trusted', sign_in: true, note: null, at: null }),
    'trusted')
})

test('B45.23: the Dev page by role: who changes what, who runs the checks, and the note', () => {
  assert.deepEqual(devView('owner', false), { change: true, runChecks: true, note: null })
  assert.deepEqual(devView('trusted', false), {
    change: false, runChecks: false,
    note: "These are the owner's choices: the chat and search use them for everyone. Only the owner can change them.",
  })
  assert.deepEqual(devView('reviewer', false), {
    change: true, runChecks: false,
    note: "Your settings apply only to you: your chat and the playground use them, everyone else keeps the owner's. " +
      "They start as the owner's.",
  })
  assert.equal(devView('reviewer', true).note,
    "Your settings apply only to you: your chat and the playground use them, everyone else keeps the owner's. " +
    "You've changed them.")
})

test('B49.2 the usage line under an answer (tokens, cost) is for the people who change models: owner and Reviewers', () => {
  assert.equal(seesUsage('owner'), true)
  assert.equal(seesUsage('reviewer'), true)
  assert.equal(seesUsage('trusted'), false)
  assert.equal(seesUsage('viewer'), false)
  assert.equal(seesUsage(roleOf(null)), true) // sign-in off: the one local user is the owner
})

test('F154.1: hidden by default, a person is a neutral label: their place and the end of their user id', () => {
  const alice = row({ user_id: 'user_2abcXYZ9', name: 'Alice Example', email: 'alice@example.com' })
  assert.equal(requestWho(alice, 0, false), 'Request 1 · id …XYZ9')
  assert.equal(requestWho(alice, 2, false), 'Request 3 · id …XYZ9')
  assert.equal(requestWho(alice, 0, true), 'Alice Example')
  assert.equal(requestWho({ ...alice, name: null }, 1, true), 'user_2abcXYZ9') // no name from Clerk: the id
})

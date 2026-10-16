// B10: the letters on the user menu's button. Run with `npm test` (node --test).
import assert from 'node:assert/strict'
import test from 'node:test'
import { initials } from './userMenu.ts'

test('B10.11 initials: the first letters of the first two words', () => {
  assert.equal(initials('Alice Example'), 'AE')
  assert.equal(initials('alice'), 'A')
  assert.equal(initials('Ana María de la Cruz'), 'AM')
})

test('B10.11 initials: an email or an id still gives letters, never an empty button', () => {
  assert.equal(initials('bob@example.com'), 'BE')
  assert.equal(initials('user_2abc'), 'U2')
  assert.equal(initials('   '), '?')
})

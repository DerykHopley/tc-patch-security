// B48 (#97, #77): the profile's and the user menu's words. Run with `npm test` (node --test).
import assert from 'node:assert/strict'
import test from 'node:test'
import { cleanName, menuLabel, nameProblem, NAME_MAX } from './profile.ts'

test('B48.21 a name is one line of plain text, trimmed; empty is none (as the server cleans it)', () => {
  assert.equal(cleanName('  Ada  '), 'Ada')
  assert.equal(cleanName('Ada\u0000\u0007 Lovelace\n'), 'Ada Lovelace')
  assert.equal(cleanName('Ada \n\t L.'), 'Ada L.')
  assert.equal(cleanName('   '), null)
  assert.equal(cleanName(''), null)
})

test('B48.21 a name over 60 characters says so before it is sent', () => {
  assert.equal(NAME_MAX, 60)
  assert.equal(nameProblem('y'.repeat(60)), null)
  assert.equal(nameProblem(`  ${'y'.repeat(60)}  `), null) // counted once trimmed
  assert.equal(nameProblem('x'.repeat(61)), 'A display name can be at most 60 characters: this one has 61.')
})

test('B48.22 the user menu: anonymous by default, the name only when given', () => {
  assert.equal(menuLabel(null), 'Your account')
  assert.equal(menuLabel('Ada Lovelace'), 'Your account: Ada Lovelace')
})

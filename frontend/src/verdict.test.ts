// "Fixed in …" under the verdict (B67, #109): one fix as before, each package's fix when OSV lists more than one.
// Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { fixedIn } from './verdict.ts'

test('B67.4 one package: "Fixed in" and the version, as before', () => {
  assert.equal(fixedIn('1.3.0', []), 'Fixed in 1.3.0')
  assert.equal(fixedIn(null, []), null)
})

test('B67.4 more than one package: each package with its fix, in OSV order', () => {
  const both = [
    { package: 'langchain', fixed_version: '0.2.0' },
    { package: 'langchain-community', fixed_version: '0.2.19' },
  ]
  assert.equal(fixedIn('0.2.0', both), 'Fixed in langchain 0.2.0, langchain-community 0.2.19')
  assert.equal(fixedIn('0.2.19', both), 'Fixed in langchain 0.2.0, langchain-community 0.2.19') // same either way
})

test('B67.4 a package with no fix listed is named, not dropped', () => {
  const fixes = [
    { package: 'llama-index', fixed_version: null },
    { package: 'llama-index-core', fixed_version: '0.12.6' },
  ]
  assert.equal(fixedIn(null, fixes), 'Fixed in llama-index-core 0.12.6; llama-index: no fix listed')
  assert.equal(fixedIn(null, [{ package: 'a', fixed_version: null }, { package: 'b', fixed_version: null }]),
    'No fix listed for a, b')
})

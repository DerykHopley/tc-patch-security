// Counts in words (B49 C2, #96): "1 source", never "1 sources". Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { count } from './plural.ts'

test('B49.1 one of a thing is singular, any other number plural', () => {
  assert.equal(count(1, 'source'), '1 source')
  assert.equal(count(0, 'source'), '0 sources')
  assert.equal(count(2, 'tool call'), '2 tool calls')
  assert.equal(count(1, 'tool call'), '1 tool call')
})

test('B49.1 an irregular plural is given', () => {
  assert.equal(count(1, 'entry', 'entries'), '1 entry')
  assert.equal(count(3, 'entry', 'entries'), '3 entries')
})

test('B49.1 big numbers get thousands separators', () => {
  assert.equal(count(12345, 'token'), '12,345 tokens')
})

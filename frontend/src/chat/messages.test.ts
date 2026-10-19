// The conversation's rules (B49 C4, #96): a question the rate limit refused stays only in the box, its refusal shown
// once; history sent to the model holds only turns that happened. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { asked, refused, toHistory } from './messages.ts'
import type { Message } from './useChat.ts'

const user = (id: number, content: string): Message => ({ id, role: 'user', content })
const answer = (id: number, content: string): Message => ({ id, role: 'assistant', content })
const quiet = (id: number, error: string): Message => ({ id, role: 'assistant', content: '', error, quiet: true })
const failed = (id: number): Message => ({ id, role: 'assistant', content: '', error: 'Network down' })

test('B49.5 a refused question leaves the conversation: it is back in the box, the refusal shows once', () => {
  const before = [user(1, 'Hi'), answer(2, 'Hello')]
  const sent = asked(before, user(3, 'Again?'))
  assert.deepEqual(refused(sent, quiet(4, 'Try again at 09:01 UTC.')), [...before, quiet(4, 'Try again at 09:01 UTC.')])
})

test('B49.5 refused again: one note, the latest', () => {
  const once = refused(asked([user(1, 'Hi')], user(2, 'Q')), quiet(3, 'Try at 09:01'))
  const twice = refused(asked(once, user(4, 'Q')), quiet(5, 'Try at 09:02'))
  assert.deepEqual(twice, [user(1, 'Hi'), quiet(5, 'Try at 09:02')])
})

test('B49.5 the next question takes the old refusal away', () => {
  const once = refused(asked([], user(1, 'Q')), quiet(2, 'Try at 09:01'))
  assert.deepEqual(asked(once, user(3, 'Q')), [user(3, 'Q')])
})

test('B49.5 history keeps real turns: not a failed request and its question, not a refusal', () => {
  const ms = [user(1, 'A'), answer(2, 'a'), user(3, 'B'), failed(4), quiet(5, 'limit')]
  assert.deepEqual(toHistory(ms), [{ role: 'user', content: 'A' }, { role: 'assistant', content: 'a' }])
})

test('B49.5 history: the last 10 turns, each cut to 2000 characters', () => {
  const ms = Array.from({ length: 12 }, (_, i) => (i % 2 ? answer(i, 'x'.repeat(3000)) : user(i, `q${i}`)))
  const h = toHistory(ms)
  assert.equal(h.length, 10)
  assert.equal(h[0].content, 'q2')
  assert.equal(h[1].content.length, 2000)
})

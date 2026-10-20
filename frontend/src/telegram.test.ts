// Telegram's setup on Settings (B57, #102): what "Find my chat id" does with the chats the server found. `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { chatsFound } from './telegram.ts'

const me = { id: '987654321', name: 'Deryk H', kind: 'private' }
const group = { id: '-1001234567890', name: 'Patch alerts', kind: 'supergroup' }

test('B57.14 one chat: its id fills the box, and the line names it', () => {
  assert.deepEqual(chatsFound([me]), { fill: '987654321', tone: 'ok',
    text: 'Found your chat with Deryk H. Its id is filled in: save to use it.' })
})

test('B57.14 several chats: the newest private chat fills the box, the others are listed by id', () => {
  assert.deepEqual(chatsFound([group, me]), { fill: '987654321', tone: 'ok',
    text: 'Found your chat with Deryk H. Its id is filled in: save to use it. Also found: Patch alerts ' +
      '(supergroup, -1001234567890).' })
})

test('B57.14 only a group: its id fills the box', () => {
  assert.equal(chatsFound([group]).fill, '-1001234567890')
  assert.match(chatsFound([group]).text, /^Found the supergroup Patch alerts\./)
})

test('B57.14 no chat yet: say what to do, fill nothing', () => {
  assert.deepEqual(chatsFound([]), { fill: null, tone: 'warn',
    text: 'Your bot has no messages from the last 24 hours. Open it in Telegram, send it any message, then try again.' })
})

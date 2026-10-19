// The chat kept for the tab's life (B49 C5, #96; DESIGN.md §11): a reload keeps the conversation, another user never
// sees it, a blocked storage never breaks the chat. Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import { clearChat, loadChat, saveChat, type ChatStorage } from './chatStore.ts'
import type { Message } from './useChat.ts'

function memory(): ChatStorage & { data: Map<string, string> } {
  const data = new Map<string, string>()
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  }
}

const blocked: ChatStorage = {
  getItem: () => {
    throw new Error('SecurityError')
  },
  setItem: () => {
    throw new Error('SecurityError')
  },
  removeItem: () => {
    throw new Error('SecurityError')
  },
}

const q = (id: number, content: string): Message => ({ id, role: 'user', content })

test('B49.4 a saved conversation comes back for the same user', () => {
  const s = memory()
  saveChat(s, 'user_a', [q(1, 'What is prompt injection?')])
  assert.deepEqual(loadChat(s, 'user_a'), [{ ...q(1, 'What is prompt injection?'), restored: true }])
})

test('B49.4 another user in the same tab never sees it', () => {
  const s = memory()
  saveChat(s, 'user_a', [q(1, 'Mine')])
  assert.deepEqual(loadChat(s, 'user_b'), [])
})

test('B49.4 sign-out clears it', () => {
  const s = memory()
  saveChat(s, 'user_a', [q(1, 'Mine')])
  clearChat(s)
  assert.deepEqual(loadChat(s, 'user_a'), [])
})

test('B49.4 blocked storage forgets, never throws', () => {
  assert.doesNotThrow(() => saveChat(blocked, 'user_a', [q(1, 'x')]))
  assert.deepEqual(loadChat(blocked, 'user_a'), [])
  assert.doesNotThrow(() => clearChat(blocked))
  assert.deepEqual(loadChat(null, 'user_a'), []) // no storage at all
})

test('B49.4 a broken or foreign value reads as no conversation', () => {
  const s = memory()
  s.setItem('chat', '{not json')
  assert.deepEqual(loadChat(s, 'user_a'), [])
  s.setItem('chat', JSON.stringify({ user: 'user_a', messages: 'nope' }))
  assert.deepEqual(loadChat(s, 'user_a'), [])
})

test('B49.4 a quiet refusal (a limit) is not kept: it was about that moment', () => {
  const s = memory()
  saveChat(s, 'user_a', [q(1, 'Hi'), { id: 2, role: 'assistant', content: '', error: 'Try at 09:01', quiet: true }])
  assert.deepEqual(loadChat(s, 'user_a').map((m) => m.id), [1])
})

test('B49.4 only the latest messages are kept, and a full storage keeps fewer rather than none', () => {
  const s = memory()
  const many = Array.from({ length: 80 }, (_, i) => q(i + 1, `question ${i + 1}`))
  saveChat(s, 'user_a', many)
  const kept = loadChat(s, 'user_a')
  assert.equal(kept.length, 40)
  assert.equal(kept.at(-1)?.id, 80)

  let room = 600 // characters this storage takes, as a full sessionStorage refuses a big value
  const tight: ChatStorage = {
    ...s,
    setItem: (k, v) => {
      if (v.length > room) throw new Error('QuotaExceededError')
      s.setItem(k, v)
    },
  }
  saveChat(tight, 'user_a', many)
  const fewer = loadChat(s, 'user_a')
  assert.ok(fewer.length > 0 && fewer.length < 40, String(fewer.length))
  assert.equal(fewer.at(-1)?.id, 80) // the newest survive
  room = 0
  saveChat(tight, 'user_a', many) // nothing fits: the old value goes, so a reload can't show an older conversation
  assert.deepEqual(loadChat(s, 'user_a'), [])
})

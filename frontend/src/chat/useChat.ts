import { useState } from 'react'
import { chat, type ChatReply, type Turn } from '../api.ts'

export interface Message {
  id: number // unique for the page's lifetime: a new chat never reuses one
  role: 'user' | 'assistant'
  content: string
  reply?: ChatReply // assistant answers only
  error?: string // set when the request failed; never sent back as history
}

// The backend accepts at most 10 history turns of 2000 characters each (the guard's limits).
const MAX_TURNS = 10
const MAX_TURN_CHARS = 2000

let nextId = 1

// The last 10 turns that really happened: a failed request and the question that caused it are left out.
function toHistory(messages: Message[]): Turn[] {
  return messages
    .filter((m, i) => !m.error && !messages[i + 1]?.error)
    .slice(-MAX_TURNS)
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_TURN_CHARS) }))
}

/** One conversation for the whole app, so moving between pages never loses it. */
export function useChat() {
  const [messages, setMessages] = useState<Message[]>([])
  const [pending, setPending] = useState(false)

  async function send(text: string) {
    if (pending) return
    const history = toHistory(messages)
    setMessages((ms) => [...ms, { id: nextId++, role: 'user', content: text }])
    setPending(true)
    try {
      const reply = await chat(text, history)
      setMessages((ms) => [...ms, { id: nextId++, role: 'assistant', content: reply.answer, reply }])
    } catch (e) {
      const error = e instanceof Error ? e.message : 'Something went wrong. Try again.'
      setMessages((ms) => [...ms, { id: nextId++, role: 'assistant', content: '', error }])
    } finally {
      setPending(false)
    }
  }

  return { messages, pending, send, newChat: () => setMessages([]) }
}

export type ChatState = ReturnType<typeof useChat>

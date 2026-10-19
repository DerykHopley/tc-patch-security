import type { Turn } from '../api.ts'
import type { Message } from './useChat.ts'

// The conversation's rules as plain functions (messages.test.ts), so useChat.ts is only the React state around them.

// The backend accepts at most 10 history turns of 2000 characters each (the guard's limits).
const MAX_TURNS = 10
const MAX_TURN_CHARS = 2000

/** The last 10 turns that really happened: a failed request and the question that caused it are left out, and so
 *  are a refusal's note (B11) and a refine's result (B24), which hold no turn. */
export function toHistory(messages: Message[]): Turn[] {
  return messages
    .filter((m, i) => !m.error && !m.refined && !(messages[i + 1]?.error && !messages[i + 1]?.quiet))
    .slice(-MAX_TURNS)
    .map((m) => ({ role: m.role, content: m.content.slice(0, MAX_TURN_CHARS) }))
}

/** A question goes in. An earlier refusal's note goes: it was about the question before (B49 C4). */
export function asked(messages: Message[], question: Message): Message[] {
  return [...messages.filter((m) => !m.quiet), question]
}

/** A limit or the spending cap refused the last question (B11, B49 C4): it leaves the conversation (the box has it
 *  back), and the refusal shows once, as the conversation's last line. Before B49 the question showed twice: as a
 *  sent bubble and back in the box. */
export function refused(messages: Message[], note: Message): Message[] {
  const last = messages.findLastIndex((m) => m.role === 'user')
  return [...messages.filter((m, i) => i !== last && !m.quiet), note]
}

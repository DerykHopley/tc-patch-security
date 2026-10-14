import { useEffect, useState } from 'react'
import type { Mood } from '../components/Robot.tsx'
import type { ChatState } from './useChat.ts'

const HAPPY_MS = 3000

/**
 * Patch's mood and the unread mark, from the chat (DESIGN.md §8.3). One source for the chat button and the
 * chat header, so they always agree:
 * - thinking while an answer is on its way;
 * - alert while the last message is an error;
 * - happy for 3 s after an answer arrives, and while an answer is unread (it arrived with the chat closed);
 * - idle otherwise.
 */
export function usePatch(chat: ChatState, open: boolean): { mood: Mood; unread: boolean } {
  const { messages, pending } = chat
  const last = messages.at(-1)

  // Unread: messages arrived since the chat was last open. Kept up to date while rendering (no effect needed).
  const [seen, setSeen] = useState(messages.length)
  if (open && seen !== messages.length) setSeen(messages.length)
  const unread = !open && messages.length > seen && last?.role === 'assistant'

  // Happy for 3 s after each answer: the timer only calms him down again.
  const [calmed, setCalmed] = useState<number | null>(null)
  const answered = last?.role === 'assistant' && !last.error ? last.id : null
  useEffect(() => {
    if (answered === null) return
    const t = setTimeout(() => setCalmed(answered), HAPPY_MS)
    return () => clearTimeout(t)
  }, [answered])
  const happy = answered !== null && calmed !== answered

  const mood: Mood = pending ? 'thinking' : last?.error ? 'alert' : happy || unread ? 'happy' : 'idle'
  return { mood, unread }
}

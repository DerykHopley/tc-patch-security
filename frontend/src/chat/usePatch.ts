import { useEffect, useState } from 'react'
import { nextPose, pickPose, type Mood, type Pose, type Random, type Variant } from '../components/patchPose.ts'
import type { ChatState } from './useChat.ts'

const HAPPY_MS = 3000

/**
 * Patch's mood and the unread mark, from the chat (DESIGN.md §8.3). One source for the chat button and the
 * chat header, so they always agree:
 * - thinking while an answer is on its way;
 * - alert while the last message is an error;
 * - happy for 3 s after an answer arrives, and while an answer is unread (it arrived with the chat closed);
 * - idle otherwise.
 *
 * Each mood has four animations (A06b). Patch gets one of them at random when he enters a mood, and keeps it while
 * he stays in it, so a re-render never makes him flicker. Places without a mood (the welcome banner, the empty-chat
 * greeting, the snapshot card) show idle, with one variant picked on page load (`restVariant`). `random` is
 * injectable so tests can pick a known variant.
 */
export function usePatch(
  chat: ChatState,
  open: boolean,
  random: Random = Math.random,
): { mood: Mood; variant: Variant; restVariant: Variant; unread: boolean } {
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

  const mood: Mood = pending ? 'thinking' : last?.error && !last.quiet ? 'alert' : happy || unread ? 'happy' : 'idle'

  // A new pick only when the mood changes, kept up to date while rendering like `seen` above.
  const [pose, setPose] = useState<Pose>(() => pickPose(mood, random))
  const next = nextPose(pose, mood, random)
  if (next !== pose) setPose(next)
  const [restVariant] = useState(() => pickPose('idle', random).variant)
  return { mood, variant: next.variant, restVariant, unread }
}

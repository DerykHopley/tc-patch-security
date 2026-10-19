import { useEffect, useState } from 'react'
import {
  ApiError,
  chat,
  type ChatReply,
  type ExplainLevel,
  type PageContext,
  type RefineFilter,
  type Refined,
} from '../api.ts'
import { announceWatchlistChanged, checkedFromChat } from '../watchlistEvents.ts'
import { loadChat, saveChat, tabStorage } from './chatStore.ts'
import { asked, refused, toHistory } from './messages.ts'

/** A refine button's result (B24): the card's tool run again with a filter, the filters it had, and its page. */
export type RefinedResult = Refined & { filters: RefineFilter[]; page: PageContext }

export interface Message {
  id: number // unique for the page's lifetime: a new chat never reuses one
  role: 'user' | 'assistant'
  content: string
  reply?: ChatReply // assistant answers only
  error?: string // set when the request failed; never sent back as history
  quiet?: boolean // B11: the error is a limit or the spending cap, shown as a quiet note, not an error bubble
  refined?: RefinedResult // B24: no question and no model text, so never sent back as history
  restored?: boolean // B49: read back from the tab's storage after a reload (chatStore.ts), not new
}

// B11: refusals that aren't faults: a chat limit (429, the retry time in its message) and the spending cap (402).
const QUIET = new Set(['rate_limited', 'spending_cap'])

let nextId = 1

/** The user's conversation from this tab's storage; nothing while who it is isn't known yet. */
function restore(user: string | null): Message[] {
  const restored = user === null ? [] : loadChat(tabStorage(), user)
  nextId = Math.max(nextId, ...restored.map((m) => m.id + 1)) // a new message never reuses a restored id
  return restored
}

/** One conversation for the whole app, so moving between pages never loses it. `pageContext`: what the user is
 *  looking at at the moment of asking (A18, usePageContext's `current`), sent with each message. `user`: whose
 *  conversation it is: kept for the tab's life under that user (B49 C5, chatStore.ts), so a reload keeps it. null:
 *  not known yet (Clerk's user still loading): nothing is read or written, so the stored conversation isn't lost. */
export function useChat(pageContext: () => PageContext, user: string | null) {
  const [messages, setMessages] = useState<Message[]>(() => restore(user))
  const [owner, setOwner] = useState(user)
  if (owner !== user) {
    // Another user (or the user now known): their own conversation, never the one on screen
    setOwner(user)
    setMessages(restore(user))
  }
  useEffect(() => {
    if (user !== null) saveChat(tabStorage(), user, messages)
  }, [user, messages])
  const [pending, setPending] = useState(false)
  // A level picked in the chat header for the next question only (A19); null = the saved level.
  const [nextLevel, setNextLevel] = useState<ExplainLevel | null>(null)

  /** savedLevel: ignore a level picked for the next question ("Explain it" and "Ask about this" use the saved one).
   *  page: the page context to send instead of the current one (B24: "Ask about this" on a tool card sends its
   *  answer's context with that CVE). True when Patch answered; false when the request failed or another was on its
   *  way (B20: the box gets it back). */
  async function send(
    text: string,
    { savedLevel = false, page }: { savedLevel?: boolean; page?: PageContext } = {},
  ): Promise<boolean> {
    if (pending) return false
    const history = toHistory(messages)
    const level = savedLevel ? undefined : (nextLevel ?? undefined)
    page ??= pageContext()
    if (!savedLevel) setNextLevel(null)
    setMessages((ms) => asked(ms, { id: nextId++, role: 'user', content: text }))
    setPending(true)
    try {
      const reply = await chat(text, history, level, page)
      setMessages((ms) => [...ms, { id: nextId++, role: 'assistant', content: reply.answer, reply }])
      if (checkedFromChat(reply)) announceWatchlistChanged() // the dashboard shows the new CVEs and last check
      return true
    } catch (e) {
      const error = e instanceof Error ? e.message : 'Something went wrong. Try again.'
      const quiet = e instanceof ApiError && QUIET.has(e.code ?? '')
      const note: Message = { id: nextId++, role: 'assistant', content: '', error, quiet }
      // B49 C4: a refused question leaves the conversation (the box has it back, B20), its note shows once
      setMessages((ms) => (quiet ? refused(ms, note) : [...ms, note]))
      return false
    } finally {
      setPending(false)
    }
  }

  /** B24: a refine button's result, as a message of its own at the end of the conversation. */
  function addRefined(refined: RefinedResult) {
    setMessages((ms) => [...ms, { id: nextId++, role: 'assistant', content: '', refined }])
  }

  return { messages, pending, send, addRefined, nextLevel, setNextLevel, newChat: () => setMessages([]) }
}

export type ChatState = ReturnType<typeof useChat>

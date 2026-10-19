import type { Message } from './useChat.ts'

// The chat kept for the tab's life (B49 C5, #96; DESIGN.md §11): a reload used to clear the conversation. It lives in
// sessionStorage, so a reload keeps it and closing the tab clears it, and it is never sent anywhere.
// - Per user: one key holds the conversation and whose it is. Another signed-in user in the same tab reads nothing
//   (and their first answer replaces it). Signing out clears it (auth/useFrontDoor.ts).
// - Wrapped like every stored value (storage.ts): blocked storage forgets, it never breaks the chat.
// - The latest 40 messages. A full storage keeps fewer of the newest rather than none; if nothing fits, the old value
//   goes, so a reload can never bring back an older conversation than the one on screen.
// sessionStorage, not localStorage: a conversation can hold what you asked about your own stack, and it should not
// outlive the tab on a shared computer.

export type ChatStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

const KEY = 'chat'
const KEEP = 40

/** The tab's sessionStorage, or null where reading it throws (blocked storage). */
export function tabStorage(): ChatStorage | null {
  try {
    return window.sessionStorage
  } catch {
    return null
  }
}

/** The user's conversation from an earlier load of this tab, each message marked `restored`; [] when there is none,
 *  it is someone else's, or storage is blocked. */
export function loadChat(storage: ChatStorage | null, user: string): Message[] {
  try {
    const saved: unknown = JSON.parse(storage?.getItem(KEY) ?? 'null')
    if (!saved || typeof saved !== 'object') return []
    const { user: owner, messages } = saved as { user?: unknown; messages?: unknown }
    if (owner !== user || !Array.isArray(messages)) return []
    return (messages as Message[]).map((m) => ({ ...m, restored: true }))
  } catch {
    return []
  }
}

/** Keeps the conversation for this tab. A quiet refusal (a limit, B11) is left out: it was about that moment. */
export function saveChat(storage: ChatStorage | null, user: string, messages: Message[]): void {
  const kept = messages.filter((m) => !m.quiet).map((m) => ({ ...m, restored: undefined })) // JSON leaves it out
  for (let n = Math.min(KEEP, kept.length); n > 0; n = Math.floor(n / 2)) {
    try {
      storage?.setItem(KEY, JSON.stringify({ user, messages: kept.slice(-n) }))
      return
    } catch {
      // full (or blocked): try with fewer
    }
  }
  clearChat(storage) // an empty chat, or nothing fits
}

export function clearChat(storage: ChatStorage | null): void {
  try {
    storage?.removeItem(KEY)
  } catch {
    // blocked: there is nothing stored to clear
  }
}

// Telegram's setup on Settings (B57, #102): what "Find my chat id" does with the chats the server found through
// Telegram's getUpdates (backend/app/notify.py `TelegramNotifier.chats`). Pure functions; the card is
// components/ServerFields.tsx.

import type { TelegramChat } from './api.ts'

export interface ChatsFound {
  fill: string | null // the chat id to put in the box; null: nothing found
  tone: 'ok' | 'warn' // the line's edge (DESIGN.md §5.7's edge rule)
  text: string
}

const what = (c: TelegramChat) => (c.kind === 'private' ? `your chat with ${c.name}` : `the ${c.kind} ${c.name}`)

/** The chat to fill in and the line under the box. The newest private chat wins (the owner messaging their own bot);
 *  without one, the newest chat. The server lists them newest first. */
export function chatsFound(chats: TelegramChat[]): ChatsFound {
  if (chats.length === 0) {
    return { fill: null, tone: 'warn',
      text: 'Your bot has no messages from the last 24 hours. Open it in Telegram, send it any message, then try again.' }
  }
  const pick = chats.find((c) => c.kind === 'private') ?? chats[0]
  const others = chats.filter((c) => c !== pick).map((c) => `${c.name} (${c.kind}, ${c.id})`)
  const found = what(pick)
  return { fill: pick.id, tone: 'ok',
    text: `Found ${found}. Its id is filled in: save to use it.${others.length ? ` Also found: ${others.join(', ')}.` : ''}` }
}

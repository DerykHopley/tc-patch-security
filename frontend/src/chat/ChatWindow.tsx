import type { CSSProperties } from 'react'
import type { Example, PageContext } from '../api.ts'
import { PinIcon } from '../components/Icons.tsx'
import { Robot, type Mood } from '../components/Robot.tsx'
import { contextWords } from '../pageContext.ts'
import '../styles/chat.css'
import { Conversation } from './Conversation.tsx'
import { LevelSwitch } from './LevelSwitch.tsx'
import { useSavedLevel } from './savedLevel.ts'
import type { ChatState } from './useChat.ts'
import type { ChatLayout } from './useChatLayout.ts'

// The chat window (DESIGN.md §6.2, §6.3): the bubble above Patch's button (opens with a pop), the enlarged bubble,
// or pinned beside the page. Header: Patch with his mood, the page underneath with the
// filters and selected CVE Patch is told about (A18), New chat, Pin (enlarged or pinned
// only), Make larger (not when pinned), close; under them the explain-level switch (A19). Empty: Patch waving behind a speech bubble, with suggested questions.
// The same element in every layout, so pinning never loses the conversation's scroll.
export function ChatWindow({ chat, mood, pageTitle, context, productName, suggestions, examples, layout, onClose }: {
  chat: ChatState
  mood: Mood
  pageTitle: string
  context: PageContext // what Patch is told about the page (A18): the chip shows it
  productName?: string
  suggestions: string[]
  examples: Example[]
  layout: ChatLayout
  onClose: () => void
}) {
  const { expanded, pinned } = layout
  const savedLevel = useSavedLevel()
  const words = contextWords(context, productName)
  const chipText = [`on ${pageTitle}`, ...words].join(' · ')
  const greeting = (
    <div className="greeting">
      <div className="robot-slot">
        <Robot mood="happy" size={92} className="wave" />
      </div>
      <p className="greeting-bubble">
        Hi, I'm <strong>Patch</strong>! I know the OWASP LLM Top 10, MITRE ATLAS and the CVEs in your LLM stack. What
        shall we look at?
      </p>
    </div>
  )
  return (
    <aside
      className={`chat-window${pinned ? ' pinned' : expanded ? ' expanded' : ''}`}
      aria-label="Chat with Patch"
      style={{ '--pin-width': `${layout.width}px` } as CSSProperties}
    >
      <header className="chat-head">
        <div className="chat-title">
          <Robot mood={mood} size={34} />
          <strong>Patch</strong>
          <span
            className="context-chip"
            title={`Patch knows: the ${pageTitle} page${words.length ? `, ${words.join(', ')}` : ''}`}
          >
            {chipText}
          </span>
        </div>
        <button type="button" onClick={chat.newChat} disabled={chat.pending || chat.messages.length === 0}>
          New chat
        </button>
        {(expanded || pinned) && (
          <button
            type="button"
            className="pin-btn"
            aria-pressed={pinned}
            aria-label={pinned ? 'Unpin: float the chat over the page' : 'Pin: dock the chat beside the page'}
            title={pinned ? 'Unpin: float over the page' : 'Pin beside the page'}
            onClick={() => layout.setPinned(!pinned)}
          >
            <PinIcon />
            {pinned ? 'Unpin' : 'Pin'}
          </button>
        )}
        {!pinned && (
          <button
            type="button"
            className="icon-btn size-btn"
            aria-label={expanded ? 'Make smaller' : 'Make larger'}
            title={expanded ? 'Make smaller' : 'Make larger'}
            onClick={layout.toggleExpanded}
          >
            <span aria-hidden="true">{expanded ? '⤡' : '⤢'}</span>
          </button>
        )}
        <button type="button" className="icon-btn" aria-label="Close the chat" title="Close" onClick={onClose}>
          <span aria-hidden="true">✕</span>
        </button>
        <LevelSwitch saved={savedLevel} next={chat.nextLevel} onPick={chat.setNextLevel} />
      </header>
      <Conversation
        messages={chat.messages}
        pending={chat.pending}
        onSend={chat.send}
        greeting={greeting}
        suggestions={suggestions}
        examples={examples}
      />
    </aside>
  )
}

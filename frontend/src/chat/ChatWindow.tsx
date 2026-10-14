import type { Example } from '../api.ts'
import { Robot, type Mood } from '../components/Robot.tsx'
import '../styles/chat.css'
import { Conversation } from './Conversation.tsx'
import type { ChatState } from './useChat.ts'

// The bubble window (DESIGN.md §6.2): opens above Patch's button with a pop. Header: Patch with his mood, the page
// underneath, New chat, Make larger, close. Empty: Patch waving behind a speech bubble, with suggested questions.
export function ChatWindow({ chat, mood, pageTitle, suggestions, examples, onClose }: {
  chat: ChatState
  mood: Mood
  pageTitle: string
  suggestions: string[]
  examples: Example[]
  onClose: () => void
}) {
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
    <aside className="chat-window" aria-label="Chat with Patch">
      <header className="chat-head">
        <div className="chat-title">
          <Robot mood={mood} size={34} />
          <strong>Patch</strong>
          <span className="context-chip" title="The page under the chat">
            on {pageTitle}
          </span>
        </div>
        <button type="button" onClick={chat.newChat} disabled={chat.pending || chat.messages.length === 0}>
          New chat
        </button>
        {/* Enlarging (and pinning) arrive with the chat layout ticket (A07): named and reachable, does nothing yet. */}
        <button
          type="button"
          className="icon-btn"
          aria-label="Make larger"
          aria-disabled="true"
          aria-describedby="larger-soon"
          title="Make larger: coming soon"
        >
          <span aria-hidden="true">⤢</span>
          <span id="larger-soon" className="visually-hidden">
            Coming soon
          </span>
        </button>
        <button type="button" className="icon-btn" aria-label="Close the chat" title="Close" onClick={onClose}>
          <span aria-hidden="true">✕</span>
        </button>
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

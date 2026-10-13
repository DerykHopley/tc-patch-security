import type { Example } from "../api";
import type { ChatState } from "../hooks/useChat";
import { Chat } from "./Chat";
import { useMood } from "../hooks/useMood";
import { Robot } from "./Robot";

// The chat as it appears over a page: in the bubble window, or pinned beside the page. Patch fronts it.
export function ChatSurface({ chat, examples, pageLabel, suggestions, onClose, onExpand, expanded, onPin, pinned, autoFocus }: {
  chat: ChatState;
  examples: Example[];
  pageLabel: string;
  suggestions: string[];
  onClose?: () => void;
  onExpand?: () => void;
  expanded?: boolean;
  /** Enlarged bubble: pin docks the chat beside the page; unpin floats it over the page again. */
  onPin?: () => void;
  pinned?: boolean;
  autoFocus?: boolean;
}) {
  const mood = useMood(chat);
  return (
    <div className="chat-surface">
      <header className="surface-head">
        <div className="surface-title">
          <Robot mood={mood} size={34} className="head-bot" />
          <strong>Patch</strong>
          <span className="context-chip" title="The page under the chat">on {pageLabel}</span>
        </div>
        <button type="button" onClick={chat.newChat} disabled={chat.pending || chat.messages.length === 0}>New chat</button>
        {onPin && (
          <button type="button" className={`icon-btn pin-btn${pinned ? " pinned" : ""}`} onClick={onPin} aria-pressed={!!pinned}
            aria-label={pinned ? "Unpin: float the chat over the page" : "Pin: dock the chat beside the page"}
            title={pinned ? "Unpin: float over the page" : "Pin beside the page"}>
            <svg width="14" height="14" viewBox="0 0 16 16" aria-hidden="true">
              <path d="M5 1.5h6l-1 4.5 2.5 2.5v1.5H8.75V15h-1.5v-5H3.5V8.5L6 6z" />
            </svg>
            <span>{pinned ? "Unpin" : "Pin"}</span>
          </button>
        )}
        {onExpand && (
          <button type="button" className="icon-btn" onClick={onExpand} aria-label={expanded ? "Make smaller" : "Make larger"}
            title={expanded ? "Make smaller" : "Make larger"}>{expanded ? "⤡" : "⤢"}</button>
        )}
        {onClose && (
          <button type="button" className="icon-btn" onClick={onClose} aria-label="Close the chat" title="Close (Esc)">✕</button>
        )}
      </header>
      <Chat
        messages={chat.messages}
        examples={examples}
        pending={chat.pending}
        selected={chat.selected}
        onSend={chat.send}
        onSelect={chat.setSelected}
        suggestions={chat.messages.length === 0 ? suggestions : []}
        autoFocus={autoFocus}
        greeting={(
          <div className="bot-greeting">
            <Robot mood="happy" size={92} className="wave" />
            <p className="bot-bubble">Hi, I'm <strong>Patch</strong>! I know the OWASP LLM Top 10, MITRE ATLAS and the CVEs in your LLM stack. What shall we look at?</p>
          </div>
        )}
      />
    </div>
  );
}


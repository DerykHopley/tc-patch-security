import type { CSSProperties } from 'react'
import type { Example } from '../api.ts'
import { DownloadIcon, PinIcon } from '../components/Icons.tsx'
import { Robot, type Mood, type Variant } from '../components/Robot.tsx'
import '../styles/chat.css'
import { CardActionsContext, type CardActionsHandle } from './CardActions.tsx'
import { Conversation } from './Conversation.tsx'
import { chatToMarkdown, exportFileName } from './exportChat.ts'
import { shownProposal } from './ProposalCard.tsx'
import { LevelSwitch } from './LevelSwitch.tsx'
import { useSavedLevel } from './savedLevel.ts'
import type { ChatState } from './useChat.ts'
import type { ChatLayout } from './useChatLayout.ts'

/** Saves text as a file: a Blob behind a temporary `<a download>`. Nothing is sent anywhere (F147). */
function download(name: string, text: string) {
  const url = URL.createObjectURL(new Blob([text], { type: 'text/markdown;charset=utf-8' }))
  const a = document.createElement('a')
  a.href = url
  a.download = name
  document.body.append(a)
  a.click()
  a.remove()
  setTimeout(() => URL.revokeObjectURL(url)) // after the click has started the download
}

// The chat window (DESIGN.md §6.2, §6.3): the bubble above Patch's button (opens with a pop), the enlarged bubble,
// or pinned beside the page. Header: Patch with his mood, the page underneath with the
// filters and selected CVE Patch is told about (A18), New chat, Export (F147), Pin (enlarged or pinned
// only), Make larger (not when pinned), close; under them the explain-level switch (A19). Empty: Patch (idle, in the
// variant picked on page load) behind a speech bubble, with suggested questions.
// The same element in every layout, so pinning never loses the conversation's scroll.
export function ChatWindow({
  chat, mood, variant, restVariant, pageTitle, words, suggestions, examples, layout, asOf, onClose, showUsage, model,
}: {
  chat: ChatState
  model: string | null // the model in use, named in the Export (F147); null while not known
  showUsage: boolean // B49 C1: tokens and cost under each answer, for the owner and Reviewers only
  asOf: string | null // the data's as-of date (B24: an accepted risk's review date must be after it)
  mood: Mood
  variant: Variant // the mood's animation, the same as on the button
  restVariant: Variant // the greeting's idle animation
  pageTitle: string
  words: string[] // what Patch is told about the page (A18), in words: the chip shows them
  suggestions: string[]
  examples: Example[]
  layout: ChatLayout
  onClose: () => void
}) {
  const { expanded, pinned } = layout
  const savedLevel = useSavedLevel()
  const chipText = [`on ${pageTitle}`, ...words].join(' · ')
  // B24: what the tool cards' buttons need. "Ask about this" asks with the saved level, as on the CVEs page.
  const cardActions: CardActionsHandle = {
    ask: (cve, page) => void chat.send(`Explain ${cve} and how to defend against it.`, { savedLevel: true, page }),
    addRefined: chat.addRefined,
    pending: chat.pending,
    asOf,
  }
  const greeting = (
    <div className="greeting">
      <div className="greeting-bubble">
        {/* The chat button's Patch, on the bubble's top-left corner; the first line wraps beside him (§8.2) */}
        <span className="robot-slot">
          <Robot size={58} pose={{ mood: 'idle', variant: restVariant }} />
        </span>
        <p>
          Hi, I'm <strong>Patch</strong>! I know the OWASP LLM Top 10, MITRE ATLAS and the CVEs on your watchlist.
          What shall we look at?
        </p>
      </div>
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
          <Robot pose={{ mood, variant }} size={34} />
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
        <button
          type="button"
          className="icon-btn"
          aria-label="Export chat as Markdown"
          title="Download this conversation as a Markdown file"
          onClick={() => {
            const now = new Date()
            const meta = { now, model, level: savedLevel, showUsage, shown: shownProposal }
            download(exportFileName(now), chatToMarkdown(chat.messages, meta))
          }}
          disabled={chat.messages.length === 0}
        >
          <DownloadIcon />
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
      <CardActionsContext value={cardActions}>
        <Conversation
          messages={chat.messages}
          pending={chat.pending}
          onSend={chat.send}
          greeting={greeting}
          suggestions={suggestions}
          examples={examples}
          showUsage={showUsage}
        />
      </CardActionsContext>
    </aside>
  )
}

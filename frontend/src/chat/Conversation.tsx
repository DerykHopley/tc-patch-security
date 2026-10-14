import {
  createContext,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
} from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import type { ChatReply, Example } from '../api.ts'
import { AnswerDetails, firstTab, sourceId, type DetailTab } from './AnswerDetails.tsx'
import type { Message } from './useChat.ts'

const reducedMotion = () => window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
const scrollTo = (el: Element | null, block: ScrollLogicalPosition) =>
  el?.scrollIntoView({ behavior: reducedMotion() ? 'auto' : 'smooth', block })

// "[2]" becomes a link to source 2 when the answer has that source; anything else stays plain text.
const linkCitations = (text: string, ns: Set<number>) =>
  text.replace(/\[(\d+)\](?!\()/g, (whole, n: string) => (ns.has(Number(n)) ? `[[${n}]](#source-${n})` : whole))

// Two significant figures: $0.00061, $0.012, $1.2; a free answer shows $0.
const dollars = (cost: number) => `$${Number(cost.toPrecision(2))}`

function Usage({ reply }: { reply: ChatReply }) {
  const u = reply.usage
  return (
    <p className="usage">
      {u.input_tokens.toLocaleString()} in · {u.output_tokens.toLocaleString()} out · {u.llm_calls} LLM calls ·{' '}
      {reply.steps} steps · {dollars(u.cost)}
      {u.estimated && <span className="chip">estimated</span>}
    </p>
  )
}

/** The citation check's result, quietly: a sourced answer that cites none of them, and citations removed. */
function CitationNote({ reply }: { reply: ChatReply }) {
  const bad = reply.bad_citations
  if (!reply.no_citations && bad.length === 0) return null
  const parts = []
  if (reply.no_citations) parts.push('No sources cited.')
  if (bad.length > 0) {
    const list = bad.map((n) => `[${n}]`).join(' ')
    parts.push(`Removed ${bad.length === 1 ? 'citation' : 'citations'} ${list}: no matching source.`)
  }
  return <p className="cite-note">{parts.join(' ')}</p>
}

// The answer a citation belongs to: Markdown renders the links, the answer handles the click.
const CiteContext = createContext<(n: number) => void>(() => {})

// Links in an answer: a citation opens its source; anything else opens in a new tab. Raw HTML is never rendered
// (react-markdown escapes it), so an answer can't inject markup.
function AnswerLink({ href = '', children }: { href?: string; children?: ReactNode }) {
  const cite = useContext(CiteContext)
  if (!href.startsWith('#source-')) {
    return (
      <a href={href} target="_blank" rel="noreferrer">
        {children}
      </a>
    )
  }
  return (
    <a
      href={href}
      className="cite"
      onClick={(e) => {
        e.preventDefault()
        cite(Number(href.slice('#source-'.length)))
      }}
    >
      {children}
    </a>
  )
}

const MARKDOWN_PARTS = { a: AnswerLink }

/** One answer with its inline details. A citation opens the details on Sources and scrolls to that source. */
function Answer({ reply }: { reply: ChatReply }) {
  const prefix = useId().replace(/:/g, '')
  const [open, setOpen] = useState(false)
  const [tab, setTab] = useState<DetailTab>(() => firstTab(reply))
  const scrollTarget = useRef<{ id: string; block: ScrollLogicalPosition } | null>(null)
  const ns = new Set(reply.sources.map((s) => s.n))

  useEffect(() => {
    // After the render that opened the details: bring the target into view.
    if (!scrollTarget.current) return
    scrollTo(document.getElementById(scrollTarget.current.id), scrollTarget.current.block)
    scrollTarget.current = null
  })

  function toggle() {
    setOpen(!open)
    if (!open) scrollTarget.current = { id: `${prefix}-details`, block: 'nearest' } // often below the fold
  }

  function cite(n: number) {
    setOpen(true)
    setTab('sources')
    scrollTarget.current = { id: sourceId(prefix, n), block: 'center' }
  }

  const hasDetails = reply.sources.length > 0 || reply.tool_calls.length > 0
  return (
    <>
      <div className="answer-text">
        <CiteContext value={cite}>
          <Markdown remarkPlugins={[remarkGfm]} components={MARKDOWN_PARTS}>
            {linkCitations(reply.answer, ns)}
          </Markdown>
        </CiteContext>
      </div>
      {reply.flags.includes('injection_phrasing') && (
        <p className="flag-note">This message looks like an injection attempt. It was answered, and logged.</p>
      )}
      <CitationNote reply={reply} />
      <Usage reply={reply} />
      {hasDetails && (
        <>
          <button type="button" className="details-toggle" aria-expanded={open} onClick={toggle}>
            {open ? 'Hide' : 'Show'} {reply.sources.length} sources · {reply.tool_calls.length} tool calls
          </button>
          {open && (
            <div id={`${prefix}-details`}>
              <AnswerDetails reply={reply} prefix={prefix} tab={tab} onTab={setTab} />
            </div>
          )}
        </>
      )}
    </>
  )
}

/** The message list, the greeting with suggestions while empty, and the message box. */
export function Conversation({ messages, pending, onSend, greeting, suggestions, examples }: {
  messages: Message[]
  pending: boolean
  onSend: (text: string) => void
  greeting: ReactNode
  suggestions: string[]
  examples: Example[]
}) {
  const [draft, setDraft] = useState('')
  const endRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  const seen = useRef({ count: -1, pending: false })

  useEffect(() => inputRef.current?.focus(), [])
  useEffect(() => {
    // A new message or the thinking note: keep the end of the conversation in view.
    if (seen.current.count === messages.length && seen.current.pending === pending) return
    seen.current = { count: messages.length, pending }
    scrollTo(endRef.current, 'end')
  })

  const canSend = draft.trim().length > 0 && !pending

  function submit(e?: FormEvent) {
    e?.preventDefault()
    if (!canSend) return
    onSend(draft.trim())
    setDraft('')
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      // Enter sends, Shift+Enter adds a line.
      e.preventDefault()
      submit()
    }
  }

  return (
    <div className="conversation">
      <div className="messages">
        {messages.length === 0 && (
          <>
            {greeting}
            <div className="suggestions">
              {suggestions.map((q) => (
                <button key={q} type="button" disabled={pending} onClick={() => onSend(q)}>
                  {q}
                </button>
              ))}
            </div>
            {examples.length > 0 && (
              <details className="more-examples">
                <summary>More examples</summary>
                <div className="example-list">
                  {examples.map((ex) => (
                    <button key={ex.id} type="button" disabled={pending} onClick={() => onSend(ex.question)}>
                      {ex.question}
                    </button>
                  ))}
                </div>
              </details>
            )}
          </>
        )}
        {messages.map((m) => (
          <div key={m.id}className={`message ${m.role}${m.error ? ' error' : ''}`}>
            {m.error ? <p role="alert">{m.error}</p> : m.reply ? <Answer reply={m.reply} /> : <p>{m.content}</p>}
          </div>
        ))}
        {pending && (
          <output className="thinking-note">Patch is thinking…</output>
        )}
        <div ref={endRef} />
      </div>
      <form className="composer" onSubmit={submit}>
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask Patch a question…"
          rows={2}
          maxLength={1000}
          aria-label="Message"
        />
        <button type="submit" disabled={!canSend}>
          Send
        </button>
      </form>
    </div>
  )
}

import { useEffect, useRef, useState, type FormEvent, type KeyboardEvent, type ReactNode } from "react";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatReply, Example } from "../api";
import { ChatDetails } from "./ChatDetails";
import { UsageLine } from "./UsageLine";

export interface Message {
  role: "user" | "assistant";
  content: string;
  reply?: ChatReply; // assistant answers only
  error?: string; // set when the request failed (U7); not sent back as history
}

interface Props {
  messages: Message[];
  examples: Example[];
  pending: boolean;
  selected: number | null;
  onSend: (text: string) => void;
  onSelect: (index: number) => void;
  /** Questions that fit the page underneath the overlay. */
  suggestions?: string[];
  autoFocus?: boolean;
  /** Shown in place of the plain intro line while the chat is empty (the Playful design's robot). */
  greeting?: ReactNode;
}

// Turn "[2]" into a link to source 2, unless it's already a Markdown link. R6, U4.
const linkCitations = (text: string) => text.replace(/\[(\d+)\](?!\()/g, "[[$1]](#source-$1)");

// U1–U3, U7, U8: the message list, example buttons, input box and spinner.
export function Chat({ messages, examples, pending, selected, onSend, onSelect, suggestions = [], autoFocus = false, greeting }: Props) {
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState<Set<number>>(new Set());
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => { if (autoFocus) inputRef.current?.focus(); }, [autoFocus]);
  const toggle = (i: number) => {
    const opening = !open.has(i);
    setOpen((o) => { const n = new Set(o); if (n.has(i)) n.delete(i); else n.add(i); return n; });
    // The details open below the answer, often out of sight in a small window: bring them into view.
    if (opening) requestAnimationFrame(() => requestAnimationFrame(() =>
      document.getElementById(`c${i}-details`)?.scrollIntoView({ behavior: "smooth", block: "nearest" })));
  };

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, pending]);

  const canSend = draft.trim().length > 0 && !pending;

  function submit(e?: FormEvent) {
    e?.preventDefault();
    if (!canSend) return;
    onSend(draft.trim());
    setDraft("");
  }

  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    // Enter sends, Shift+Enter adds a line.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  }

  // A citation opens that answer's inline sources and scrolls to the cited one.
  function openCitation(index: number, href: string) {
    onSelect(index);
    setOpen((o) => new Set(o).add(index));
    requestAnimationFrame(() => requestAnimationFrame(() =>
      document.querySelector(`#c${index}-${href.slice(1)}`)?.scrollIntoView({ behavior: "smooth", block: "center" })));
  }

  return (
    <section className="chat compact">
      <div className="messages">
        {messages.length === 0 && (greeting ?? (
          <p className="muted intro">Ask about LLM security risks, attacks on AI systems, or CVEs in LLM products.</p>
        ))}
        {messages.map((m, i) => (
          <div
            key={i}
            className={`message ${m.role}${m.error ? " error" : ""}${i === selected ? " selected" : ""}`}
            onClick={m.reply ? () => onSelect(i) : undefined}
          >
            {m.error ? (
              <p>{m.error}</p>
            ) : m.role === "assistant" ? (
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{
                  a: ({ href = "", children }) =>
                    href.startsWith("#source-") ? (
                      <a href={href} className="cite" onClick={(e) => { e.preventDefault(); openCitation(i, href); }}>
                        {children}
                      </a>
                    ) : (
                      <a href={href} target="_blank" rel="noreferrer">{children}</a>
                    ),
                }}
              >
                {linkCitations(m.content)}
              </Markdown>
            ) : (
              <p>{m.content}</p>
            )}
            {m.reply?.flags.includes("injection_phrasing") && (
              <p className="flag-note">This message looks like an injection attempt. It was answered, and logged.</p>
            )}
            {m.reply && <UsageLine usage={m.reply.usage} steps={m.reply.steps} />}
            {m.reply && (m.reply.sources.length > 0 || m.reply.tool_calls.length > 0) && (
              <>
                <button type="button" className="details-toggle" aria-expanded={open.has(i)}
                  onClick={(e) => { e.stopPropagation(); toggle(i); }}>
                  {open.has(i) ? "Hide" : "Show"} {m.reply.sources.length} sources · {m.reply.tool_calls.length} tool calls
                </button>
                {open.has(i) && <div id={`c${i}-details`}><ChatDetails reply={m.reply} idPrefix={`c${i}-source-`} /></div>}
              </>
            )}
          </div>
        ))}
        {pending && (
          <div className="message assistant thinking" role="status">
            <span className="spinner" aria-hidden="true" /> Thinking…
          </div>
        )}
        <div ref={endRef} />
      </div>

      {(suggestions.length > 0 || examples.length > 0) && (
        <div className="suggest">
          {suggestions.map((q) => (
            <button key={q} type="button" disabled={pending} onClick={() => onSend(q)}>{q}</button>
          ))}
          {examples.length > 0 && (
            <details className="more-examples">
              <summary>More examples</summary>
              <div className="example-list">
                {examples.map((ex) => (
                  <button key={ex.id} type="button" disabled={pending} onClick={() => onSend(ex.question)}>{ex.question}</button>
                ))}
              </div>
            </details>
          )}
        </div>
      )}

      <form className="composer" onSubmit={submit}>
        <textarea
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask a question…"
          rows={2}
          maxLength={1000}
          aria-label="Message"
        />
        <button type="submit" disabled={!canSend}>Send</button>
      </form>
    </section>
  );
}

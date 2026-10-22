import type { ChatReply, Source } from '../api.ts'
import { EXPLAIN_LEVELS, type ExplainLevel } from '../explainLevels.ts'
import { count } from '../plural.ts'
import { httpHref, proposalAfter, proposalOf } from '../toolCalls.ts'
import type { Proposal } from '../toolResults.ts'
import type { Message, RefinedResult } from './useChat.ts'

// The chat's Export (F147, #147; DESIGN.md §6.2): the conversation on screen as a Markdown file. Built in the browser
// on the click and sent nowhere, like the conversation kept in sessionStorage (§11).

export interface ExportMeta {
  now: Date
  model: string | null // the model in use, when known
  level: ExplainLevel | null // the saved explain level, when known
  showUsage: boolean // the usage line is exported only for those who see it (B49 C1)
  shown?: (p: Proposal) => Proposal // a proposal as its card shows it now (approved or cancelled since the answer)
}

const levelLabel = (id: ExplainLevel) => EXPLAIN_LEVELS.find((lv) => lv.id === id)?.label ?? id

/** "2026-10-22 09:05" in UTC. */
const utcMinute = (d: Date) => d.toISOString().slice(0, 16).replace('T', ' ')

/** patch-chat-YYYY-MM-DD-HHMM.md, by the UTC minute. */
export function exportFileName(now: Date): string {
  return `patch-chat-${utcMinute(now).replace(' ', '-').replace(':', '')}.md`
}

/** An answer as a block quote: what it holds stays inside its turn. */
const quote = (text: string) =>
  text
    .split('\n')
    .map((line) => (line ? `> ${line}` : '>'))
    .join('\n')

/** Plain text inside a line: Markdown's marks are escaped, so a title or question reads as written. */
const plain = (text: string) => text.replace(/[\\`*_[\]<>#|~]/g, '\\$&')

/** A question as the chat shows it: plain text, its lines kept (hard breaks). A line that would start a heading, a
 *  list or a setext underline is escaped too. */
const question = (text: string) =>
  text
    .split('\n')
    .map((line) => plain(line).replace(/^([-+=])/, '\\$1').replace(/^(\d+)([.)])/, '$1\\$2'))
    .join('\\\n')

/** A link when the URL is http or https (a web result's could be anything); else the title as text. */
function link(title: string, url: string): string {
  const href = httpHref(url)
  return href ? `[${plain(title)}](<${href.replace(/[<>\s]/g, encodeURIComponent)}>)` : plain(title)
}

function sourceLine(s: Source): string {
  return `- \\[${s.n}\\] ${link(s.title, s.url)}${s.doc_type === 'web' ? ' · Web result, unverified' : ''}`
}

// Two significant figures: $0.00061, $0.012, $1.2; a free answer shows $0.
const dollars = (cost: number) => `$${Number(cost.toPrecision(2))}`

/** The usage line under an answer (A08, B49 C1), as the chat shows it: "1,234 in · 56 out · 2 LLM calls · …". */
export function usageText(reply: ChatReply): string {
  const u = reply.usage
  return [
    `${u.input_tokens.toLocaleString('en')} in`,
    `${u.output_tokens.toLocaleString('en')} out`,
    count(u.llm_calls, 'LLM call'),
    count(reply.steps, 'step'),
    dollars(u.cost),
  ].join(' · ')
}

/** The tools Patch ran, by name: their arguments and results stay out (the cards' JSON is not the conversation). */
const toolNames = (reply: ChatReply) =>
  reply.tool_calls.map((c) => `\`${c.name}\`${c.status === 'error' ? " (didn't finish)" : ''}`).join(', ')

/** A proposal card (B21, B22) in one line: its state as the card shows it now, its title, before → after. */
function proposalLine(p: Proposal): string {
  const after = proposalAfter(p)
  return `**Proposed change** (${p.state}): ${plain(p.title)}. ${plain(p.before)} → ${plain(after.after)}`
}

function answer(reply: ChatReply, meta: ExportMeta): string[] {
  const blocks = ['**Patch:**', quote(reply.answer)]
  for (const c of reply.tool_calls) {
    const p = proposalOf(c)
    if (p) blocks.push(proposalLine(meta.shown?.(p) ?? p))
  }
  if (reply.sources.length) blocks.push(`Sources:\n\n${reply.sources.map(sourceLine).join('\n')}`)
  if (reply.tool_calls.length) blocks.push(`Tool calls: ${toolNames(reply)}`)
  const facts = [`Explain level: ${levelLabel(reply.explain_level)}`]
  if (meta.showUsage) facts.push(usageText(reply) + (reply.usage.estimated ? ' (estimated)' : ''))
  blocks.push(`*${facts.join(' · ')}*`)
  return blocks
}

/** A refine button's result (B24): the filters applied and the count; no model text. */
function refinedSearch(refined: RefinedResult): string[] {
  const n = (refined.call.result as { sources?: unknown[] } | null)?.sources?.length ?? 0
  return [
    `**Patch:** Searched again with ${plain(refined.applied.join(', '))}: ${count(n, 'source')}.`,
    `Tool calls: \`${refined.call.name}\``,
  ]
}

/** The conversation as Markdown: a title line, the date, the model and explain level; then each turn. */
export function chatToMarkdown(messages: Message[], meta: ExportMeta): string {
  const facts = [`Exported ${utcMinute(meta.now)} UTC`]
  if (meta.model) facts.push(`Model: ${meta.model}`)
  if (meta.level) facts.push(`Explain level: ${levelLabel(meta.level)}`)
  const blocks = ['# Chat with Patch', facts.join(' · '), '---']
  for (const m of messages) {
    if (m.role === 'user') blocks.push(`**You:** ${question(m.content)}`)
    else if (m.quiet) blocks.push(`*${plain(m.error ?? '')}*`) // a limit's note (B11)
    else if (m.error) blocks.push(`**Patch:** *Error: ${plain(m.error)}*`)
    else if (m.refined) blocks.push(...refinedSearch(m.refined))
    else if (m.reply) blocks.push(...answer(m.reply, meta))
  }
  return `${blocks.join('\n\n')}\n`
}

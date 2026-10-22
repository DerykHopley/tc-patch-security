// The chat's Export (F147, #147): the conversation on screen as a Markdown file, built in the browser and sent nowhere.
// Run with `npm test`.
import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { ChatReply, Source, ToolCallRecord } from '../api.ts'
import { chatToMarkdown, exportFileName, type ExportMeta } from './exportChat.ts'
import type { Message } from './useChat.ts'

const NOW = new Date('2026-10-22T09:05:00Z')
const META: ExportMeta = { now: NOW, model: 'openai/gpt-5-mini', level: 'normal', showUsage: false }

const reply = (answer: string, more: Partial<ChatReply> = {}): ChatReply => ({
  answer, sources: [], tool_calls: [], query: null, steps: 2, flags: [], bad_citations: [], no_citations: false,
  usage: { input_tokens: 1234, output_tokens: 56, llm_calls: 2, estimated: false, cost: 0.00061 },
  explain_level: 'normal', page_context: {}, dropped_context: [], search_reused: false, ...more,
})
const q = (id: number, content: string): Message => ({ id, role: 'user', content })
const a = (id: number, r: ChatReply): Message => ({ id, role: 'assistant', content: r.answer, reply: r })

test('F147.1 the file is named by the UTC minute: patch-chat-YYYY-MM-DD-HHMM.md', () => {
  assert.equal(exportFileName(NOW), 'patch-chat-2026-10-22-0905.md')
  assert.equal(exportFileName(new Date('2026-01-03T23:59:59.999Z')), 'patch-chat-2026-01-03-2359.md')
})

test('F147.2 a title, the date, the model and explain level; then the question and the answer', () => {
  const md = chatToMarkdown([q(1, 'What is prompt injection?'), a(2, reply('It is when text steers the model.'))], META)
  assert.equal(
    md,
    [
      '# Chat with Patch',
      '',
      'Exported 2026-10-22 09:05 UTC · Model: openai/gpt-5-mini · Explain level: Normal',
      '',
      '---',
      '',
      '**You:** What is prompt injection?',
      '',
      '**Patch:**',
      '',
      '> It is when text steers the model.',
      '',
      '*Explain level: Normal*',
      '',
    ].join('\n'),
  )
})

const source = (n: number, title: string, url: string, more: Partial<Source> = {}): Source => ({
  n, chunk_id: `c${n}`, doc_id: `d${n}`, doc_type: 'owasp_llm', title, section: null, date: null, url, snippet: 'text',
  score: 0.5, product: null, severity: null, cvss: null, kev: null, ...more,
})

test('F147.3 the answer keeps its citations; its sources follow, numbered, with titles and URLs; a web one marked', () => {
  const r = reply('Untrusted text steers the model [1]. A blog shows it [2].', {
    sources: [
      source(1, 'LLM01:2025 Prompt Injection', 'https://genai.owasp.org/llmrisk/llm01-prompt-injection/'),
      source(2, 'A [demo] page', 'https://example.org/post', { doc_type: 'web', site: 'example.org' }),
    ],
  })
  const md = chatToMarkdown([q(1, 'Show me'), a(2, r)], META)
  assert.ok(md.includes('> Untrusted text steers the model [1]. A blog shows it [2].'), md)
  assert.ok(
    md.includes(
      [
        'Sources:',
        '',
        '- \\[1\\] [LLM01:2025 Prompt Injection](<https://genai.owasp.org/llmrisk/llm01-prompt-injection/>)',
        '- \\[2\\] [A \\[demo\\] page](<https://example.org/post>) · Web result, unverified',
      ].join('\n'),
    ),
    md,
  )
})

test('F147.4 a source URL that is not http or https is shown as text, never as a link', () => {
  const r = reply('See [1].', { sources: [source(1, 'Trap', 'javascript:alert(1)', { doc_type: 'web' })] })
  const md = chatToMarkdown([q(1, 'Q'), a(2, r)], META)
  assert.ok(md.includes('- \\[1\\] Trap · Web result, unverified'), md)
  assert.ok(!md.includes('javascript:'), md)
})

const call = (name: string, result: unknown, status: 'ok' | 'error' = 'ok') =>
  ({ id: `t-${name}`, name, args: { id: 'CVE-2025-3248' }, result, status, error: null, duration_ms: 5,
    retryable: false }) as unknown as ToolCallRecord

test('F147.5 tool calls by name, not their JSON; the usage line for those who see it', () => {
  const r = reply('Langflow is affected.', {
    tool_calls: [call('lookup_cve', { id: 'CVE-2025-3248', secret: 'raw-json' }), call('research_web', null, 'error')],
  })
  const md = chatToMarkdown([q(1, 'Am I affected?'), a(2, r)], { ...META, showUsage: true })
  assert.ok(md.includes("Tool calls: `lookup_cve`, `research_web` (didn't finish)"), md)
  assert.ok(!md.includes('raw-json'), md)
  assert.ok(md.includes('*Explain level: Normal · 1,234 in · 56 out · 2 LLM calls · 2 steps · $0.00061*'), md)
  const viewer = chatToMarkdown([q(1, 'Am I affected?'), a(2, r)], META)
  assert.ok(!viewer.includes('1,234 in'), viewer)
})

const proposal = {
  proposal_id: 'p1', action: 'watch', title: 'Watch Langflow', why: null, before: 'Not watched', after: 'Watched',
  fields: { status: null }, state: 'proposed',
}

test('F147.6 a proposal: its summary and the state shown on its card (proposed, approved, cancelled)', () => {
  const r = reply('I can add it.', { tool_calls: [call('update_watchlist', proposal)] })
  const ms = [q(1, 'Watch Langflow'), a(2, r)]
  const asSent = chatToMarkdown(ms, META)
  assert.ok(asSent.includes('**Proposed change** (proposed): Watch Langflow. Not watched → Watched'), asSent)
  for (const state of ['approved', 'cancelled'] as const) {
    const shown = chatToMarkdown(ms, { ...META, shown: (p) => ({ ...p, state }) })
    assert.ok(shown.includes(`**Proposed change** (${state}): Watch Langflow.`), shown)
  }
})

test('F147.7 a failed request, a limit note and a refined search are kept as the chat shows them', () => {
  const ms: Message[] = [
    q(1, 'First'),
    { id: 2, role: 'assistant', content: '', error: 'The server did not answer. Try again.' },
    q(3, 'Second'),
    a(4, reply('An answer.')),
    {
      id: 5, role: 'assistant', content: '',
      refined: { applied: ['High or worse'], call: call('search_cves', { sources: [1, 2] }), filters: [], page: {} },
    } as unknown as Message,
    { id: 6, role: 'assistant', content: '', error: 'Try again at 09:01 UTC.', quiet: true },
  ]
  const md = chatToMarkdown(ms, META)
  assert.ok(md.includes('**You:** First\n\n**Patch:** *Error: The server did not answer. Try again.*'), md)
  assert.ok(md.includes('**Patch:** Searched again with High or worse: 2 sources.\n\nTool calls: `search_cves`'), md)
  assert.ok(md.endsWith('*Try again at 09:01 UTC.*\n'), md)
})

test('F147.8 a heading or an unclosed fence in an answer stays inside its turn', () => {
  const r = reply('# Fix it now\n\nRun:\n\n```bash\npip install -U langflow\n\nNo closing fence.')
  const md = chatToMarkdown([q(1, 'How?'), a(2, r), q(3, 'Thanks')], META)
  assert.ok(
    md.includes('> # Fix it now\n>\n> Run:\n>\n> ```bash\n> pip install -U langflow\n>\n> No closing fence.\n\n'),
    md,
  )
  assert.ok(md.includes('\n\n**You:** Thanks\n'), md) // outside the quote: a quoted fence ends with the quote
  assert.ok(!/^#(?! Chat with Patch)/m.test(md), md) // the title is the file's only heading
})

test('F147.9 a question is plain text, as the chat shows it: its marks and line breaks kept, never Markdown', () => {
  const md = chatToMarkdown([q(1, 'Is `eval` *bad*?\n# not a heading\n===\n1. not a list\n- nor this')], META)
  assert.ok(
    md.includes('**You:** Is \\`eval\\` \\*bad\\*?\\\n\\# not a heading\\\n\\===\\\n1\\. not a list\\\n\\- nor this\n'),
    md,
  )
})

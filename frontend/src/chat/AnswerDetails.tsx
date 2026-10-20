import { useId, type KeyboardEvent } from 'react'
import type { ChatReply, DocType, QueryInfo, Source } from '../api.ts'
import { ExternalLink } from '../components/ExternalLink.tsx'
import { SeverityBadge } from '../components/SeverityBadge.tsx'
import { ToolCallCard, WebFacts } from './ToolCallCard.tsx'

export type DetailTab = 'sources' | 'tools' | 'query'

const DOC_LABEL: Record<DocType, string> = {
  owasp_llm: 'OWASP LLM Top 10',
  owasp_web: 'OWASP Top 10',
  atlas_technique: 'ATLAS technique',
  atlas_mitigation: 'ATLAS mitigation',
  atlas_case: 'ATLAS case study',
  cve: 'CVE',
  web: 'Web result, unverified',
}

/** The tab an answer's details open on: sources if it has any, else tool calls, else the query plan. */
export function firstTab(reply: ChatReply): DetailTab {
  return reply.sources.length ? 'sources' : reply.tool_calls.length ? 'tools' : 'query'
}

export const sourceId = (prefix: string, n: number) => `${prefix}-source-${n}`

function Sources({ sources, prefix }: { sources: Source[]; prefix: string }) {
  if (sources.length === 0) return <p className="meta">No sources for this answer.</p>
  return (
    <ol className="sources">
      {sources.map((s) => (
        <li key={s.chunk_id} id={sourceId(prefix, s.n)} className="source" data-n={s.n}>
          <div className="source-head">
            <span className="source-n">{s.n}</span>
            <ExternalLink href={s.url}>{s.title}</ExternalLink>
          </div>
          {s.doc_type === 'web' ? (
            <WebFacts site={s.site} date={s.date} flagged={!!s.flags?.includes('injection_phrasing')} />
          ) : (
            <div className="meta">
              {DOC_LABEL[s.doc_type]}
              {s.section && <> · {s.section}</>}
              {s.date && <> · {s.date}</>}
              {s.score !== null && <> · score {s.score.toFixed(3)}</>}
            </div>
          )}
          {s.doc_type === 'cve' && (
            <div className="chips">
              <SeverityBadge severity={s.severity} cvss={s.cvss} />
              {s.kev && <span className="chip kev">CISA KEV</span>}
            </div>
          )}
          <p className="snippet">{s.snippet}</p>
        </li>
      ))}
    </ol>
  )
}

function QueryPlan({ query }: { query: QueryInfo }) {
  const filters = Object.entries(query.filters)
  const foundBy = Object.entries(query.found_by ?? {}) // which retriever (keyword, vector) found each source
  return (
    <div className="query-plan">
      <dl>
        <dt>Semantic query</dt>
        <dd>{query.semantic_query}</dd>
        <dt>Rewrites</dt>
        <dd>
          {query.rewrites.length === 0 ? (
            <span className="meta">none</span>
          ) : (
            <ul className="rewrites">
              {query.rewrites.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          )}
        </dd>
        <dt>Filters</dt>
        <dd>
          {filters.length === 0 ? (
            <span className="meta">none</span>
          ) : (
            filters.map(([k, v]) => (
              <span key={k} className="chip">
                {k}: {v}
              </span>
            ))
          )}
        </dd>
        {query.dropped_filters.length > 0 && (
          <>
            <dt>Dropped filters</dt>
            <dd>
              {query.dropped_filters.map((f) => (
                <span key={f} className="chip warn">
                  {f}
                </span>
              ))}
            </dd>
          </>
        )}
        {foundBy.length > 0 && (
          <>
            <dt>Found by</dt>
            <dd>
              {foundBy.map(([n, by]) => (
                <span key={n} className="chip">
                  [{n}] {by.join(' + ')}
                </span>
              ))}
            </dd>
          </>
        )}
      </dl>
      {query.relaxed && <p className="notice">Relaxed: the filters left no results, so search ran again without them.</p>}
    </div>
  )
}

// An answer's sources, tool calls and query plan as tabs, inline under the answer (DESIGN.md §6.2).
// Arrow keys move between tabs, as the ARIA tabs pattern expects.
export function AnswerDetails({ reply, prefix, tab, onTab }: {
  reply: ChatReply
  prefix: string
  tab: DetailTab
  onTab: (tab: DetailTab) => void
}) {
  const id = useId()
  const tabs: { id: DetailTab; label: string; n?: number }[] = [
    { id: 'sources' as const, label: 'Sources', n: reply.sources.length },
    ...(reply.tool_calls.length ? [{ id: 'tools' as const, label: 'Tool calls', n: reply.tool_calls.length }] : []),
    ...(reply.query ? [{ id: 'query' as const, label: 'Query plan' }] : []),
  ]

  function onKeyDown(e: KeyboardEvent) {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return
    const i = tabs.findIndex((t) => t.id === tab)
    const next = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]
    onTab(next.id)
    document.getElementById(`${id}-${next.id}`)?.focus()
  }

  return (
    <div className="answer-details">
      <div className="detail-tabs" role="tablist" aria-label="Answer details">
        {tabs.map((t) => (
          <button
            key={t.id}
            id={`${id}-${t.id}`}
            type="button"
            role="tab"
            aria-selected={tab === t.id}
            aria-controls={`${id}-panel`}
            tabIndex={tab === t.id ? 0 : -1}
            onClick={() => onTab(t.id)}
            onKeyDown={onKeyDown}
          >
            {t.label}
            {t.n !== undefined && <span className="count"> {t.n}</span>}
          </button>
        ))}
      </div>
      <div id={`${id}-panel`} role="tabpanel" aria-labelledby={`${id}-${tab}`}>
        {tab === 'sources' && <Sources sources={reply.sources} prefix={prefix} />}
        {tab === 'tools' && reply.tool_calls.map((c) => <ToolCallCard key={c.id} call={c} page={reply.page_context} />)}
        {tab === 'query' && reply.query && <QueryPlan query={reply.query} />}
      </div>
    </div>
  )
}

import type { ReactNode } from 'react'
import type { Severity, ToolCallRecord } from '../api.ts'
import { SeverityBadge } from './SeverityBadge.tsx'

// One card per tool call: name, arguments, status, time, and the result drawn for its tool. Errors in red.
// Result shapes come from backend/app/tools/*.py.

interface CveResult {
  id: string
  product: string
  published: string
  severity: Severity | null
  cvss: number | null
  cwes: string[]
  owasp: { code: string; title: string; url: string } | null
  url: string
  kev: { date_added: string; due: string } | null
  watch_status: 'open' | 'fixed' | 'not_affected' | 'not_watched'
}

interface WeaknessResult {
  kind: 'cwe' | 'atlas_technique'
  id: string
  url: string
  name?: string
  category?: { code: string; title: string; url: string } | null
  cves_in_snapshot?: number
  tactics?: string[]
  maturity?: string
  mitigations?: { id: string; name: string }[]
  cited_by_llm_top10?: { code: string; title: string }[]
}

interface WatchlistResult {
  message: string
  watchlist: string[]
}

const STATUS_LABEL = { open: 'Open', fixed: 'Fixed', not_affected: 'Not affected', not_watched: 'Not watched' }

const External = ({ href, children }: { href: string; children: ReactNode }) => (
  <a href={href} target="_blank" rel="noreferrer">
    {children}
  </a>
)

function CveCard({ r }: { r: CveResult }) {
  return (
    <div className="result-card cve-card">
      <p className="result-title">
        <External href={r.url}>{r.id}</External> · {r.product}
      </p>
      <div className="chips">
        <SeverityBadge severity={r.severity} cvss={r.cvss} />
        {r.kev && <span className="chip kev">CISA KEV · due {r.kev.due}</span>}
        <span className="chip">{STATUS_LABEL[r.watch_status]}</span>
      </div>
      <p className="meta">
        Published {r.published} · {r.cwes.join(', ') || 'no CWE'}
        {r.owasp && (
          <>
            {' · '}
            <External href={r.owasp.url}>{r.owasp.title}</External>
          </>
        )}
      </p>
    </div>
  )
}

function WeaknessCard({ r }: { r: WeaknessResult }) {
  if (r.kind === 'cwe') {
    return (
      <div className="result-card weakness-card">
        <p className="result-title">
          <External href={r.url}>{r.id}</External>
        </p>
        <p className="meta">
          {r.category ? (
            <>
              OWASP 2025: <External href={r.category.url}>{r.category.title}</External>
            </>
          ) : (
            'Not in any OWASP Top 10 2025 category'
          )}
          {' · '}
          {r.cves_in_snapshot} CVEs in the snapshot
        </p>
      </div>
    )
  }
  return (
    <div className="result-card weakness-card">
      <p className="result-title">
        <External href={r.url}>
          {r.id} {r.name}
        </External>
      </p>
      <p className="meta">
        {r.tactics?.join(', ')} · {r.maturity}
      </p>
      {!!r.cited_by_llm_top10?.length && (
        <p className="meta">Cited by: {r.cited_by_llm_top10.map((c) => c.title).join(', ')}</p>
      )}
      {!!r.mitigations?.length && (
        <ul className="mitigations">
          {r.mitigations.map((m) => (
            <li key={m.id}>
              {m.id} {m.name}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function WatchlistCard({ r }: { r: WatchlistResult }) {
  return (
    <div className="result-card watchlist-card">
      <p className="result-title">{r.message}</p>
      <p className="meta">Watching: {r.watchlist.join(', ') || 'nothing'}</p>
    </div>
  )
}

export function ToolCallCard({ call }: { call: ToolCallRecord }) {
  const r = call.result
  let body = null
  if (r && call.name === 'lookup_cve') body = <CveCard r={r as unknown as CveResult} />
  else if (r && call.name === 'explain_weakness') body = <WeaknessCard r={r as unknown as WeaknessResult} />
  else if (r && call.name === 'update_watchlist') body = <WatchlistCard r={r as unknown as WatchlistResult} />
  return (
    <article className={`tool-card ${call.status}`}>
      <header>
        <code>{call.name}</code>
        <span className={`status ${call.status}`}>{call.status === 'ok' ? 'OK' : 'Error'}</span>
        <span className="meta">{call.duration_ms.toFixed(1)} ms</span>
      </header>
      <pre className="args">{JSON.stringify(call.args, null, 2)}</pre>
      {call.error && (
        <p className="tool-error">
          <strong>{call.error.code}</strong>: {call.error.message}
        </p>
      )}
      {body}
      {r && (
        <details className="raw">
          <summary>Raw result</summary>
          <pre>{JSON.stringify(r, null, 2)}</pre>
        </details>
      )}
    </article>
  )
}

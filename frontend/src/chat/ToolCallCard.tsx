import type { ReactNode } from 'react'
import type { Decision, Epss, PageContext, PriorityLevel, Severity, ToolCallRecord, Verdict, WhoActs } from '../api.ts'
import { contextWords } from '../pageContext.ts'
import { OverdueMark, PriorityChip } from '../components/Priority.tsx'
import { NoFixMark, STATUS_LABEL as CVE_STATUS_LABEL } from '../components/Decision.tsx'
import { epssPercentile, epssScore, PossibleMatch } from '../components/SnapshotFacts.tsx'
import { VERDICT_LABEL, VerdictChip, VerdictFacts } from '../components/Verdict.tsx'
import { SeverityBadge } from '../components/SeverityBadge.tsx'

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
  kev: { date_added: string; deadline: string } | null
  watch_status: 'open' | 'fixed' | 'not_affected' | 'accepted' | 'not_watched'
  no_fix: boolean // A16b: no fixed version in OSV, so not overdue
  decision: Decision | null
  review_due: boolean
  open_days: number
  epss: Epss | null
  possible_match: boolean
  verdict: Verdict
  verdict_reason: string
  fixed_version: string | null
  who_acts: WhoActs
  priority: {
    level: PriorityLevel
    reasons: string[]
    due_date: string
    due_from: string
    overdue: boolean
    alert_priority: number
  } | null // A16; null off the watchlist
}

// check_affected (A15): one CVE's verdict, or a product's open CVEs by verdict.
interface AffectedOne {
  id: string
  product: string
  severity: Severity | null
  verdict: Verdict
  reason: string
  fixed_version: string | null
  who_acts: WhoActs
  usage: string
  version: string | null
  possible_match: boolean
}

interface AffectedProduct {
  product: string
  usage: string
  version: string | null
  open: number
  counts: Record<Verdict, number>
  cves: { id: string; severity: Severity | null; verdict: Verdict; reason: string; fixed_version: string | null }[]
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

// prioritise (A18): the rules' order for the watchlist and the page's view. Drawn in that order, never re-sorted.
interface FixFirstCve {
  rank: number
  n: number
  id: string
  product: string
  severity: Severity | null
  kev: boolean
  verdict: Verdict
  status: 'open' | 'accepted'
  review_due: boolean
  priority: PriorityLevel
  reasons: string[]
  due_date: string
  due_from: string
  overdue: boolean
  no_fix: boolean
  open_days: number
}

interface FixFirstResult {
  filters: Record<string, string | boolean>
  ignored: string[]
  product: string | null
  total_open: number
  cves: FixFirstCve[]
}

interface WatchlistResult {
  message: string
  watchlist: string[]
}

const STATUS_LABEL = { ...CVE_STATUS_LABEL, not_watched: 'Not watched' }

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
        {r.kev && <span className="chip kev">CISA KEV · KEV deadline {r.kev.deadline}</span>}
        {r.priority && <PriorityChip level={r.priority.level} />}
        <span className="chip">
          {STATUS_LABEL[r.watch_status]}
          {r.review_due ? ' · review due' : ''}
        </span>
        {r.possible_match && <PossibleMatch />}
        {r.verdict && <VerdictChip verdict={r.verdict} />}
      </div>
      {r.priority && (
        <p className="meta">
          Priority: {r.priority.reasons.join(' · ')} · {r.no_fix ? 'decide by' : 'due'} {r.priority.due_date}{' '}
          ({r.priority.due_from})
          {r.priority.overdue && <OverdueMark />}
          {r.no_fix && r.watch_status === 'open' && <NoFixMark days={r.open_days} />}
        </p>
      )}
      {r.watch_status === 'accepted' && r.decision?.reason && (
        <p className="meta">
          Accepted: {r.decision.reason}
          {r.decision.review_date ? ` · review ${r.decision.review_date}` : ''}
        </p>
      )}
      {r.verdict_reason && <p className="meta">Verdict: {r.verdict_reason}</p>}
      {r.epss && (
        <p className="meta">
          EPSS {epssScore(r.epss)} · {epssPercentile(r.epss)} · EPSS by FIRST, {r.epss.date}
        </p>
      )}
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

function AffectedCard({ r }: { r: AffectedOne | AffectedProduct }) {
  if ('counts' in r) {
    return (
      <div className="result-card affected-card">
        <p className="result-title">
          {r.product} · {r.usage} · {r.version ? `version ${r.version}` : 'no version given'}
        </p>
        <p className="meta">
          {r.open} open: {(['affected', 'unknown', 'not_affected'] as Verdict[])
            .map((v) => `${r.counts[v]} ${VERDICT_LABEL[v].toLowerCase()}`)
            .join(', ')}
        </p>
        <ul className="affected-list">
          {r.cves.map((c) => (
            <li key={c.id}>
              {c.id} <VerdictChip verdict={c.verdict} /> <span className="meta">{c.reason}</span>
            </li>
          ))}
        </ul>
      </div>
    )
  }
  return (
    <div className="result-card affected-card">
      <p className="result-title">
        {r.id} · {r.product} · {r.usage}
        {r.version ? ` ${r.version}` : ''}
      </p>
      <div className="chips">
        <VerdictChip verdict={r.verdict} />
        <SeverityBadge severity={r.severity} cvss={null} />
        {r.possible_match && <PossibleMatch />}
      </div>
      <p className="meta verdict-lines">
        <VerdictFacts reason={r.reason} fixed={r.fixed_version} who={r.who_acts} />
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

function FixFirstCard({ r }: { r: FixFirstResult }) {
  const view = contextWords(r.filters as PageContext, r.product ?? undefined).join(', ')
  return (
    <div className="result-card fix-first-card">
      <p className="result-title">
        {r.total_open} open{view ? ` · ${view}` : ' on your watchlist'} · in the rules' order
      </p>
      {r.ignored.map((i) => (
        <p key={i} className="meta">
          Not applied: {i}
        </p>
      ))}
      {r.cves.length === 0 ? (
        <p className="meta">Nothing open in this view.</p>
      ) : (
        <ol className="fix-list">
          {r.cves.map((c) => (
            <li key={c.id}>
              <span className="fix-head">
                <strong>{c.id}</strong>
                <PriorityChip level={c.priority} />
                <SeverityBadge severity={c.severity} cvss={null} />
                {c.kev && <span className="chip kev">KEV</span>}
                {c.review_due && <span className="chip review-due">Review due</span>}
                {c.no_fix && <NoFixMark days={c.open_days} />}
                {c.overdue && <OverdueMark />}
              </span>
              <span className="meta">
                {c.product} · {c.reasons.join(' · ')} · {c.no_fix ? 'decide by' : 'due'} {c.due_date} ({c.due_from})
              </span>
            </li>
          ))}
        </ol>
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
  else if (r && call.name === 'check_affected') body = <AffectedCard r={r as unknown as AffectedOne | AffectedProduct} />
  else if (r && call.name === 'prioritise') body = <FixFirstCard r={r as unknown as FixFirstResult} />
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

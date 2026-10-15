import { useState, type ReactNode } from 'react'
import { retryTool, type PageContext, type ToolCallRecord, type Verdict } from '../api.ts'
import { contextWords, STATUS_LABEL as CVE_STATUS_LABEL } from '../cveView.ts'
import { OverdueMark, PriorityChip } from '../components/Priority.tsx'
import { NoFixMark } from '../components/Decision.tsx'
import { epssPercentile, epssScore, PossibleMatch } from '../components/SnapshotFacts.tsx'
import { VERDICT_LABEL, VerdictChip, VerdictFacts } from '../components/Verdict.tsx'
import { SeverityBadge } from '../components/SeverityBadge.tsx'
import type {
  AffectedOne,
  AffectedProduct,
  CveResult,
  CweResult,
  FixFirstResult,
  Proposal,
  ResearchResult,
  TechniqueResult,
  UpdatesResult,
  WatchlistResult,
} from '../toolResults.ts'
import { utcTime } from '../freshness.ts'
import { scheduleLine } from '../refreshRuns.ts'
import { followLink, openPath } from '../route.ts'

// One card per tool call: name, arguments, status, time, and the result drawn for its tool. Errors in red.
// Result types come from the tools' declared result models (toolResults.ts, generated from backend/app/tools/).

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

function WeaknessCard({ r }: { r: CweResult | TechniqueResult }) {
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
  const view = contextWords(r.filters, r.product ?? undefined).join(', ')
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

function WatchlistCard({ r }: { r: WatchlistResult | Proposal }) {
  if ('proposal_id' in r) {
    return (
      <div className="result-card watchlist-card">
        <p className="result-title">Proposed: {r.title}</p>
        <p className="meta">
          {r.before} → {r.after} · approve, edit or cancel it in the card under the answer
        </p>
      </div>
    )
  }
  return (
    <div className="result-card watchlist-card">
      <p className="result-title">{r.message}</p>
      <p className="meta">Watching: {r.watchlist.join(', ') || 'nothing'}</p>
    </div>
  )
}

/** A web result's facts (B08), on its source and in research_web's card: always "Web result, unverified", the site,
 *  the date when Tavily gives one, and "Flagged" when the page tries to give instructions. */
export function WebFacts({ site, date, flagged }: { site?: string | null; date: string | null; flagged: boolean }) {
  return (
    <div className="chips web-facts">
      <span className="chip web-unverified">Web result, unverified</span>
      {flagged && (
        <span className="chip web-flagged" title="This page's text tries to give instructions. Patch ignores them.">
          Flagged: instructions ignored
        </span>
      )}
      <span className="meta">
        {site}
        {date ? ` · ${date}` : ' · no date given'}
      </span>
    </div>
  )
}

const VIA = {
  mcp: "Tavily's MCP server",
  api: "Tavily's search API (the MCP server didn't answer)",
  canned: "the model check's saved web results",
}

function ResearchCard({ r }: { r: ResearchResult }) {
  return (
    <div className="result-card research-card">
      <p className="result-title">Web search: “{r.query}”</p>
      <p className="meta">
        {r.results.length} {r.results.length === 1 ? 'result' : 'results'} · via {VIA[r.via]}
        {r.flagged > 0 && ` · ${r.flagged} flagged`} · {r.searches_left} searches left today
      </p>
      {r.results.length > 0 && (
        <ol className="web-list">
          {r.results.map((w) => (
            <li key={w.n}>
              <span className="source-n">{w.n}</span>{' '}
              <External href={w.url}>{w.title}</External>
              <WebFacts site={w.site} date={w.date} flagged={w.flagged} />
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

// check_updates' card (B06, DESIGN.md §6.2): when it checked (or why it didn't), the counts, the new CVEs and the
// user's alerts, each with its source number, and a link to the CVEs page filtered to new (B05's `new=1`).
const REASON_LABEL: Record<string, string> = {
  kev: 'Added to CISA KEV',
  kev_recheck: 'In KEV while marked fixed: recheck',
  new: 'New',
  new_unscored: 'New, not scored yet',
  now_critical: 'Now critical',
  due_soon: 'Due soon',
  overdue: 'Overdue',
}

function updatesTitle(r: UpdatesResult): string {
  if (r.mode === 'snapshot') return `A frozen snapshot, as of ${r.as_of}: nothing to check`
  if (!r.last_checked) return 'Not checked yet'
  return `${r.ran ? 'Checked the feeds' : 'Last check'} · ${utcTime(r.last_checked)}`
}

function UpdatesCard({ r }: { r: UpdatesResult }) {
  const c = r.counts
  return (
    <div className="result-card updates-card">
      <p className="result-title">{updatesTitle(r)}</p>
      {r.refusal && r.refusal.reason !== 'snapshot' && <p className="meta">{r.refusal.message}</p>}
      {r.mode === 'live' && <p className="meta updates-schedule">{scheduleLine(r.schedule, r.mode)}</p>}
      {r.ok === false && <p className="tool-error">The check failed, nothing changed: {r.problems.join('; ')}</p>}
      {r.status === 'partial' && <p className="meta">Partial: {r.problems.join('; ')}. The rest was written.</p>}
      {r.ok && (
        <p className="meta">
          {c.new} new · {c.updated} updated · {c.kev_added} added to KEV · {c.rescored} rescored · {r.alerts_total}{' '}
          {r.alerts_total === 1 ? 'alert' : 'alerts'} for you
        </p>
      )}
      {r.new_cves.length > 0 && (
        <>
          <p className="updates-head">New CVEs</p>
          <ul className="updates-list">
            {r.new_cves.map((v) => (
              <li key={v.id}>
                {v.n && <span className="source-n">{v.n}</span>}
                <strong>{v.id}</strong>
                <span className="meta">{v.product}</span>
                <SeverityBadge severity={v.severity} cvss={null} />
                {v.kev && <span className="chip kev">KEV</span>}
                {v.priority ? <PriorityChip level={v.priority} /> : <span className="chip">Not watched</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {r.alerts.length > 0 && (
        <>
          <p className="updates-head">
            Alerts for you{r.alerts_total > r.alerts.length ? ` (first ${r.alerts.length} of ${r.alerts_total})` : ''}
          </p>
          <ul className="updates-list">
            {r.alerts.map((a) => (
              <li key={`${a.cve} ${a.reason}`}>
                {a.n && <span className="source-n">{a.n}</span>}
                <strong>{a.cve}</strong>
                <span className="chip">{REASON_LABEL[a.reason] ?? a.reason}</span>
                {a.held && <span className="meta">held for quiet hours</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {c.new > 0 && r.ok && (
        <p className="meta">
          <a href="/cves?new=1" onClick={(e) => followLink(e, openPath)}>
            See the new CVEs on the CVEs page
          </a>
        </p>
      )}
    </div>
  )
}

function ResultCard({ call }: { call: ToolCallRecord }) {
  // Checking the name narrows the result to that tool's type.
  if (call.name === 'lookup_cve' && call.result) return <CveCard r={call.result} />
  if (call.name === 'explain_weakness' && call.result) return <WeaknessCard r={call.result} />
  if (call.name === 'check_affected' && call.result) return <AffectedCard r={call.result} />
  if (call.name === 'prioritise' && call.result) return <FixFirstCard r={call.result} />
  if (call.name === 'update_watchlist' && call.result) return <WatchlistCard r={call.result} />
  if (call.name === 'propose_decision' && call.result) return <WatchlistCard r={call.result} />
  if (call.name === 'research_web' && call.result) return <ResearchCard r={call.result} />
  if (call.name === 'check_updates' && call.result) return <UpdatesCard r={call.result} />
  return null
}

// B20: a step tried again keeps its new record for the page's lifetime, so switching tabs doesn't lose it.
const retried = new WeakMap<ToolCallRecord, ToolCallRecord>()

/** `page`: the answer's page context, sent again with Try again (prioritise reads it). */
export function ToolCallCard({ call: original, page = {} }: { call: ToolCallRecord; page?: PageContext }) {
  const [call, setCall] = useState(() => retried.get(original) ?? original)
  const [trying, setTrying] = useState(false)
  const [retryError, setRetryError] = useState<string | null>(null)
  const r = call.result
  const again = call !== original // this card shows a step that was tried again

  const tryAgain = () => {
    setTrying(true)
    setRetryError(null)
    retryTool(original, page)
      .then((rec) => {
        retried.set(original, rec)
        setCall(rec)
      })
      .catch((e: unknown) => setRetryError(e instanceof Error ? e.message : 'Something went wrong. Try again.'))
      .finally(() => setTrying(false))
  }

  return (
    <article className={`tool-card ${call.status}`}>
      <header>
        <code>{call.name}</code>
        <span className={`status ${call.status}`}>
          {call.status === 'ok' ? (again ? 'OK on retry' : 'OK') : call.retryable ? "Didn't finish" : 'Error'}
        </span>
        <span className="meta">{call.duration_ms.toFixed(1)} ms</span>
      </header>
      <pre className="args">{JSON.stringify(call.args, null, 2)}</pre>
      {call.error && (
        <p className="tool-error">
          {call.retryable ? "didn't finish: " : <><strong>{call.error.code}</strong>: </>}
          {call.error.message}
        </p>
      )}
      {call.retryable && (
        <div className="try-again-row">
          <button type="button" className="try-again" onClick={tryAgain} disabled={trying} aria-busy={trying}>
            {trying && <span className="spinner" aria-hidden="true" />}
            {trying ? 'Trying again…' : 'Try again'}
          </button>
          <span className="meta">Runs this step only.</span>
        </div>
      )}
      {retryError && (
        <p className="tool-error" role="alert">
          {retryError}
        </p>
      )}
      {again && call.status === 'ok' && (
        <output className="retry-note">
          This step worked on a second try. The answer above was written without it: ask again to have Patch use it.
        </output>
      )}
      <ResultCard call={call} />
      {r && (
        <details className="raw">
          <summary>Raw result</summary>
          <pre>{JSON.stringify(r, null, 2)}</pre>
        </details>
      )}
    </article>
  )
}

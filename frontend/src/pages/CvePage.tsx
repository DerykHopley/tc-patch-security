import { useCallback, useEffect, useState } from 'react'
import { ApiError, cve as fetchCve, markSeen, setStatus, type CveDetail, type DecisionInput } from '../api.ts'
import { CveActions } from '../components/CveActions.tsx'
import { DecisionSummary, HistoryList } from '../components/Decision.tsx'
import { ExternalLink as External } from '../components/ExternalLink.tsx'
import { DueFacts, PriorityChip, PriorityReasons } from '../components/Priority.tsx'
import { SeverityBadge } from '../components/SeverityBadge.tsx'
import { Tip } from '../components/Tip.tsx'
import { EPSS_URL, epssPercentile, epssScore, PossibleMatch } from '../components/SnapshotFacts.tsx'
import { USAGE_LABEL, VerdictChip, VerdictFacts } from '../components/Verdict.tsx'
import { NEW_TITLE, STATUS_LABEL } from '../cveView.ts'
import { marksSeen, rangeWords, showsPriority } from '../cvePage.ts'
import { followLink, openedFromList, PATHS } from '../route.ts'
import { HEADER_TIPS } from '../tips.ts'
import '../styles/cves.css'
import '../styles/cvePage.css'

// The page for one CVE (B35, DESIGN.md §5.15): /cves/CVE-…. Everything Patch knows about it in one place: the full
// summary, the product and its affected versions, the facts, your assessment with the actions, the decision history,
// and the links out to NVD and OSV. Its own page rather than a side panel (the owner's choice, #85): a link can be
// shared, Back works, and alerts and the chat link straight to it.

type Loaded = { detail: CveDetail } | { missing: true } | { error: string } | null

// onAsk: "Ask Patch" opens the chat and asks about this CVE (Patch is told it: the page context, A18).
export function CvePage({ id, asOf, onAsk, onNavigate }: {
  id: string
  asOf: string | null
  onAsk: (cveId: string) => void
  onNavigate: (href: string) => void
}) {
  const [loaded, setLoaded] = useState<Loaded>(null)

  const load = useCallback(
    () =>
      fetchCve(id).then(
        (detail) => {
          setLoaded({ detail })
          // B40: you've seen it now. The chip stays for this visit (it was new when you opened it); the list and a
          // later visit show it as seen. A failed mark is harmless: it stays new, and the next visit tries again.
          if (marksSeen(detail)) markSeen(detail.id).catch(() => {})
        },
        (e: unknown) =>
          setLoaded(e instanceof ApiError && e.status === 404 ? { missing: true } : { error: (e as Error).message }),
      ),
    [id],
  )
  useEffect(() => {
    void load()
  }, [load])

  // Every status change goes through the dialog and becomes a decision record (A16b); its errors show there.
  async function decide(cveId: string, body: DecisionInput) {
    await setStatus(cveId, body)
    await load()
  }

  return (
    <div className="page cve-page">
      <BackLink onNavigate={onNavigate} />
      {loaded === null ? (
        <section className="card cve-head" aria-busy="true">
          <p className="meta">Loading {id}…</p>
        </section>
      ) : 'missing' in loaded ? (
        <section className="card cve-head cve-missing" aria-labelledby="cve-missing-title">
          <h2 id="cve-missing-title">No such CVE</h2>
          <p>
            <strong className="cve-missing-id">{id}</strong> isn't in Patch's data. Check the id, or find the CVE in
            the list.
          </p>
          <p>
            <a href={PATHS.cves} onClick={(e) => followLink(e, onNavigate)}>
              Back to the CVEs list
            </a>
          </p>
        </section>
      ) : 'error' in loaded ? (
        <p className="dash-error" role="alert">
          {loaded.error}{' '}
          <button type="button" onClick={() => void load()}>
            Try again
          </button>
        </p>
      ) : (
        <CveDetails detail={loaded.detail} asOf={asOf} onDecide={decide} onAsk={onAsk} onNavigate={onNavigate} />
      )}
    </div>
  )
}

/** Back to the list. Opened from the list, it steps back in history, so the list keeps its filters, page and scroll
 *  (as the browser's Back does); opened from anywhere else (an alert, the chat, a shared link), it opens the list. */
function BackLink({ onNavigate }: { onNavigate: (href: string) => void }) {
  return (
    <a
      className="cve-back"
      href={PATHS.cves}
      onClick={(e) =>
        followLink(e, (href) => {
          if (openedFromList()) history.back()
          else onNavigate(href)
        })
      }
    >
      <span aria-hidden="true">←</span> CVEs on your watchlist
    </a>
  )
}

function CveDetails({ detail: d, asOf, onDecide, onAsk, onNavigate }: {
  detail: CveDetail
  asOf: string | null
  onDecide: (cve: string, body: DecisionInput) => Promise<void>
  onAsk: (cve: string) => void
  onNavigate: (href: string) => void
}) {
  const row = d.row
  return (
    <>
      <section className="card cve-head" aria-labelledby="cve-title">
        <div className="cve-title-row">
          <h2 id="cve-title">{d.id}</h2>
          {d.kev && (
            <Tip text={`In CISA KEV: known exploited. KEV deadline ${d.kev.deadline}`} className="chip kev" plain>
              KEV
            </Tip>
          )}
          {row?.new && (
            <Tip text={NEW_TITLE} className="chip new-chip" plain>
              New
            </Tip>
          )}
          {d.possible_match && <PossibleMatch />}
          {!d.watched && <span className="chip not-watched">Not on your watchlist</span>}
        </div>
        <p className="cve-meta">
          <strong>{d.product_name}</strong>
          <SeverityBadge severity={d.severity} cvss={d.cvss} />
          <span>
            Published <span className="num">{d.published}</span>
          </span>
        </p>
        <p className="cve-description">{d.description}</p>
        <p className="cve-links">
          <External href={d.url}>NVD</External>
          <External href={d.osv_url}>OSV.dev</External>
        </p>
      </section>

      <div className="cve-grid">
        <section className="card cve-assessment" aria-labelledby="cve-assessment-title">
          <h2 id="cve-assessment-title">Your assessment</h2>
          {row ? (
            <>
              <dl className="cve-facts">
                <dt>Status</dt>
                <dd>
                  <span className="status">
                    {STATUS_LABEL[row.status]}
                    {row.review_due && <span className="chip review-due">Review due</span>}
                  </span>
                  <DecisionSummary row={row} />
                </dd>
                <dt>Verdict</dt>
                <dd className="verdict-cell">
                  <VerdictChip verdict={row.verdict} />
                  <VerdictFacts reason={row.verdict_reason} fixed={row.fixed_version} who={row.who_acts} />
                </dd>
                {showsPriority(row) && (
                  <>
                    <dt>Priority</dt>
                    <dd>
                      <PriorityChip level={row.priority} />
                      <PriorityReasons reasons={row.priority_reasons} />
                    </dd>
                    <dt>Due</dt>
                    <dd className="due-facts">
                      <DueFacts
                        due={row.due_date}
                        from={row.due_from}
                        overdue={row.overdue}
                        kevDeadline={row.kev_deadline}
                        noFix={row.no_fix && row.open ? { days: row.open_days } : null}
                      />
                    </dd>
                  </>
                )}
              </dl>
              <CveActions row={row} asOf={asOf} onDecide={onDecide} onAsk={onAsk} />
            </>
          ) : (
            <>
              <p>
                {d.product_name} isn't on your watchlist, so this CVE has no status, priority or due date. The version
                check's advice still applies.
              </p>
              <dl className="cve-facts">
                <dt>Verdict</dt>
                <dd className="verdict-cell">
                  <VerdictChip verdict={d.verdict} />
                  <VerdictFacts reason={d.verdict_reason} fixed={d.fixed_version} who={d.who_acts} />
                </dd>
              </dl>
              <div className="actions cve-actions">
                <button type="button" aria-label={`Ask Patch about ${d.id}`} onClick={() => onAsk(d.id)}>
                  Ask Patch
                </button>
              </div>
              <p>
                <a className="see-all" href={PATHS.settings} onClick={(e) => followLink(e, onNavigate)}>
                  Watch {d.product_name} in Settings <span aria-hidden="true">→</span>
                </a>
              </p>
            </>
          )}
        </section>

        <section className="card cve-facts-card" aria-labelledby="cve-facts-title">
          <h2 id="cve-facts-title">Facts</h2>
          <dl className="cve-facts">
            <dt>Severity</dt>
            <dd>
              <SeverityBadge severity={d.severity} cvss={d.cvss} />
            </dd>
            <dt>
              <Tip text={HEADER_TIPS.epss}>EPSS</Tip>
            </dt>
            <dd>
              {d.epss ? (
                <>
                  {epssScore(d.epss)} · {epssPercentile(d.epss)}
                  <span className="cve-fact-note">
                    EPSS by <External href={EPSS_URL}>FIRST</External>, {d.epss.date}
                  </span>
                </>
              ) : (
                'Not scored'
              )}
            </dd>
            <dt>CISA KEV</dt>
            <dd>
              {d.kev ? (
                <>
                  Known exploited, listed {d.kev.date_added}
                  <span className="cve-fact-note">
                    KEV deadline {d.kev.deadline} (CISA's date, not your due date)
                  </span>
                  <span className="cve-fact-note">Required action: {d.kev.required_action}</span>
                  <span className="cve-fact-note">Used in ransomware: {d.kev.ransomware}</span>
                </>
              ) : (
                'Not listed'
              )}
            </dd>
            <dt>OWASP</dt>
            <dd>
              {d.owasp ? (
                <>
                  <External href={d.owasp.url}>{d.owasp.title}</External>
                  {d.owasp.list && <span className="cve-fact-note">{d.owasp.list}</span>}
                </>
              ) : (
                'In no OWASP Top 10 2025 category'
              )}
            </dd>
            <dt>CWE</dt>
            <dd>{d.cwes.length ? d.cwes.join(', ') : 'None given'}</dd>
          </dl>
        </section>

        <section className="card cve-versions" aria-labelledby="cve-versions-title">
          <h2 id="cve-versions-title">Product and versions</h2>
          <dl className="cve-facts">
            <dt>Product</dt>
            <dd>{d.product_name}</dd>
            {d.watched && (
              <>
                <dt>You run</dt>
                <dd>
                  {USAGE_LABEL[d.usage]} · {d.version ? `version ${d.version}` : 'no version given'}
                  {d.internet_facing ? ' · internet-facing' : ''}
                </dd>
              </>
            )}
          </dl>
          {d.affected.length === 0 ? (
            <p>OSV.dev lists no affected versions for {d.product_name}, so the version check can't tell.</p>
          ) : (
            <ul className="cve-packages">
              {d.affected.map((a) => (
                <li key={`${a.ecosystem}/${a.package}/${a.advisory}`}>
                  <strong>{a.package}</strong> <span className="meta">({a.ecosystem})</span>
                  <ul>
                    {a.ranges.map((r, i) => (
                      <li key={i}>{rangeWords(r)}</li>
                    ))}
                  </ul>
                  <span className="cve-fact-note">
                    Advisory <External href={`https://osv.dev/vulnerability/${encodeURIComponent(a.advisory)}`}>
                      {a.advisory}
                    </External>
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>

        {row && (
          <section className="card cve-history" aria-labelledby="cve-history-title">
            <h2 id="cve-history-title">Decision history</h2>
            {row.history.length ? <HistoryList history={row.history} /> : <p>No decisions yet.</p>}
          </section>
        )}
      </div>
    </>
  )
}

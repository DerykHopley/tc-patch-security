import { useState } from 'react'
import { checkNow, setSchedulePaused, type DataStatus, type RefreshResult, type SnapshotSource } from '../api.ts'
import { checkedLine, replyLine, runBanner, type Tone } from '../freshness.ts'
import { followLink } from '../route.ts'
import { announceWatchlistChanged } from '../watchlistEvents.ts'
import '../styles/settings.css' // the card head and its status chip, shared with the Settings cards (§5.2)
import '../styles/runs.css' // B19: "Schedule paused"

// The dashboard's "Data freshness" card (DESIGN.md §5.10, B02): Live or Snapshot, when the live data was last
// checked, Check now (live mode only), and the sources with their licences, attributions and NVD's notice.
// After a check that ran, the dashboard and any CVE list on screen load again (the "data changed" event), so the
// new CVEs and the new last-checked time show at once.
// B20: when the last run was partial or failed, a banner says which sources updated, which didn't, and when Retry may
// run; Retry is Check now again (the server keeps the 5-minute rule, and a refusal shows in the line as usual).
// B19: when the schedule is paused, "Schedule paused" with Resume (saves the setting); a link to the run history.

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

export function FreshnessCard({ data, asOf, sources, onNavigate }: {
  data: DataStatus
  asOf: string
  sources: SnapshotSource[]
  onNavigate: (href: string) => void
}) {
  const [checking, setChecking] = useState(false)
  const [resumed, setResumed] = useState(false)
  const [resuming, setResuming] = useState(false)
  const [line, setLine] = useState<{ tone: Tone; text: string } | null>(null)
  const [latest, setLatest] = useState<RefreshResult | null | undefined>(undefined) // this page's last run, if any
  const live = data.mode === 'live'
  const banner = live ? runBanner(latest !== undefined ? latest : data.last_result) : null
  const paused = live && !!data.schedule?.paused && !resumed

  const resume = () => {
    setResuming(true)
    setSchedulePaused(false)
      .then((saved) => {
        setResumed(true)
        const h = saved.alerts.schedule_hours
        setLine({ tone: 'ok', text: `Schedule resumed: a check every ${h === 1 ? 'hour' : `${h} hours`}.` })
      })
      .catch((e: unknown) => setLine({ tone: 'error', text: `Not resumed: ${message(e)}` }))
      .finally(() => setResuming(false))
  }

  const check = () => {
    setChecking(true)
    setLine(null)
    checkNow()
      .then((reply) => {
        setLine(replyLine(reply))
        if (reply.ran) setLatest(reply.result)
        if (reply.ran && reply.result?.ok) announceWatchlistChanged() // ok: a version was written (partial too)
      })
      .catch((e: unknown) => setLine({ tone: 'error', text: message(e) }))
      .finally(() => setChecking(false))
  }

  return (
    <section className="card freshness" aria-labelledby="freshness-title">
      <div className="card-head">
        <h2 id="freshness-title">Data freshness</h2>
        <span
          className={`status-chip ${live ? 'live' : 'mock'}`}
          title={live ? 'Live data: Check now refreshes it from the feeds.' : 'A frozen snapshot: it never changes.'}
        >
          {live ? 'Live' : 'Snapshot'}
        </span>
      </div>
      <p className="meta checked-line">{checkedLine(data, asOf)}</p>
      {banner && (
        <div className={`run-banner ${banner.tone}`}>
          <p className="run-banner-text">{banner.text}</p>
          <ul className="run-banner-details">
            {banner.details.map((d) => (
              <li key={d}>{d}</li>
            ))}
          </ul>
          <button type="button" className="retry" onClick={check} disabled={checking}>
            Retry
          </button>
        </div>
      )}
      {paused && (
        <div className="schedule-paused">
          <p>Schedule paused</p>
          <button type="button" onClick={resume} disabled={resuming} aria-busy={resuming}>
            {resuming ? 'Resuming…' : 'Resume'}
            <span className="visually-hidden"> the schedule</span>
          </button>
        </div>
      )}
      {live && (
        <div className="check-now-row">
          <button type="button" className="check-now" onClick={check} disabled={checking} aria-busy={checking}>
            {checking && <span className="spinner" aria-hidden="true" />}
            {checking ? 'Checking…' : 'Check now'}
          </button>
        </div>
      )}
      {/* <output> is a status region; it is always in the page, so a screen reader hears the line when it appears. */}
      <output className={`check-line${line ? ` ${line.tone}` : ''}`}>{line?.text}</output>
      {live && (
        <a className="edit-link" href="/settings#schedule" onClick={(e) => followLink(e, onNavigate)}>
          Schedule and refresh runs <span aria-hidden="true">→</span>
        </a>
      )}
      <ul className="side-list">
        {sources.map((s) => (
          <li key={s.id}>
            <a href={s.url} target="_blank" rel="noreferrer">
              {s.name}
            </a>
            <span className="meta">
              {s.count.toLocaleString('en')} items · {s.licence} ·{' '}
              {s.as_of && s.as_of !== s.retrieved ? `as of ${s.as_of}, ` : ''}retrieved {s.retrieved}
            </span>
            <span className="meta attribution">{s.attribution}</span>
            {s.notice && <span className="meta freshness-notice">{s.notice}</span>}
          </li>
        ))}
      </ul>
    </section>
  )
}

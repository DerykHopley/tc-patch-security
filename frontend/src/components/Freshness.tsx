import { useState } from 'react'
import { checkNow, type DataStatus, type SnapshotSource } from '../api.ts'
import { checkedLine, replyLine, type Tone } from '../freshness.ts'
import { announceWatchlistChanged } from '../watchlistEvents.ts'
import '../styles/settings.css' // the card head and its status chip, shared with the Settings cards (§5.2)

// The dashboard's "Data freshness" card (DESIGN.md §5.10, B02): Live or Snapshot, when the live data was last
// checked, Check now (live mode only), and the sources with their licences, attributions and NVD's notice.
// After a check that ran, the dashboard and any CVE list on screen load again (the "data changed" event), so the
// new CVEs and the new last-checked time show at once.

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

export function FreshnessCard({ data, asOf, sources }: { data: DataStatus; asOf: string; sources: SnapshotSource[] }) {
  const [checking, setChecking] = useState(false)
  const [line, setLine] = useState<{ tone: Tone; text: string } | null>(null)
  const live = data.mode === 'live'

  const check = () => {
    setChecking(true)
    setLine(null)
    checkNow()
      .then((reply) => {
        setLine(replyLine(reply))
        if (reply.ran && reply.result?.ok) announceWatchlistChanged()
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

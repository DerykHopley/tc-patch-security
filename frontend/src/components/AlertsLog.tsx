import { useCallback, useEffect, useState } from 'react'
import { alertsLog, type AlertLogEntry, type DataStatus } from '../api.ts'
import { channelResult, entryReason, noChannels } from '../alertsLog.ts'
import { utcTime } from '../freshness.ts'
import { followLink } from '../route.ts'
import { useWatchlistChanged } from '../watchlistEvents.ts'
import '../styles/settings.css' // .alert-log, shared with the Settings page
import '../styles/alerts.css'

// The alerts log (B04, DESIGN.md §5.11): the dashboard's "Recent alerts" card, and the same list on Settings.
// One entry per message: an alert links to its CVE the way the notification does (`#cve=…`: the banner, with
// "Explain it"); a digest says its counts. Under each, what every channel did: sent, recorded only, not set up, or
// failed with the error, in words, so colour is never the only cue.

/** The list itself. `labelledBy`: the heading that names it ("Recent alerts"). */
export function AlertList({ entries, labelledBy }: { entries: AlertLogEntry[]; labelledBy: string }) {
  return (
    <ul className="alert-log" aria-labelledby={labelledBy}>
      {entries.map((e, i) => (
        <li key={`${e.at}-${i}`}>
          {e.kind === 'alert' && e.cve ? <a href={`#cve=${e.cve}`}>{e.title}</a> : <strong>{e.title}</strong>}
          <span className="meta">
            {entryReason(e)} · {utcTime(e.at)}
          </span>
          {e.kind === 'digest' && <span className="meta">{e.body}</span>}
          <span className="channel-results">
            {e.channels.length === 0 ? (
              <span className="result muted">{noChannels(e)}</span>
            ) : (
              e.channels.map((c) => {
                const r = channelResult(c)
                return (
                  <span key={c.channel} className={`result ${r.tone}`} title={c.error ?? undefined}>
                    {r.text}
                  </span>
                )
              })
            )}
          </span>
        </li>
      ))}
    </ul>
  )
}

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

/** The dashboard's card: the last 20 alerts, loaded again after Check now (the data-changed event). */
export function AlertsCard({ data, onNavigate }: { data: DataStatus; onNavigate: (href: string) => void }) {
  const [entries, setEntries] = useState<AlertLogEntry[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(
    () =>
      alertsLog().then(
        (r) => {
          setEntries(r.alerts)
          setError(null)
        },
        (e: unknown) => setError(message(e)),
      ),
    [],
  )
  useEffect(() => {
    load()
  }, [load])
  useWatchlistChanged(load)

  return (
    <section className="card alerts-card" aria-labelledby="alerts-title">
      <h2 id="alerts-title">Recent alerts</h2>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : entries === null ? (
        <p className="meta">Loading the alerts…</p>
      ) : entries.length === 0 ? (
        <p className="meta">
          No alerts yet.{' '}
          {data.mode === 'live'
            ? 'A check sends them when something on your watchlist needs you.'
            : 'The snapshot never changes, so only test alerts from Settings appear here.'}
        </p>
      ) : (
        <AlertList entries={entries} labelledBy="alerts-title" />
      )}
      <a className="edit-link" href="/settings" onClick={(e) => followLink(e, onNavigate)}>
        Alert settings <span aria-hidden="true">→</span>
      </a>
    </section>
  )
}

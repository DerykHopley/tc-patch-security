import { useCallback, useEffect, useState } from 'react'
import { alertsLog, type AlertLogEntry, type DataStatus } from '../api.ts'
import { alertsLink, channelResult, dashboardAlerts, emptyAlerts, entryReason, noChannels } from '../alertsLog.ts'
import { utcTime } from '../freshness.ts'
import { cvePath, followLink, openPath } from '../route.ts'
import { keepInView } from '../keepInView.ts'
import { useWatchlistChanged } from '../watchlistEvents.ts'
import '../styles/settings.css' // .alert-log, shared with the Settings page
import '../styles/alerts.css'

// The alerts log (B04, DESIGN.md §5.11): the dashboard's "Recent alerts" card, the last 5 real alerts (#144), and the
// full log on Settings (Delivery for the owner, the Alerts card for anyone else).
// One entry per message: an alert links to its CVE's page, as the notification does (B35, `/cves/CVE-…`); a digest
// says its counts. In Delivery, under each, what every channel did: sent, recorded only, not set up, or
// failed with the error, in words, so colour is never the only cue.

/** The list itself. `labelledBy`: the heading that names it. `channels`: each channel's result under each entry (the
 *  owner's Delivery card only, #144: on the dashboard it's housekeeping, and anyone else has no channels). */
export function AlertList({ entries, labelledBy, channels = false }: {
  entries: AlertLogEntry[]
  labelledBy: string
  channels?: boolean
}) {
  return (
    <ul className="alert-log" aria-labelledby={labelledBy}>
      {entries.map((e, i) => (
        <li key={`${e.at}-${i}`}>
          {e.kind === 'alert' && e.cve ? (
            <a href={cvePath(e.cve)} onClick={(ev) => followLink(ev, openPath)}>
              {e.title}
            </a>
          ) : <strong>{e.title}</strong>}
          <span className="meta">
            {entryReason(e)} · {utcTime(e.at)}
          </span>
          {e.kind === 'digest' && <span className="meta">{e.body}</span>}
          {channels && <ChannelResults e={e} />}
        </li>
      ))}
    </ul>
  )
}

/** What each channel did with one entry, in words. */
function ChannelResults({ e }: { e: AlertLogEntry }) {
  return (
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
  )
}

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

/** The dashboard's card: the last 5 real alerts (#144), loaded again after Check now (the data-changed event). */
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
  // B50 (#95): a link to /#recent-alerts (Settings had one until #144; the anchor stays so older links still land):
  // once the list is in, bring the card into view, and keep it there while the cards above it load (B38)
  const loaded = entries !== null
  useEffect(() => {
    if (!loaded || window.location.hash !== '#recent-alerts') return
    return keepInView(document.getElementById('recent-alerts'), () => undefined)
  }, [loaded])
  const owner = data.schedule?.yours !== false // anyone else's alerts are in Patch only (B48, B50)
  const shown = entries && dashboardAlerts(entries)
  const more = alertsLink(owner)

  return (
    <section id="recent-alerts" className="card alerts-card" aria-labelledby="alerts-title">
      <h2 id="alerts-title">Recent alerts</h2>
      {error ? (
        <p className="form-error" role="alert">
          {error}
        </p>
      ) : shown === null ? (
        <p className="meta">Loading the alerts…</p>
      ) : shown.length === 0 ? (
        <p className="meta">{emptyAlerts(data.mode, owner)}</p>
      ) : (
        <AlertList entries={shown} labelledBy="alerts-title" />
      )}
      <a className="edit-link" href={more.href} onClick={(e) => followLink(e, onNavigate)}>
        {more.text} <span aria-hidden="true">→</span>
      </a>
    </section>
  )
}

import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  alertsLog,
  resetState,
  testAlert,
  type AlertLogEntry,
  type AlertSettings,
  type Channel,
  type Severity,
  type TestAlertReply,
} from '../api.ts'
import { SaveBar } from '../components/SaveBar.tsx'
import { useSettings } from '../components/useSettings.ts'
import '../styles/settings.css'

// The Settings page (DESIGN.md §5.7): alert rules saved for spec B's refresh, delivery channels with real test
// sends, the watchlist link, the data and a safe reset. Each card says what it really does today.

type Kind = 'live' | 'saved' | 'mock'
const KIND_LABEL: Record<Kind, string> = { live: 'Live', saved: 'Saved for later', mock: 'Mock' }

function Status({ kind, why }: { kind: Kind; why: string }) {
  return (
    <span className={`status-chip ${kind}`} title={why}>
      {KIND_LABEL[kind]}
    </span>
  )
}

function Card({ title, kind, why, children }: { title: string; kind: Kind; why: string; children: ReactNode }) {
  const id = `card-${title.toLowerCase()}`
  return (
    <section className="card settings-card" aria-labelledby={id}>
      <div className="card-head">
        <h2 id={id}>{title}</h2>
        <Status kind={kind} why={why} />
      </div>
      {children}
    </section>
  )
}

const SEVERITIES: { value: Severity; label: string }[] = [
  { value: 'LOW', label: 'Low' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'HIGH', label: 'High' },
  { value: 'CRITICAL', label: 'Critical' },
]
const SCHEDULES: AlertSettings['schedule_hours'][] = [1, 3, 6, 12, 24]
const CHANNELS: { id: Channel; label: string; what: string }[] = [
  { id: 'desktop', label: 'Desktop notification', what: "Your OS's own notification, on the computer running the app." },
  { id: 'email', label: 'Email', what: 'A plain-text email with a link back to the CVE.' },
  { id: 'ntfy', label: 'Phone push (ntfy)', what: 'A push to the ntfy app on your phone; self-hostable.' },
]

function when(iso: string): string {
  return iso.replace('T', ' ').replace(/(:\d\d)?\+00:00$/, ' UTC')
}

function outcome(e: AlertLogEntry): ReactNode {
  if (e.error_code === 'not_configured') return <span className="log-error">not set up</span>
  if (e.error) return <span className="log-error">failed: {e.error}</span>
  return e.sent ? 'sent' : 'recorded only'
}

export function SettingsPage({ asOf, onOpenDashboard }: { asOf: string | null; onOpenDashboard: () => void }) {
  const s = useSettings()
  const [log, setLog] = useState<AlertLogEntry[]>([])
  const [preview, setPreview] = useState<TestAlertReply | null>(null)
  const [sending, setSending] = useState<Channel | 'preview' | null>(null)
  const [alertError, setAlertError] = useState<string | null>(null)
  const [confirmText, setConfirmText] = useState('')
  const [resetDone, setResetDone] = useState(false)
  const [resetError, setResetError] = useState<string | null>(null)

  const refreshLog = useCallback(
    () =>
      alertsLog().then(
        (r) => setLog(r.alerts),
        () => setLog([]),
      ),
    [],
  )
  useEffect(() => {
    refreshLog()
  }, [refreshLog])

  if (!s.draft || !s.reply) {
    return (
      <div className="page">
        <p className="muted">{s.error ?? 'Loading settings…'}</p>
      </div>
    )
  }
  const a = s.draft.alerts
  const channels = s.reply.channels
  const set = (v: Partial<AlertSettings>) => s.patch('alerts', v)

  async function sendTest(channel: Channel | 'preview') {
    setAlertError(null)
    setSending(channel)
    try {
      setPreview(await testAlert(channel))
    } catch (e) {
      setAlertError((e as Error).message)
    } finally {
      setSending(null)
      await refreshLog()
    }
  }

  async function reset() {
    setResetError(null)
    try {
      await resetState()
    } catch (e) {
      setResetError((e as Error).message)
      return
    }
    setConfirmText('')
    setResetDone(true)
    setPreview(null)
    setAlertError(null)
    setLog([])
    s.reload()
  }

  return (
    <div className="page settings-page">
      <p className="page-intro">Alerts for your watchlist, how they reach you, and the demo data.</p>

      <div className="settings-grid">
        <Card title="Alerts" kind="saved" why="Saved now; the refresh worker (spec B) will read them">
          <p className="meta">The refresh worker will read these. Nothing checks for new CVEs yet.</p>

          <div className="check-row switch-row">
            <input type="checkbox" id="al-enabled" checked={a.enabled} onChange={(e) => set({ enabled: e.target.checked })}
              aria-describedby="al-enabled-why" />
            <label htmlFor="al-enabled">
              <strong>Send alerts</strong>
            </label>
            <span id="al-enabled-why" className="meta">Turn all alerts on or off.</span>
          </div>

          <fieldset disabled={!a.enabled}>
            <legend>Alert me when</legend>
            <label className="check-row">
              <input type="checkbox" checked={a.kev} onChange={(e) => set({ kev: e.target.checked })} />
              <span>
                A CVE on my watchlist is added to CISA KEV <span className="tag urgent">urgent</span>
              </span>
            </label>
            <label className="check-row">
              <input type="checkbox" checked={a.kev_recheck} onChange={(e) => set({ kev_recheck: e.target.checked })} />
              <span>A CVE I marked fixed is added to KEV, so I can check the fix</span>
            </label>
            <div className="check-row">
              <span className="check-spacer" aria-hidden="true" />
              <span>
                A new CVE is published at or above{' '}
                <select aria-label="Minimum severity" value={a.min_severity}
                  onChange={(e) => set({ min_severity: e.target.value as Severity })}>
                  {SEVERITIES.map((v) => (
                    <option key={v.value} value={v.value}>
                      {v.label}
                    </option>
                  ))}
                </select>
              </span>
            </div>
            <label className="check-row">
              <input type="checkbox" checked={a.unscored} onChange={(e) => set({ unscored: e.target.checked })} />
              <span>
                A new CVE has no severity yet <span className="meta inline">NVD often scores days later</span>
              </span>
            </label>
            <label className="check-row">
              <input type="checkbox" checked={a.now_critical} onChange={(e) => set({ now_critical: e.target.checked })} />
              <span>An open CVE is rescored as critical</span>
            </label>
          </fieldset>

          <fieldset disabled={!a.enabled}>
            <legend>Timing</legend>
            <div className="field-row">
              <label htmlFor="al-schedule">Check for new CVEs every</label>
              <select id="al-schedule" value={a.schedule_hours}
                onChange={(e) => set({ schedule_hours: Number(e.target.value) as AlertSettings['schedule_hours'] })}>
                {SCHEDULES.map((h) => (
                  <option key={h} value={h}>
                    {h === 1 ? 'hour' : `${h} hours`}
                  </option>
                ))}
              </select>
            </div>
            <div className="field-row">
              <label htmlFor="al-digest">Bundle into one digest above</label>
              <input id="al-digest" type="number" min={1} max={50} value={a.digest_over}
                onChange={(e) => set({ digest_over: Math.max(1, Math.min(50, Math.round(Number(e.target.value)) || 1)) })} />
              <span className="meta inline">alerts per check</span>
            </div>
            <div className="field-row">
              <span id="al-quiet">Quiet hours</span>
              <input type="time" aria-label="Quiet hours start" value={a.quiet_start ?? ''}
                onChange={(e) => set({ quiet_start: e.target.value || null })} />
              <span className="meta inline">to</span>
              <input type="time" aria-label="Quiet hours end" value={a.quiet_end ?? ''}
                onChange={(e) => set({ quiet_end: e.target.value || null })} />
              {(a.quiet_start || a.quiet_end) && (
                <button type="button" className="link-btn" onClick={() => set({ quiet_start: null, quiet_end: null })}>
                  Clear<span className="visually-hidden"> quiet hours</span>
                </button>
              )}
            </div>
            <p className="meta">KEV alerts still come through in quiet hours.</p>
          </fieldset>
        </Card>

        <Card title="Delivery" kind="live" why="Test alerts are really sent">
          <p className="meta">
            Pick where alerts go. Connection details and secrets live in <code>backend/.env</code>, never here.
          </p>
          <ul className="channels">
            {CHANNELS.map((c) => {
              const st = channels[c.id]
              return (
                <li key={c.id} className={`channel${st.configured ? '' : ' unconfigured'}`}>
                  <input type="checkbox" id={`ch-${c.id}`} checked={a.channels.includes(c.id)}
                    aria-describedby={`ch-${c.id}-what ch-${c.id}-detail`}
                    onChange={(e) =>
                      set({ channels: e.target.checked ? [...a.channels, c.id] : a.channels.filter((x) => x !== c.id) })
                    } />
                  <div className="channel-text">
                    <label htmlFor={`ch-${c.id}`}>
                      <strong>{c.label}</strong>
                    </label>
                    <span className={`setup-pill${st.configured ? ' ready' : ''}`}>{st.configured ? 'ready' : 'not set up'}</span>
                    <span id={`ch-${c.id}-what`} className="meta">{c.what}</span>
                    <span id={`ch-${c.id}-detail`} className="meta">{st.detail}</span>
                  </div>
                  <button type="button" disabled={sending !== null} onClick={() => sendTest(c.id)}>
                    {sending === c.id ? 'Sending…' : 'Send test'}
                    <span className="visually-hidden"> alert by {c.label.toLowerCase()}</span>
                  </button>
                </li>
              )
            })}
          </ul>
          <div className="callout">
            <strong>Keep the ntfy topic secret.</strong> ntfy's docs say a topic name is "essentially a password", and your
            alerts show which products you run. No alert ever includes the CVE description.
          </div>
          <button type="button" onClick={() => sendTest('preview')} disabled={sending !== null}>
            Preview an alert (send nothing)
          </button>
          {alertError && (
            <p role="alert" className="form-error">
              {alertError}
            </p>
          )}
          {preview && (
            <div className="push-preview" aria-live="polite">
              <div className="push">
                <div className="push-app">
                  <span>{preview.channel} · LLM security</span>
                  <span>priority {preview.alert.priority}</span>
                </div>
                <strong>{preview.alert.title}</strong>
                <span>{preview.alert.body}</span>
              </div>
              <p className="meta">{preview.note} Built from fields only, never the CVE description.</p>
            </div>
          )}

          <h3 id="recent-alerts">Recent alerts</h3>
          {log.length === 0 ? (
            <p className="meta">No alerts yet.</p>
          ) : (
            <ul className="alert-log" aria-labelledby="recent-alerts">
              {log.map((e, i) => (
                <li key={`${e.at}-${i}`}>
                  <span>{e.title}</span>
                  <span className="meta">
                    {e.channel} · {when(e.at)} · {outcome(e)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Card>

        <Card title="Watchlist" kind="live" why="Alerts and the dashboard both use it">
          <p className="meta">Which products count as yours. Alerts and the dashboard both use it.</p>
          <button type="button" onClick={onOpenDashboard}>
            Edit on the dashboard
          </button>
        </Card>

        <Card title="Data" kind="live" why="The snapshot the app reads">
          <p>
            Snapshot of OWASP, MITRE ATLAS, NVD and CISA KEV, as of <strong>{asOf ?? '…'}</strong>.
          </p>
          <button type="button" disabled aria-describedby="check-now-why">
            Check for new CVEs now
          </button>
          <p id="check-now-why" className="meta">
            Not built yet: needs the refresh worker (spec B).
          </p>

          <div className="danger-zone">
            <h3>Reset demo data</h3>
            <p className="meta">
              Back to the default watchlist, no fixed or not-affected marks, default settings, and an empty alerts log.
            </p>
            <div className="field-row">
              <label htmlFor="reset-confirm">
                Type <code>reset</code> to confirm
              </label>
              <input id="reset-confirm" value={confirmText} autoComplete="off"
                onChange={(e) => {
                  setConfirmText(e.target.value)
                  setResetDone(false)
                }} />
              <button type="button" className="danger-btn" disabled={confirmText !== 'reset'} onClick={reset}>
                Reset<span className="visually-hidden"> demo data</span>
              </button>
            </div>
            {resetDone && <p className="ok-note">✓ Reset to the defaults.</p>}
            {resetError && (
              <p role="alert" className="form-error">
                {resetError}
              </p>
            )}
          </div>
        </Card>
      </div>

      <SaveBar dirty={s.dirty} saving={s.saving} saved={s.saved} error={s.error} onSave={s.save} onDiscard={s.discard} />
    </div>
  )
}

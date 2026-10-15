import { useCallback, useEffect, useState, type ReactNode } from 'react'
import {
  alertsLog,
  EXPLAIN_LEVELS,
  resetState,
  testAlert,
  type AlertLogEntry,
  type AlertSettings,
  type Channel,
  type PolicySettings,
  type Severity,
  type TestAlertReply,
} from '../api.ts'
import { SaveBar } from '../components/SaveBar.tsx'
import { Card } from '../components/StatusCard.tsx'
import { useSettings } from '../components/useSettings.ts'
import { useWatchlist } from '../components/useWatchlist.ts'
import { WatchlistCard } from '../components/WatchlistCard.tsx'
import '../styles/settings.css'

// The Settings page (DESIGN.md §5.7): alert rules saved for spec B's refresh, delivery channels with real test
// sends, the watchlist (A15b: edited here, the dashboard only filters by it), the data and a safe reset. Each card says what it really does today.

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

// Your policy (A16): days per priority level. The rules set the level; the policy only sets the due date.
const POLICY_DAYS: { key: keyof PolicySettings & `${string}_days`; label: string }[] = [
  { key: 'urgent_days', label: 'Urgent' },
  { key: 'high_days', label: 'High' },
  { key: 'normal_days', label: 'Normal' },
  { key: 'low_days', label: 'Low' },
]
const clampDays = (v: string) => Math.max(1, Math.min(730, Math.round(Number(v)) || 1))

function when(iso: string): string {
  return iso.replace('T', ' ').replace(/(:\d\d)?\+00:00$/, ' UTC')
}

function outcome(e: AlertLogEntry): ReactNode {
  if (e.error_code === 'not_configured') return <span className="log-error">not set up</span>
  if (e.error) return <span className="log-error">failed: {e.error}</span>
  return e.sent ? 'sent' : 'recorded only'
}

/** B20: a failed save, shown in each card whose edits it didn't save. The edits stay; Save changes tries again. */
function NotSaved({ error, show }: { error: string | null; show: boolean }) {
  if (!error || !show) return null
  return (
    <p role="alert" className="form-error">
      Not saved: {error} Your changes are still here; Save changes tries again.
    </p>
  )
}

export function SettingsPage({ asOf }: { asOf: string | null }) {
  const s = useSettings()
  const w = useWatchlist() // its own route, the same save bar (A15b)
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
  const policy = s.draft.policy
  const daysInOrder = policy.urgent_days <= policy.high_days && policy.high_days <= policy.normal_days &&
    policy.normal_days <= policy.low_days

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
    w.reload()
  }

  // One save bar for the settings and the watchlist. Each saves only if it changed; a rejected watchlist shows its
  // message in its card and stays unsaved, so the bar keeps saying so.
  const dirty = s.dirty || w.dirty
  async function saveAll() {
    if (w.dirty) await w.save()
    if (s.dirty) await s.save()
  }
  function discardAll() {
    s.discard()
    w.discard()
  }

  return (
    <div className="page settings-page">
      <p className="page-intro">Alerts for your watchlist, how they reach you, and the demo data.</p>

      <div className="settings-grid">
        <WatchlistCard w={w} />

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
          <NotSaved error={s.error} show={s.changed('alerts', { except: ['channels'] })} />
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
          <NotSaved error={s.error} show={s.changed('alerts', { only: ['channels'] })} />
        </Card>

        <Card title="Patch's answers" kind="live" why="Patch uses it on your next question">
          <p className="meta">
            How Patch pitches an answer. The facts and sources stay the same at every level; only the wording changes.
            The chat header can switch it for one question.
          </p>
          <fieldset>
            <legend>Explain level</legend>
            {EXPLAIN_LEVELS.map((lv) => (
              <label key={lv.id} className="check-row">
                <input type="radio" name="explain-level" value={lv.id} checked={s.draft?.explain_level === lv.id}
                  onChange={() => s.setValue('explain_level', lv.id)} />
                <strong>{lv.label}</strong>
                <span className="meta inline">{lv.what}</span>
              </label>
            ))}
          </fieldset>
          <NotSaved error={s.error} show={s.changed('explain_level')} />
        </Card>

        <Card title="Priority and due dates" kind="live" why="The CVEs page and the dashboard use it at once">
          <p className="meta">
            Fixed rules set each open CVE's priority from CISA KEV, EPSS, severity, the version check and whether the
            product is internet-facing. Your policy turns the priority into a due date: the publication date (or the
            day it was added to KEV) plus the days below.
          </p>
          <fieldset className="policy-days">
            <legend>Days allowed per priority</legend>
            {POLICY_DAYS.map(({ key, label }) => (
              <div key={key} className="field-row">
                <label htmlFor={`policy-${key}`}>{label}</label>
                <input id={`policy-${key}`} type="number" min={1} max={730} value={policy[key]}
                  onChange={(e) => s.patch('policy', { [key]: clampDays(e.target.value) })} />
                <span className="meta inline">days</span>
              </div>
            ))}
            {!daysInOrder && (
              <p role="alert" className="form-error">
                A more urgent priority can't get more days than a less urgent one: urgent ≤ high ≤ normal ≤ low.
              </p>
            )}
          </fieldset>
          <label className="check-row">
            <input type="checkbox" checked={policy.adopt_kev_deadline}
              onChange={(e) => s.patch('policy', { adopt_kev_deadline: e.target.checked })} />
            <span>
              Use CISA's KEV deadline as the due date for CVEs in KEV
              <span className="meta inline"> (set for US federal agencies; always shown as its own fact)</span>
            </span>
          </label>
          <fieldset>
            <legend>Rule threshold</legend>
            <div className="field-row">
              <label htmlFor="priority-epss">EPSS percentile for high priority</label>
              <input id="priority-epss" type="number" min={50} max={99} value={s.draft.priority.epss_percentile}
                aria-describedby="priority-epss-why"
                onChange={(e) => s.patch('priority', {
                  epss_percentile: Math.max(50, Math.min(99, Math.round(Number(e.target.value)) || 90)),
                })} />
              <span className="meta inline">th or above</span>
            </div>
            <p id="priority-epss-why" className="meta">
              On an internet-facing product, a CVE at or above this EPSS percentile is high priority.
            </p>
          </fieldset>
          <NotSaved error={s.error} show={s.changed('policy') || s.changed('priority')} />
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

      <SaveBar dirty={dirty} saving={s.saving || w.saving} saved={s.saved || w.justSaved} error={s.error}
        onSave={saveAll} onDiscard={discardAll} />
    </div>
  )
}

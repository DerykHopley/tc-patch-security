import { useCallback, useContext, useEffect, useState } from 'react'
import { roleOf } from '../access.ts'
import { DELIVERY_SHOWN } from '../alertsLog.ts'
import { AccessContext } from '../auth/AccessGate.tsx'
import { dataSources } from '../freshness.ts'
import { resetDeletes, resetKeeps, START_OVER_BUTTON } from '../startOver.ts'
import {
  alertsLog,
  EXPLAIN_LEVELS,
  resetState,
  testAlert,
  type AlertLogEntry,
  type AlertSettings,
  type Channel,
  type DataMode,
  type PolicySettings,
  type Severity,
  type TestAlertReply,
} from '../api.ts'
import { AlertList } from '../components/AlertsLog.tsx'
import { ConnectedAccountsCard } from '../auth/ConnectedAccounts.tsx'
import { RefreshRuns } from '../components/RefreshRuns.tsx'
import { RequestsCard } from '../components/RequestsCard.tsx'
import { ProfileCard, useProfileDraft } from '../components/Profile.tsx'
import { IN_PATCH_NOTE } from '../profile.ts'
import { ownersSchedule as ownersScheduleLine } from '../refreshRuns.ts'
import { followLink, openPath } from '../route.ts'
import { SaveBar } from '../components/SaveBar.tsx'
import {
  DataSourceFields, DeliveryFields, isReady, openSetup, revealError, TimeZoneField,
} from '../components/ServerFields.tsx'
import { Card, CardLevel } from '../components/StatusCard.tsx'
import { useServerSettings } from '../components/useServerSettings.ts'
import { useSettings } from '../components/useSettings.ts'
import { useWatchlist } from '../components/useWatchlist.ts'
import { WatchlistCard } from '../components/WatchlistCard.tsx'
import { WelcomeSwitch } from '../components/WelcomeSwitch.tsx'
import '../styles/settings.css'

// The Settings page (DESIGN.md §5.7): in two parts since B48 (#97). "Yours", for everyone: the profile and connected
// accounts, the watchlist (A15b: edited here, the dashboard only filters by it), the alert rules (B04), Patch's answers,
// priority and due dates, then Start over (B50: a reset of the user's own data, in a warning card at the end). "This
// Patch", the owner's only: requests, refresh runs, delivery channels with real test sends, and the data.

const SEVERITIES: { value: Severity; label: string }[] = [
  { value: 'LOW', label: 'Low' },
  { value: 'MEDIUM', label: 'Medium' },
  { value: 'HIGH', label: 'High' },
  { value: 'CRITICAL', label: 'Critical' },
]
const SCHEDULES: AlertSettings['schedule_hours'][] = [1, 3, 6, 12, 24]
const SCHEDULE_KEYS = ['schedule_hours', 'schedule_paused'] // on the Refresh runs card (B19), not Alerts
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
// B26: the Delivery card's server settings, for its "Not saved" line
const DELIVERY_KEYS = ['app_url', 'ntfy_url', 'smtp_port', 'smtp_starttls', 'ntfy_topic', 'ntfy_token', 'smtp_host',
  'smtp_user', 'smtp_password', 'alert_email_from', 'alert_email_to'] as const
const clampDays = (v: string) => Math.max(1, Math.min(730, Math.round(Number(v)) || 1))

/** B20: a failed save, shown in each card whose edits it didn't save. The edits stay; Save changes tries again. */
function NotSaved({ error, show }: { error: string | null; show: boolean }) {
  if (!error || !show) return null
  return (
    <p role="alert" className="form-error">
      Not saved: {error} Your changes are still here; Save changes tries again.
    </p>
  )
}

// `onServerSaved`: the owner saved server settings (B26), so the app's status (live or snapshot, the date) loads again.
export function SettingsPage({ asOf, mode, onServerSaved }: {
  asOf: string | null
  mode?: DataMode
  onServerSaved?: () => void
}) {
  const role = roleOf(useContext(AccessContext)) // B50: what Start over deletes depends on it
  const s = useSettings()
  const w = useWatchlist() // its own route, the same save bar (A15b)
  const p = useProfileDraft() // B48: your display name, the same save bar
  const savedAlerts = s.reply?.settings.alerts
  // B26: the owner's server settings (null for anyone else), saved by the same bar
  const srv = useServerSettings(s.reply?.server, !!(savedAlerts?.quiet_start && savedAlerts.quiet_end), (r) => {
    s.setServer(r)
    onServerSaved?.()
  })
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

  // B19: the dashboard's "Schedule and refresh runs" link opens /settings#schedule: bring the schedule into view
  const loaded = !!s.draft
  useEffect(() => {
    if (loaded && window.location.hash === '#schedule') document.getElementById('schedule')?.scrollIntoView({ block: 'center' })
  }, [loaded])

  if (!s.draft || !s.reply) {
    return (
      <div className="page">
        <p className="muted">{s.error ?? 'Loading settings…'}</p>
      </div>
    )
  }
  const a = s.draft.alerts
  const channels = s.reply.channels
  const quietTz = s.reply.alert_tz ?? 'UTC'
  const owner = isReady(srv) ? srv : null // B26: the owner sees the server settings; anyone else none of them
  const set = (v: Partial<AlertSettings>) => s.patch('alerts', v)
  // B48: the owner sees "This Patch" too; anyone else (sign-in on) only "Yours", with their alerts in Patch only
  const isOwner = s.reply.owner === true
  const live = mode === 'live'
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

  // One save bar for the settings, the watchlist and the profile. Each saves only if it changed; a rejected watchlist
  // or name shows its message in its card and stays unsaved, so the bar keeps saying so.
  const dirty = s.dirty || w.dirty || srv.dirty || p.dirty
  async function saveAll() {
    if (w.dirty) await w.save()
    if (p.dirty) await p.save()
    // B26: quiet hours saved for the first time take the zone shown with them (the owner's: B48)
    const quietSet = isOwner && !!(a.quiet_start && a.quiet_end) &&
      s.changed('alerts', { only: ['quiet_start', 'quiet_end'] })
    if (srv.dirty || quietSet) {
      const error = await srv.save(quietSet)
      if (error && owner) revealError(owner, error) // a folded setup block it's about opens, its field focused
    }
    if (s.dirty) await s.save()
  }
  function discardAll() {
    s.discard()
    w.discard()
    srv.discard()
    p.discard()
  }

  return (
    <div className="page settings-page">
      {/* Two parts (B48, #97, DESIGN.md §5.7): "Yours" for everyone, the owner too; "This Patch", the owner's only (the
          API refuses its routes to anyone else). Each part: packed columns, never CSS `columns`, so DOM order = reading
          order = Tab order. */}
      <CardLevel.Provider value={3}>
        <section className="settings-part" aria-labelledby="part-yours">
          <div className="part-head">
            <h2 id="part-yours">Yours</h2>
            <p className="page-intro">
              Your profile, watchlist, alerts and answers. Everyone who uses Patch has their own. Edits wait for Save
              changes, at the bottom of the page.
            </p>
          </div>
          <div className="settings-layout">
            <WatchlistCard w={w} />

            <div className="settings-column">
              <ProfileCard p={p} />
              <ConnectedAccountsCard />
              <Card title="Alerts">
                <p className="meta">
                  Each live check {isOwner ? 'sends' : 'records'} these alerts once per CVE and reason. A CVE due in 3 days,
                  or overdue (again each week), always alerts while alerts are on.
                </p>
                {!isOwner && (
                  <>
                    {/* B48: anyone but the owner: alerts in Patch only (the channels are the owner's) */}
                    <p className="in-patch-note" data-testid="in-patch-note">{IN_PATCH_NOTE}</p>
                    <p className="meta" id="schedule" data-testid="owners-schedule">
                      {s.reply.schedule ? ownersScheduleLine(s.reply.schedule, mode ?? 'snapshot') : null}
                    </p>
                  </>
                )}

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
                    <label htmlFor="al-digest">Bundle into one digest above</label>
                    <input id="al-digest" type="number" min={1} max={50} value={a.digest_over}
                      onChange={(e) => set({ digest_over: Math.max(1, Math.min(50, Math.round(Number(e.target.value)) || 1)) })} />
                    <span className="meta inline">alerts per check</span>
                  </div>
                  {/* Quiet hours hold what would be sent: the owner's only (B48: nothing is sent for anyone else) */}
                  {isOwner && (
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
                  )}
                  {owner ? (
                    <TimeZoneField f={owner} />
                  ) : isOwner ? (
                    <p className="meta">
                      Alerts found in quiet hours are held and sent as one digest when they end. Times are in the alert time
                      zone ({quietTz}).
                    </p>
                  ) : null}
                </fieldset>
                <NotSaved error={srv.error} show={srv.changed(['alert_tz'])} />
                <NotSaved error={s.error} show={s.changed('alerts', { except: ['channels', ...SCHEDULE_KEYS] })} />
              </Card>
            </div>

            <div className="settings-column">
              <Card title="Patch's answers">
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
                <WelcomeSwitch />
              </Card>

              <Card title="Priority and due dates">
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

            </div>

            {/* B50 (#95): its own warning card, the last of "Yours", across both columns: it deletes the user's whole
                state (the decision history too), so it says exactly what goes and what stays. */}
            <Card title="Start over" className="danger-card" anchor="start-over">
              <p className="meta">Resets everything you set up in Patch to the defaults. It can't be undone. It deletes:</p>
              <ul className="reset-list">
                {resetDeletes(role).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              <p className="meta">{resetKeeps(role)}</p>
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
                  {START_OVER_BUTTON}
                </button>
              </div>
              {resetDone && <p className="ok-note">✓ Reset to the defaults.</p>}
              {resetError && (
                <p role="alert" className="form-error">
                  {resetError}
                </p>
              )}
            </Card>
          </div>
        </section>

        {isOwner && channels && (
          <section className="settings-part" aria-labelledby="part-patch">
            <div className="part-head">
              <h2 id="part-patch">This Patch</h2>
              <p className="page-intro">Only you see this part: it sets Patch up for everyone who uses it.</p>
            </div>
            {/* Requests first, at the top of the right column (owner, 2026-10-19): the card the owner acts on, where
                an alert's /settings#requests lands. So the right column comes first in the DOM (and on a phone);
                the CSS puts it on the right. Since B50 Delivery shows 3 alerts, not 20, so Data moved under it: Delivery
                and Data on the left balance Requests and Refresh runs (20 runs) on the right (DECISIONS.md, B50). */}
            <div className="settings-layout patch-layout">
              <div className="settings-column column-right">
                <RequestsCard />
                <Card title="Refresh runs">
                  <p className="meta">
                    How often the live data is checked, and the last 20 checks: the schedule's, Check now's and Patch's.
                  </p>
                  {/* The owner's only (B48): the refresh is shared and runs on this schedule; anyone else gets one line on
                      their Alerts card */}
                  <fieldset id="schedule">
                    <legend>Schedule</legend>
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
                    <div className="check-row switch-row">
                      {/* B50: nothing is scheduled in snapshot mode, so there is nothing to pause */}
                      <input type="checkbox" id="al-paused" checked={a.schedule_paused} disabled={!live}
                        onChange={(e) => set({ schedule_paused: e.target.checked })} aria-describedby="al-paused-why" />
                      <label htmlFor="al-paused">
                        <strong>Pause the schedule</strong>
                      </label>
                      <span id="al-paused-why" className="meta">
                        {live
                          ? "No scheduled check starts. Check now and Patch's check still work."
                          : 'Only in live mode: the snapshot never changes, so no check is scheduled to pause.'}
                      </span>
                    </div>
                  </fieldset>
                  <NotSaved error={s.error} show={s.changed('alerts', { only: SCHEDULE_KEYS })} />
                  <RefreshRuns reload={JSON.stringify(s.reply.settings.alerts)} />
                </Card>
              </div>

              <div className="settings-column column-left">
                <Card title="Delivery">
                  <p className="meta">
                    Pick where your alerts go, and set each channel up below. A secret you save is never shown again; one set
                    in the server's environment wins. Everyone else's alerts show in Patch only.
                  </p>
                  <ul className="channels">
                    {CHANNELS.map((c) => {
                      const st = channels[c.id]
                      return (
                        <li key={c.id} className={`channel${st.configured ? '' : ' unconfigured'}`}>
                          <input type="checkbox" id={`ch-${c.id}`} checked={a.channels.includes(c.id)}
                            aria-describedby={`ch-${c.id}-what ch-${c.id}-detail`}
                            onChange={(e) => {
                              set({ channels: e.target.checked ? [...a.channels, c.id] : a.channels.filter((x) => x !== c.id) })
                              // ticked but not set up: its setup block opens (the desktop channel has none)
                              if (e.target.checked && !st.configured && c.id !== 'desktop') openSetup(c.id)
                            }} />
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
                  {owner && <DeliveryFields f={owner} ready={{ ntfy: channels.ntfy.configured, email: channels.email.configured }} />}
                  <NotSaved error={srv.error} show={srv.changed(DELIVERY_KEYS)} />
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
                      {preview.channel !== 'desktop' && <p className="meta" data-testid="tap-line">{preview.tap}</p>}
                    </div>
                  )}

                  {/* B50 (#95): the last 3 (a test send shows at the top); the dashboard's card has the last 20 */}
                  <h4 id="delivery-recent">Recent alerts</h4>
                  {log.length === 0 ? (
                    <p className="meta">No alerts yet.</p>
                  ) : (
                    <AlertList entries={log.slice(0, DELIVERY_SHOWN)} labelledBy="delivery-recent" />
                  )}
                  <a className="edit-link" href="/#recent-alerts" onClick={(e) => followLink(e, openPath)}>
                    All recent alerts on the dashboard <span aria-hidden="true">→</span>
                  </a>
                  <NotSaved error={s.error} show={s.changed('alerts', { only: ['channels'] })} />
                </Card>

                <Card title="Data">
                  <p data-testid="data-sources">
                    {dataSources(mode ?? 'snapshot')} As of <strong>{asOf ?? '…'}</strong>.
                  </p>
                  {owner && <DataSourceFields f={owner} />}
                  <NotSaved error={srv.error} show={srv.changed(['data_mode', 'nvd_api_key'])} />
                  <p className="meta" data-testid="check-now-pointer">
                    In live mode, <strong>Check now</strong> on the{' '}
                    <a href="/" onClick={(e) => followLink(e, openPath)}>dashboard's Data freshness card</a> checks the feeds
                    for new CVEs. Every check is listed under <a href="#schedule">Refresh runs</a>.
                  </p>
                </Card>
              </div>
            </div>
          </section>
        )}
      </CardLevel.Provider>

      <SaveBar dirty={dirty} saving={s.saving || w.saving || srv.saving || p.saving}
        saved={s.saved || w.justSaved || srv.justSaved || p.justSaved}
        error={s.error ?? srv.error ?? p.error}
        onSave={saveAll} onDiscard={discardAll} />
    </div>
  )
}

import { useEffect, useState } from "react";
import { ApiError, alertsLog, resetState, testAlert, type AlertMessage, type AlertSettings, type Channel, type Severity } from "../api";
import { SEVERITIES, sevLabel } from "../severity";
import { SaveBar } from "./SaveBar";
import { useSettings } from "./useSettings";

// What each control does today, so the page never pretends: Live, Saved for later, or Mock.
export function Status({ kind, children }: { kind: "live" | "saved" | "mock"; children?: React.ReactNode }) {
  const label = { live: "Live", saved: "Saved for later", mock: "Mock" }[kind];
  return <span className={`status-chip ${kind}`} title={typeof children === "string" ? children : undefined}>{label}</span>;
}

const SCHEDULES: AlertSettings["schedule_hours"][] = [1, 3, 6, 12, 24];

const CHANNELS: { id: Channel; label: string; what: string }[] = [
  { id: "desktop", label: "Desktop notification", what: "Your OS's own notification, on the computer running the app." },
  { id: "email", label: "Email", what: "A plain-text email with a link back to the CVE." },
  { id: "ntfy", label: "Phone push (ntfy)", what: "A push to the ntfy app on your phone; self-hostable." },
];

// G1–G4: alerts, delivery, data. Alert settings are saved now and read by the refresh worker later.
export function Settings({ asOf, onOpenDashboard }: { asOf: string | null; onOpenDashboard: () => void }) {
  const s = useSettings();
  const [log, setLog] = useState<AlertMessage[]>([]);
  const [preview, setPreview] = useState<{ alert: AlertMessage; note: string; channel: string } | null>(null);
  const [sending, setSending] = useState<Channel | "preview" | null>(null);
  const [alertError, setAlertError] = useState<string | null>(null);
  const [confirmText, setConfirmText] = useState("");
  const [resetDone, setResetDone] = useState(false);

  useEffect(() => { alertsLog().then((r) => setLog(r.alerts)).catch(() => setLog([])); }, []);

  if (!s.draft || !s.reply) return <p className="muted page-pad">{s.error ?? "Loading settings…"}</p>;
  const a = s.draft.alerts;
  const set = (v: Partial<AlertSettings>) => s.patch("alerts", v);

  async function sendTest(channel: Channel | "preview") {
    setAlertError(null);
    setSending(channel);
    try {
      const r = await testAlert(channel);
      setPreview({ ...r, channel: r.notifier });
    } catch (e) {
      setAlertError(e instanceof ApiError ? e.message : "Couldn't send the test alert.");
    } finally {
      setSending(null);
      setLog((await alertsLog().catch(() => ({ alerts: log }))).alerts);
    }
  }

  async function reset() {
    await resetState();
    setConfirmText("");
    setResetDone(true);
    setPreview(null);
    setLog([]);
    s.reload();
  }

  return (
    <div className="settings-page">
      <header className="page-head">
        <h2 className="page-title">Settings</h2>
        <p className="muted">Alerts for your watchlist, how they reach you, and the demo data.</p>
      </header>

      <div className="settings-grid">
        <section className="panel">
          <div className="panel-head"><h3>Alerts</h3><Status kind="saved">Used by the refresh worker, not built yet</Status></div>
          <p className="meta">The refresh worker in ALERTS-PLAN.md will read these. Nothing checks for new CVEs yet.</p>

          <label className="switch-row">
            <input type="checkbox" id="al-enabled" checked={a.enabled} onChange={(e) => set({ enabled: e.target.checked })} />
            <span><strong>Send alerts</strong><span className="meta">Turn all alerts on or off.</span></span>
          </label>

          <fieldset disabled={!a.enabled}>
            <legend>Alert me when</legend>
            <label className="check-row">
              <input type="checkbox" id="al-kev" checked={a.kev} onChange={(e) => set({ kev: e.target.checked })} />
              <span>A CVE on my watchlist is added to CISA KEV <span className="pill urgent">urgent</span></span>
            </label>
            <label className="check-row">
              <input type="checkbox" id="al-kev-recheck" checked={a.kev_recheck} onChange={(e) => set({ kev_recheck: e.target.checked })} />
              <span>A CVE I marked fixed is added to KEV, so I can check the fix</span>
            </label>
            <div className="check-row">
              <span className="check-spacer" aria-hidden="true" />
              <span>
                A new CVE is published at or above{" "}
                <select id="al-min-sev" aria-label="Minimum severity" value={a.min_severity}
                  onChange={(e) => set({ min_severity: e.target.value as Severity })}>
                  {SEVERITIES.map((v) => <option key={v} value={v}>{sevLabel(v)}</option>)}
                </select>
              </span>
            </div>
            <label className="check-row">
              <input type="checkbox" id="al-unscored" checked={a.unscored} onChange={(e) => set({ unscored: e.target.checked })} />
              <span>A new CVE has no severity yet <span className="meta inline">NVD often scores days later</span></span>
            </label>
            <label className="check-row">
              <input type="checkbox" id="al-now-critical" checked={a.now_critical} onChange={(e) => set({ now_critical: e.target.checked })} />
              <span>An open CVE is rescored as critical</span>
            </label>
          </fieldset>

          <fieldset disabled={!a.enabled}>
            <legend>Timing</legend>
            <div className="field-row">
              <label htmlFor="al-schedule">Check for new CVEs every</label>
              <select id="al-schedule" value={a.schedule_hours}
                onChange={(e) => set({ schedule_hours: Number(e.target.value) as AlertSettings["schedule_hours"] })}>
                {SCHEDULES.map((h) => <option key={h} value={h}>{h === 1 ? "hour" : `${h} hours`}</option>)}
              </select>
            </div>
            <div className="field-row">
              <label htmlFor="al-digest">Bundle into one digest above</label>
              <input id="al-digest" type="number" min={1} max={50} value={a.digest_over}
                onChange={(e) => set({ digest_over: Math.max(1, Math.min(50, Number(e.target.value) || 1)) })} />
              <span className="meta inline">alerts per check</span>
            </div>
            <div className="field-row">
              <label htmlFor="al-quiet-start">Quiet hours</label>
              <input id="al-quiet-start" type="time" value={a.quiet_start ?? ""} onChange={(e) => set({ quiet_start: e.target.value || null })} />
              <span className="meta inline">to</span>
              <input id="al-quiet-end" type="time" aria-label="Quiet hours end" value={a.quiet_end ?? ""}
                onChange={(e) => set({ quiet_end: e.target.value || null })} />
              {(a.quiet_start || a.quiet_end) && (
                <button type="button" className="link-btn" onClick={() => set({ quiet_start: null, quiet_end: null })}>Clear</button>
              )}
            </div>
            <p className="meta">KEV alerts still come through in quiet hours.</p>
          </fieldset>
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Delivery</h3><Status kind="live">Test alerts are really sent</Status></div>
          <p className="meta">Pick where alerts go. Connection details and secrets live in <code>backend/.env</code>, never here.</p>
          <ul className="channels">
            {CHANNELS.map((c) => {
              const st = s.reply!.env.channels[c.id];
              const on = a.channels.includes(c.id);
              return (
                <li key={c.id} className={st.configured ? "" : "unconfigured"}>
                  <label className="check-row">
                    <input type="checkbox" id={`ch-${c.id}`} checked={on}
                      onChange={(e) => set({ channels: e.target.checked ? [...a.channels, c.id] : a.channels.filter((x) => x !== c.id) })} />
                    <span>
                      <strong>{c.label}</strong> <span className={`pill ${st.configured ? "ready" : "todo"}`}>{st.configured ? "ready" : "not set up"}</span>
                      <span className="meta">{c.what}</span>
                      <span className="meta">{st.detail}</span>
                    </span>
                  </label>
                  <button type="button" disabled={!st.configured || sending !== null} onClick={() => sendTest(c.id)}>
                    {sending === c.id ? "Sending…" : "Send test"}
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="callout">
            <strong>Keep the ntfy topic secret.</strong> ntfy's docs say a topic name is "essentially a password", and your
            alerts show which products you run. Email and desktop alerts never include the CVE description either.
          </div>
          <button type="button" onClick={() => sendTest("preview")} disabled={sending !== null}>Preview an alert (send nothing)</button>
          {alertError && <p className="save-error">{alertError}</p>}
          {preview && (
            <div className="push-preview" aria-live="polite">
              <div className="push">
                <div className="push-app"><span>{preview.channel} · LLM security</span><span>priority {preview.alert.priority}</span></div>
                <strong>{preview.alert.title}</strong>
                <span>{preview.alert.body}</span>
              </div>
              <p className="meta">{preview.note} Built from fields only, never the CVE description.</p>
            </div>
          )}

          <h4>Recent alerts</h4>
          {log.length === 0 ? <p className="muted">No alerts yet.</p> : (
            <ul className="alert-log">
              {log.map((m, i) => (
                <li key={`${m.at}-${i}`}>
                  <span>{m.title}</span>
                  <span className="meta">{m.channel} · {m.at?.replace("T", " ").replace("+00:00", " UTC")} ·{" "}
                    {m.error ? <span className="save-error">failed: {m.error}</span> : m.sent ? "sent" : "recorded only"}</span>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Watchlist</h3><Status kind="live" /></div>
          <p className="meta">Which products count as yours. Alerts and the dashboard both use it.</p>
          <button type="button" onClick={onOpenDashboard}>Edit on the dashboard</button>
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Data</h3><Status kind="live" /></div>
          <p>Snapshot of OWASP, MITRE ATLAS, NVD and CISA KEV, as of <strong>{asOf ?? "…"}</strong>.</p>
          <button type="button" disabled title="Needs the refresh worker (ALERTS-PLAN.md)">Check for new CVEs now</button>
          <p className="meta">Not built yet: needs the refresh worker.</p>

          <div className="danger">
            <h4>Reset demo data</h4>
            <p className="meta">Back to the default watchlist, no fixed or not-affected marks, default settings, and an empty alerts log.</p>
            <div className="field-row">
              <label htmlFor="reset-confirm">Type <code>reset</code> to confirm</label>
              <input id="reset-confirm" value={confirmText} onChange={(e) => { setConfirmText(e.target.value); setResetDone(false); }} />
              <button type="button" className="danger-btn" disabled={confirmText !== "reset"} onClick={reset}>Reset</button>
            </div>
            {resetDone && <p className="saved">✓ Reset to the defaults.</p>}
          </div>
        </section>
      </div>

      <SaveBar dirty={s.dirty} saving={s.saving} savedAt={s.savedAt} error={s.error} onSave={s.save} onDiscard={s.discard} />
    </div>
  );
}

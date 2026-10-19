import type { ReactNode } from 'react'
import type { SecretName, ServerFields, ServerStatus } from '../api.ts'
import {
  blockOf, browserZone, fieldsNamedIn, reachableFromPhone, secretLine, SETUP_KEYS, setupState, sourceLine, tapLine,
  type SetupBlock, type SetupKey,
} from '../serverSettings.ts'
import { feedsLine } from '../freshness.ts'
import type { ServerSettingsForm } from './useServerSettings.ts'

// B26: the owner's settings that used to need backend/.env and a restart, each in the Settings card it belongs to.
// A setting the server's environment sets is shown, disabled, with a line saying so: the environment wins. A
// secret's box is write-only: it never shows what's saved, only whether something is (DESIGN.md §5.7).

type Ready = ServerSettingsForm & { status: ServerStatus; draft: ServerFields }

export const isReady = (f: ServerSettingsForm): f is Ready => !!f.status && !!f.draft

function EnvNote({ f, k, id }: { f: Ready; k: keyof ServerFields; id: string }) {
  const line = sourceLine(f.status, k)
  return line ? <p id={id} className="meta env-note">{line}</p> : null
}

/** One secret: a masked, write-only box, with Remove for a saved one. */
export function SecretField({ f, k, label, why }: { f: Ready; k: SecretName; label: string; why?: string }) {
  const s = f.status.secrets[k]
  const edit = f.secrets[k]
  const env = s.source === 'env'
  const id = `srv-${k}`
  return (
    <div className="secret-field">
      <div className="field-row">
        <label htmlFor={id}>{label}</label>
        <input id={id} type="password" autoComplete="new-password" spellCheck={false} disabled={env}
          value={typeof edit === 'string' ? edit : ''} aria-describedby={`${id}-state${why ? ` ${id}-why` : ''}`}
          placeholder={env ? 'set in the environment' : s.set && edit !== null ? 'saved' : 'not set'}
          onChange={(e) => f.setSecret(k, e.target.value === '' ? undefined : e.target.value)} />
        {!env && s.set && edit !== null && (
          <button type="button" className="link-btn" onClick={() => f.setSecret(k, null)}>
            Remove<span className="visually-hidden"> the saved {label.toLowerCase()}</span>
          </button>
        )}
        {edit === null && (
          <button type="button" className="link-btn" onClick={() => f.setSecret(k, undefined)}>
            Keep<span className="visually-hidden"> the saved {label.toLowerCase()}</span>
          </button>
        )}
      </div>
      <p id={`${id}-state`} className={`meta secret-state${edit === null ? ' removing' : ''}`}>
        {secretLine(f.status, k, edit)}
      </p>
      {why && <p id={`${id}-why`} className="meta">{why}</p>}
    </div>
  )
}

/** B28: where live data comes from (FEEDS, .env only). The fake feeds are a warning: made-up CVEs, made-up alerts. */
function FeedsLine({ status }: { status: ServerStatus }) {
  const line = feedsLine(status.feeds)
  return <p className={`feeds-line ${line.tone}`} data-testid="feeds-line">{line.text}</p>
}

/** Data card: live or snapshot, where live data comes from, and the optional NVD key. */
export function DataSourceFields({ f }: { f: Ready }) {
  const env = f.status.fields.data_mode.source === 'env'
  return (
    <fieldset aria-describedby="srv-data-mode-env">
      <legend>Data source</legend>
      <label className="check-row">
        <input type="radio" name="data-mode" value="snapshot" disabled={env} checked={f.draft.data_mode === 'snapshot'}
          onChange={() => f.set({ data_mode: 'snapshot' })} />
        <strong>Snapshot</strong>
        <span className="meta inline"> the frozen data, as of its date</span>
      </label>
      <label className="check-row">
        <input type="radio" name="data-mode" value="live" disabled={env} checked={f.draft.data_mode === 'live'}
          onChange={() => f.set({ data_mode: 'live' })} />
        <strong>Live</strong>
        <span className="meta inline"> Check now and the schedule refresh it from the feeds; the date is today</span>
      </label>
      <FeedsLine status={f.status} />
      <p className="meta">Switches when you save, with no restart. Back to the snapshot, the live data stays for next time.</p>
      <EnvNote f={f} k="data_mode" id="srv-data-mode-env" />
      <SecretField f={f} k="nvd_api_key" label="NVD API key (optional)"
        why="With a key, NVD allows 50 requests per 30 seconds instead of 5. Only matters after a long gap." />
    </fieldset>
  )
}

function zones(current: string): string[] {
  const all = typeof Intl.supportedValuesOf === 'function' ? Intl.supportedValuesOf('timeZone') : []
  return [...new Set(['UTC', current, browserZone(), ...all])].toSorted((a, b) => (a === 'UTC' ? -1 : b === 'UTC' ? 1 :
    a.localeCompare(b)))
}

/** Alerts card, Timing: the quiet hours' time zone. */
export function TimeZoneField({ f }: { f: Ready }) {
  const tz = f.status.fields.alert_tz
  const env = tz.source === 'env'
  const unsaved = tz.source === 'default' && f.draft.alert_tz !== tz.value
  return (
    <>
      <div className="field-row">
        <label htmlFor="srv-alert-tz">Quiet hours are in</label>
        <select id="srv-alert-tz" value={f.draft.alert_tz} disabled={env} aria-describedby="srv-alert-tz-why"
          onChange={(e) => f.set({ alert_tz: e.target.value })}>
          {zones(f.draft.alert_tz).map((z) => (
            <option key={z} value={z}>
              {z.replaceAll('_', ' ')}
            </option>
          ))}
        </select>
      </div>
      <p id="srv-alert-tz-why" className="meta">
        {env ? sourceLine(f.status, 'alert_tz') : unsaved
          ? `Your browser's time zone. Saved with your quiet hours; until then the server uses ${tz.value}.`
          : 'Alerts found in quiet hours are held and sent as one digest when they end.'}
      </p>
    </>
  )
}

const SETUP_TITLE: Record<SetupBlock, string> = {
  links: 'Alert links', ntfy: 'Phone push (ntfy)', email: 'Email (SMTP)',
}
const blockElement = (b: SetupBlock) => document.getElementById(`setup-${b}`) as HTMLDetailsElement | null

/** Unfolds a setup block. Native <details>: React never sets `open`, so the owner's folding is theirs. */
export function openSetup(b: SetupBlock) {
  const el = blockElement(b)
  if (el) el.open = true
}

/** A failed save: unfold the blocks it is about and focus the first field. The ones the error names; else (a network
 *  error names none) the ones with unsaved edits. Returns nothing: the error itself shows in the card (B20). */
export function revealError(f: Ready, error: string) {
  const named = fieldsNamedIn(error)
  const keys = named.length ? named : Object.values(SETUP_KEYS).flat().filter((k) => f.changed([k]))
  for (const k of keys) {
    const b = blockOf(k)
    if (b) openSetup(b)
  }
  const first = keys.map((k) => document.getElementById(fieldId(k)) as HTMLInputElement | null)
    .find((el) => el && !el.disabled)
  first?.focus()
}

// A field's box: `srv-<name>` for a secret (SecretField), dashes for the plain fields
const PLAIN: readonly SetupKey[] = ['app_url', 'ntfy_url', 'smtp_port', 'smtp_starttls']
const fieldId = (k: SetupKey) => `srv-${PLAIN.includes(k) ? k.replaceAll('_', '-') : k}`

/** One folded setup block (DESIGN.md §5.7): a summary naming it and its state, the fieldset under it. Folded, its
 *  fields stay in the page, so what the owner typed survives folding. */
function Setup({ b, state, unsaved, children }: { b: SetupBlock; state: string; unsaved: boolean; children: ReactNode }) {
  return (
    <details className="setup-block" id={`setup-${b}`}>
      <summary>
        <strong>{SETUP_TITLE[b]}</strong> · {state}
        {unsaved && <span className="setup-unsaved"> · unsaved changes</span>}
      </summary>
      <fieldset aria-label={SETUP_TITLE[b]}>{/* the summary shows its name: no legend */}
        {children}
      </fieldset>
    </details>
  )
}

/** Delivery card: where alert links point, and each channel's connection details, each block folded.
 *  `ready`: whether ntfy and email can send (the server's channel status). */
export function DeliveryFields({ f, ready }: { f: Ready; ready: Record<'ntfy' | 'email', boolean> }) {
  const appUrl = f.draft.app_url
  const here = window.location.origin
  const setup = (b: SetupBlock) => ({
    b, state: setupState(f.status, b, b !== 'links' && ready[b]), unsaved: f.changed(SETUP_KEYS[b]),
  })
  return (
    <>
      <Setup {...setup('links')}>
        <div className="field-row">
          <label htmlFor="srv-app-url">App address for alert links</label>
          <input id="srv-app-url" type="url" inputMode="url" spellCheck={false} value={appUrl}
            disabled={f.status.fields.app_url.source === 'env'} aria-describedby="srv-app-url-tap srv-app-url-env"
            onChange={(e) => f.set({ app_url: e.target.value })} />
          {appUrl !== here && f.status.fields.app_url.source !== 'env' && (
            <button type="button" className="link-btn" onClick={() => f.set({ app_url: here })}>
              Use this page's address
            </button>
          )}
        </div>
        <p id="srv-app-url-tap" className={`meta tap-line${reachableFromPhone(appUrl) ? ' reachable' : ''}`}>
          {tapLine(appUrl)}
        </p>
        <EnvNote f={f} k="app_url" id="srv-app-url-env" />
      </Setup>

      <Setup {...setup('ntfy')}>
        <div className="field-row">
          <label htmlFor="srv-ntfy-url">Server</label>
          <input id="srv-ntfy-url" type="url" inputMode="url" spellCheck={false} value={f.draft.ntfy_url}
            disabled={f.status.fields.ntfy_url.source === 'env'} aria-describedby="srv-ntfy-url-env"
            onChange={(e) => f.set({ ntfy_url: e.target.value })} />
        </div>
        <EnvNote f={f} k="ntfy_url" id="srv-ntfy-url-env" />
        <SecretField f={f} k="ntfy_topic" label="Topic" why="Letters, digits, - and _. Long and random: it works like a password." />
        <SecretField f={f} k="ntfy_token" label="Access token (optional)" />
      </Setup>

      <Setup {...setup('email')}>
        <SecretField f={f} k="smtp_host" label="SMTP server" />
        <div className="field-row">
          <label htmlFor="srv-smtp-port">Port</label>
          <input id="srv-smtp-port" type="number" min={1} max={65535} value={f.draft.smtp_port}
            disabled={f.status.fields.smtp_port.source === 'env'} aria-describedby="srv-smtp-port-env"
            onChange={(e) => f.set({ smtp_port: Math.max(1, Math.min(65535, Math.round(Number(e.target.value)) || 587)) })} />
          <span className="meta inline">587 with STARTTLS, 465 with TLS</span>
        </div>
        <EnvNote f={f} k="smtp_port" id="srv-smtp-port-env" />
        <label className="check-row">
          <input type="checkbox" id="srv-smtp-starttls" checked={f.draft.smtp_starttls} disabled={f.status.fields.smtp_starttls.source === 'env'}
            onChange={(e) => f.set({ smtp_starttls: e.target.checked })} />
          <span>Use STARTTLS</span>
        </label>
        <EnvNote f={f} k="smtp_starttls" id="srv-smtp-starttls-env" />
        <SecretField f={f} k="smtp_user" label="User name" />
        <SecretField f={f} k="smtp_password" label="Password" />
        <SecretField f={f} k="alert_email_from" label="From (empty: the user name)" />
        <SecretField f={f} k="alert_email_to" label="Send to" />
      </Setup>
    </>
  )
}

// The owner's server settings on Settings (B26): live or snapshot data, the quiet hours' time zone, the alert link
// address, the channels' connection details and secrets. Pure functions; the hook is components/useServerSettings.ts.
// The environment wins when it sets one (backend/app/server_settings.py); a secret is never shown, only "set".

import type { SecretName, ServerFields, ServerStatus, ServerUpdate } from './api.ts'

/** Secrets typed (a new value) or removed (null) since the last save. Untouched ones are left out. */
export type SecretEdits = Partial<Record<SecretName, string | null>>

/** Whether a phone could open this address: not when its host is this machine (localhost, 127.0.0.0/8, ::1) or
 *  0.0.0.0, which on a phone is the phone itself. The backend's `reachable_from_phone` has the same rule. */
export function reachableFromPhone(url: string): boolean {
  let host: string
  try {
    host = new URL(url).hostname.replace(/^\[|\]$/g, '')
  } catch {
    return false
  }
  if (!host || host === 'localhost' || host.endsWith('.localhost')) return false
  return !(host.startsWith('127.') || host === '0.0.0.0' || host === '::1' || host === '::')
}

/** What tapping a phone alert does with this address. */
export function tapLine(url: string): string {
  return reachableFromPhone(url)
    ? 'A phone can open this address: tapping an alert opens Patch at the CVE, with Explain it one tap away.'
    : "A phone can't open this address (it's this computer), so alerts carry no link: tapping one opens the " +
        'message in the ntfy app. Use a LAN, Tailscale or Cloud Run address to open Patch from the alert.'
}

/** The browser's time zone, e.g. Europe/London (UTC when the browser doesn't say). */
export function browserZone(): string {
  return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'
}

/** The form's starting values. The time zone is the browser's while nothing is saved or set in the environment,
 *  unless quiet hours are already saved: those were meant in the server's zone, so it stays until the owner picks. */
export function baselineOf(status: ServerStatus, zone: string, quietSaved: boolean): ServerFields {
  const f = status.fields
  const tz = f.alert_tz.source === 'default' && !quietSaved ? zone : f.alert_tz.value
  return {
    data_mode: f.data_mode.value,
    alert_tz: tz,
    app_url: f.app_url.value,
    ntfy_url: f.ntfy_url.value,
    smtp_port: f.smtp_port.value,
    smtp_starttls: f.smtp_starttls.value,
  }
}

const trimUrl = (v: string) => v.trim().replace(/\/+$/, '')

/** What Save sends: the fields changed from the form's start, the secrets typed or removed, and the shown time zone
 *  when quiet hours are being saved while the server has none (so they mean what the owner saw). */
export function serverChanges(status: ServerStatus, base: ServerFields, draft: ServerFields, secrets: SecretEdits,
  quietSet: boolean): ServerUpdate {
  const out: ServerUpdate = {}
  const put = <K extends keyof ServerFields>(k: K, v: ServerFields[K]) => {
    ;(out as Record<string, unknown>)[k] = v
  }
  for (const k of Object.keys(draft) as (keyof ServerFields)[]) {
    if (status.fields[k].source === 'env') continue // the environment wins: never sent
    const v = k === 'app_url' || k === 'ntfy_url' ? trimUrl(String(draft[k])) : draft[k]
    const before = k === 'app_url' || k === 'ntfy_url' ? trimUrl(String(base[k])) : base[k]
    if (v !== before) put(k, v)
  }
  const tz = status.fields.alert_tz
  if (quietSet && tz.source === 'default' && draft.alert_tz !== tz.value) put('alert_tz', draft.alert_tz)
  for (const [k, v] of Object.entries(secrets) as [SecretName, string | null][]) {
    if (status.secrets[k].source === 'env') continue
    if (v === null || v.trim() !== '') out[k] = v === null ? null : k === 'smtp_password' ? v : v.trim()
  }
  return out
}

const envLine = (name: string) => `Set in the server's environment (${name}), which wins.`

/** The note under a plain setting set in the environment; null when Settings decides it. */
export function sourceLine(status: ServerStatus, key: keyof ServerFields): string | null {
  return status.fields[key].source === 'env' ? envLine(status.env_names[key]) : null
}

/** The note under a secret's box: where it's set, never what it is. `edit`: what the owner typed or removed. */
export function secretLine(status: ServerStatus, key: SecretName, edit: string | null | undefined): string {
  const s = status.secrets[key]
  if (s.source === 'env') return envLine(status.env_names[key])
  if (edit === null) return 'Removed when you save.'
  if (edit) return 'Saved when you save.'
  return s.set ? 'Saved. Type a new one to replace it.' : 'Not set.'
}

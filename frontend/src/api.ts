// The backend's HTTP API. Every call goes through request(), so a server that isn't
// running gives one plain message instead of a raw network error.

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface Health {
  status: 'ok'
  llm: string // provider id, e.g. "fake"
  model: string // the model in use, as shown to the user
  as_of: string // the as-of date, YYYY-MM-DD
  dev_panel: boolean // the Dev page is shown only when this is true
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_URL}${path}`, init)
  } catch {
    throw new Error(`Can't reach the backend at ${API_URL}. Is it running?`)
  }
  const body: unknown = await res.json().catch(() => null)
  if (!res.ok) {
    const message = (body as { error?: { message?: string } } | null)?.error?.message
    throw new Error(message ?? `The backend answered ${res.status}.`)
  }
  return body as T
}

export const health = () => request<Health>('/health')

// --- Settings page (A13): alert rules, channels, test alerts, the alerts log, reset

export type Severity = 'LOW' | 'MEDIUM' | 'HIGH' | 'CRITICAL'
export type Channel = 'desktop' | 'email' | 'ntfy'

export interface AlertSettings {
  enabled: boolean
  min_severity: Severity
  kev: boolean
  kev_recheck: boolean
  unscored: boolean
  now_critical: boolean
  digest_over: number
  schedule_hours: 1 | 3 | 6 | 12 | 24
  quiet_start: string | null // HH:MM
  quiet_end: string | null
  channels: Channel[]
}

export interface AppSettings {
  alerts: AlertSettings
}

export interface ChannelStatus {
  configured: boolean
  detail: string // how it's set up, or how to set it up; never a secret
}

export interface SettingsReply {
  settings: AppSettings
  channels: Record<Channel, ChannelStatus>
}

export interface AlertMessage {
  title: string
  body: string
  priority: number
  tags: string[]
  click: string | null
}

export interface AlertLogEntry extends AlertMessage {
  at: string // ISO time, UTC
  channel: Channel | 'preview'
  sent: boolean
  error: string | null
  error_code: 'not_configured' | 'notify_failed' | null
}

export interface TestAlertReply {
  alert: AlertMessage
  channel: Channel | 'preview'
  sent: boolean
  note: string
}

const sendJson = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

export const getSettings = () => request<SettingsReply>('/settings')
export const saveSettings = (s: AppSettings) => request<{ settings: AppSettings }>('/settings', sendJson('PUT', s))
export const alertsLog = () => request<{ alerts: AlertLogEntry[] }>('/alerts')
export const testAlert = (channel: Channel | 'preview') =>
  request<TestAlertReply>('/alerts/test', sendJson('POST', { channel }))
export const resetState = () =>
  request<{ reset: boolean; watchlist: string[] }>('/state/reset', sendJson('POST', { confirm: 'reset' }))

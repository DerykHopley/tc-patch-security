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

// --- Chat (A06). Shapes written by hand from backend/app/schemas.py. Severity is the dashboard's, below.

export type Role = 'user' | 'assistant'
export type DocType = 'owasp_llm' | 'owasp_web' | 'atlas_technique' | 'atlas_mitigation' | 'atlas_case' | 'cve'

export interface Turn {
  role: Role
  content: string
}

export interface Source {
  n: number
  chunk_id: string
  doc_id: string
  doc_type: DocType
  title: string
  section: string | null
  date: string | null
  url: string
  snippet: string
  score: number | null // null for a CVE added by lookup_cve
  product: string | null
  severity: Severity | null
  cvss: number | null
  kev: boolean | null
}

export interface QueryInfo {
  original: string
  semantic_query: string
  rewrites: string[]
  filters: Record<string, string>
  dropped_filters: string[]
  relaxed: boolean
}

export interface ToolCallRecord {
  id: string
  name: string
  args: Record<string, unknown>
  status: 'ok' | 'error'
  result: Record<string, unknown> | null
  error: { code: string; message: string } | null
  duration_ms: number
}

export interface Usage {
  input_tokens: number
  output_tokens: number
  llm_calls: number
  estimated: boolean
  cost: number // USD, OpenRouter's usage.cost summed over the answer; 0 for local models and FakeLLM
}

export interface ChatReply {
  answer: string
  sources: Source[]
  tool_calls: ToolCallRecord[]
  query: QueryInfo | null
  usage: Usage
  steps: number
  flags: string[] // "injection_phrasing": flagged, still answered
  bad_citations: number[] // [n] removed from the answer: no source n
  no_citations: boolean // has sources but cites none of them
}

export interface Example {
  id: string
  question: string
}

export const chat = (message: string, history: Turn[]) =>
  request<ChatReply>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history }),
  })

export const examples = () => request<Example[]>('/examples')

// --- Dashboard (A04)

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type CveStatus = 'open' | 'fixed' | 'not_affected'

export interface Product {
  id: string
  name: string
}

export interface Dashboard {
  as_of: string
  watchlist: string[] // product ids
  products: Product[] // every product in the snapshot: the watchlist is chosen from these
  kpis: {
    open: number
    critical: number
    kev: number
    kev_next_due: { cve: string; due: string } | null
    new_30d: number
  }
}

export interface CveRow {
  id: string
  product: string
  product_name: string
  severity: Severity | null
  cvss: number | null
  published: string
  owasp: string | null
  owasp_title: string | null
  kev: boolean
  kev_due: string | null
  status: CveStatus
  summary: string
  url: string
}

export interface CveQuery {
  product?: string
  severity_min?: Severity
  status: CveStatus | 'all'
  limit: number
  offset: number
}

export interface CvePage {
  total: number
  rows: CveRow[]
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export const dashboard = () => request<Dashboard>('/dashboard')

export function cves(q: CveQuery): Promise<CvePage> {
  const params = new URLSearchParams({ status: q.status, limit: String(q.limit), offset: String(q.offset) })
  if (q.product) params.set('product', q.product)
  if (q.severity_min) params.set('severity_min', q.severity_min)
  return request<CvePage>(`/cves?${params}`)
}

export const setStatus = (id: string, status: CveStatus) =>
  request<{ id: string; status: CveStatus }>(`/cves/${encodeURIComponent(id)}`, json('PATCH', { status }))

export const setWatchlist = (products: string[]) =>
  request<{ watchlist: string[] }>('/watchlist', json('PUT', { products }))

// --- Settings page (A13): alert rules, channels, test alerts, the alerts log, reset

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

export const getSettings = () => request<SettingsReply>('/settings')
export const saveSettings = (s: AppSettings) => request<{ settings: AppSettings }>('/settings', json('PUT', s))
export const alertsLog = () => request<{ alerts: AlertLogEntry[] }>('/alerts')
export const testAlert = (channel: Channel | 'preview') =>
  request<TestAlertReply>('/alerts/test', json('POST', { channel }))
export const resetState = () =>
  request<{ reset: boolean; watchlist: string[] }>('/state/reset', json('POST', { confirm: 'reset' }))

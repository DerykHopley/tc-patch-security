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
  score: number | null // fused RRF score; null for a CVE added by lookup_cve
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
  found_by: Record<string, string[]> // source n → the retrievers that found it: "keyword" (BM25), "vector"
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
    new_since: string // the first of those 30 days, YYYY-MM-DD: the tile's link filters on it
  }
  by_product: ProductCounts[] // open CVEs per watched product, in watchlist order
  per_month: { month: string; count: number }[] // all statuses, by publication month (YYYY-MM)
  by_owasp: { code: string; title: string; count: number }[] // open CVEs per OWASP web category
  owasp_unmapped: number // open CVEs whose CWE isn't in OWASP's lists
  latest_incidents: Incident[] // the 5 latest MITRE ATLAS incidents
  freshness: Source[] // one per snapshot source
}

export type ProductCounts = { product: string; name: string; total: number } & Record<Severity, number>

export interface Incident {
  id: string
  name: string
  date: string
  url: string
  summary: string
}

export interface Source {
  id: string // owasp_llm, owasp_web, atlas, nvd, kev, osv, epss
  name: string
  licence: string
  attribution: string // the credit line shown in the freshness panel
  notice?: string // NVD's required notice
  url: string
  retrieved: string
  as_of?: string // when the data is dated, if not the retrieval day (OSV, EPSS)
  count: number
}

// EPSS by FIRST: the chance of exploitation in the next 30 days (0-1) and its percentile, frozen with the snapshot.
export interface Epss {
  score: number
  percentile: number
  date: string
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
  epss: Epss | null
  possible_match: boolean // product guessed from the description and not confirmed by OSV
}

export interface CveQuery {
  product?: string
  severity_min?: Severity
  status: CveStatus | 'all'
  kev?: boolean // only CVEs in CISA KEV (A04b: the KEV tile's link)
  published_since?: string // YYYY-MM-DD, inclusive (A04b: the "new in 30 days" tile's link)
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
  if (q.kev !== undefined) params.set('kev', String(q.kev))
  if (q.published_since) params.set('published_since', q.published_since)
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

// --- Dev panel (A11): only when the backend allows it (Health.dev_panel); off, every /dev route is a 404

export type Provider = 'fake' | 'openrouter' | 'local'

export interface DevSettings {
  provider: Provider
  openrouter_model: string
  local_url: string // checked by the backend's SSRF guard: this machine only
  local_model: string
  temperature: number
  max_steps: number
  top_n: number
  per_query_k: number
  per_doc_cap: number
  rrf_k: number
  keyword_weight: number // 0 = vector only, 1 = keyword (BM25) only
  use_rewrites: boolean
  use_filters: boolean
}

export interface DevSettingsReply {
  settings: DevSettings
  defaults: DevSettings // from the backend's .env
  openrouter_key: boolean // whether OPENROUTER_API_KEY is set; the key itself never leaves the server
}

export interface DevInfo {
  chunks: number
  by_doc_type: Record<string, number>
  embedder: string
  dim: number
  min_score: number
  as_of: string
  local_hosts: string[]
}

export interface Hit {
  chunk_id: string
  title: string
  doc_type: DocType
  score: number
}

export type SearchOptions = Pick<
  DevSettings,
  'top_n' | 'per_query_k' | 'per_doc_cap' | 'rrf_k' | 'keyword_weight' | 'use_rewrites' | 'use_filters'
>

export interface DevSearch {
  query: QueryInfo
  options: SearchOptions
  lists: { retriever: 'vector' | 'keyword'; query: string; hits: Hit[] }[] // each query on each retriever, before fusion
  fused: { chunk_id: string; title: string; doc_type: DocType; rrf: number }[]
  final: { n: number; chunk_id: string; title: string; section: string | null; doc_type: DocType }[]
  map: { query: string; x: number; y: number }[] // the semantic query, then each rewrite
}

export interface MapPoint {
  id: string
  doc_id: string
  title: string
  type: DocType
  x: number
  y: number
}

export interface EmbeddingMapData {
  embedder: string
  dim: number
  explained: [number, number]
  points: MapPoint[]
}

export const getDevSettings = () => request<DevSettingsReply>('/dev/settings')
export const saveDevSettings = (s: DevSettings) => request<{ settings: DevSettings }>('/dev/settings', json('PUT', s))
export const devInfo = () => request<DevInfo>('/dev/info')
export const devModels = (url: string) => request<{ models: string[] }>(`/dev/models?${new URLSearchParams({ url })}`)
export const devSearch = (query: string) => request<DevSearch>('/dev/search', json('POST', { query }))
export const devMap = () => request<EmbeddingMapData>('/dev/map')

// --- The model check (A12): exact checks per question, retrieval metrics per embedder, the report

export interface CheckFailure {
  name: string // a check id, e.g. "tools"
  passed: boolean
  expected: string
  got: string
}

export interface ModelCheckRow {
  id: string
  question: string
  passed: boolean
  checks: Record<string, boolean>
  failures: CheckFailure[]
  tools: string[]
  answer: string
  seconds: number
  cost: number // USD
  tokens_in: number
  tokens_out: number
  steps: number
  error: string | null
}

export interface ModelCheckSummary {
  questions: number
  passed: number
  errors: number
  checks_passed: number
  checks_total: number
  by_check: Record<string, { passed: number; total: number }>
  seconds_total: number
  avg_seconds: number | null
  cost_total: number
  avg_cost: number | null
  tokens_in: number
  tokens_out: number
  estimated: boolean
  bad_citations: number
  no_citations: number
}

export interface ModelCheckRun {
  id: string
  status: 'running' | 'done' | 'failed'
  model: string
  provider: Provider
  started: string
  finished: string | null
  total: number
  error: string | null
  summary: ModelCheckSummary | null // null while running
  results: ModelCheckRow[]
}

export type ModelCheckListed = Omit<ModelCheckRun, 'results'>

export interface RetrievalMiss {
  id: string
  question: string
  expected: string[]
  got: string[] // the top 5 documents instead
  rank: number | null // of the first right document, up to 10
}

export interface RetrievalMetrics {
  questions: number
  hits: number
  hit_rate_at_5: number | null
  mrr: number | null
  misses: RetrievalMiss[]
}

export interface RetrievalRun {
  id: string
  embedder: string
  dim: number
  started: string
  seconds: number
  questions: number
  modes: { vector: RetrievalMetrics; hybrid: RetrievalMetrics }
}

export const startModelCheck = (ids: string[] = []) =>
  request<ModelCheckRun>('/dev/model-check', json('POST', { ids }))
export const getModelCheck = (id: string) => request<ModelCheckRun>(`/dev/model-check/${encodeURIComponent(id)}`)
export const listModelChecks = () => request<{ runs: ModelCheckListed[] }>('/dev/model-checks')
export const runRetrievalCheck = () => request<RetrievalRun>('/dev/retrieval-check', { method: 'POST' })
export const listRetrievalChecks = () => request<{ runs: RetrievalRun[] }>('/dev/retrieval-checks')

/** The report page for these runs; none named = the latest run per model and per embedder. */
export function reportUrl(models: string[], retrieval: string[]): string {
  const q = new URLSearchParams()
  if (models.length) q.set('models', models.join(','))
  if (retrieval.length) q.set('retrieval', retrieval.join(','))
  const s = q.toString()
  return `${API_URL}/dev/report${s ? `?${s}` : ''}`
}

// The backend's HTTP API. Every call goes through request(), so a server that isn't
// running gives one plain message instead of a raw network error.

import { cvesQuery, type CveView } from './cveView.ts'
import type { NamedResult, Proposal, ProposalSource } from './toolResults.ts'

export const API_URL: string = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export interface Health {
  status: 'ok'
  llm: string // provider id, e.g. "fake"
  model: string // the model in use, as shown to the user
  as_of: string // the as-of date, YYYY-MM-DD
  dev_panel: boolean // the Dev page is shown only when this is true
  mode: DataMode // B02: frozen snapshot or live data
  last_checked: string | null // B02: when the live data was last checked (ISO 8601, UTC); null before the first check
}

// B02: the data mode. "snapshot": frozen data, as of the snapshot date. "live": refreshed by Check now, as of today.
export type DataMode = 'snapshot' | 'live'

export interface DataStatus {
  mode: DataMode
  last_checked: string | null
  last_result?: RefreshResult | null // /dashboard only (B20): the last run, for the partial or failed banner
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
export type DocType =
  | 'owasp_llm'
  | 'owasp_web'
  | 'atlas_technique'
  | 'atlas_mitigation'
  | 'atlas_case'
  | 'cve'
  | 'web' // a web result from research_web (B08): unverified

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
  site?: string | null // web only (B08): the page's site
  flags?: string[] // web only: "injection_phrasing" when the page tries to give instructions
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

// `name` and `result` come as a pair (NamedResult): check the name, and the result has that tool's type.
export type ToolCallRecord = NamedResult & {
  id: string
  args: Record<string, unknown>
  status: 'ok' | 'error'
  error: { code: string; message: string } | null
  duration_ms: number
  retryable: boolean // B20: an error a second try may pass (a timeout, a rate limit): the card offers Try again
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
  flags: string[] // "injection_phrasing": flagged, still answered; "web_injection_phrasing": a web result was
  bad_citations: number[] // [n] removed from the answer: no source n
  no_citations: boolean // has sources but cites none of them
  explain_level: ExplainLevel // the level this answer was pitched at (A19)
  page_context: PageContext // the checked page context Patch had (A18)
  dropped_context: string[] // page-context values the backend dropped: "key=value"
}

// Page context (A18): fixed fields only, each checked by the backend (app/page_context.py). Never free text.
export interface PageContext {
  page?: 'dashboard' | 'cves' | 'settings' | 'dev'
  product?: string // one id, or the dashboard's several (A15b): `langflow,ollama`
  severity?: Severity
  status?: CveStatus | 'all'
  verdict?: Verdict
  kev?: boolean
  since?: string // YYYY-MM-DD
  new?: boolean // new since the last check (B05)
  cve?: string // the selected CVE
}

export interface Example {
  id: string
  question: string
}

// How Patch pitches an answer (A19). Same facts and sources at every level; only the wording changes.
export type ExplainLevel = 'simple' | 'normal' | 'deep_dive'

export const EXPLAIN_LEVELS: { id: ExplainLevel; label: string; what: string }[] = [
  { id: 'simple', label: 'Simple', what: 'Plain words and everyday comparisons.' },
  { id: 'normal', label: 'Normal', what: 'Clear and direct, for developers.' },
  { id: 'deep_dive', label: 'Deep dive', what: 'The technical detail: CWE, attack path, CVSS vector.' },
]

// explainLevel: this message only; left out, the backend uses the saved level. page: what the user is looking at.
export const chat = (message: string, history: Turn[], explainLevel?: ExplainLevel, page?: PageContext) =>
  request<ChatReply>('/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, history, ...(explainLevel && { explain_level: explainLevel }), ...(page && { page }) }),
  })

/** Try again on a tool card (B20): that one step, run again with the same arguments. Its result is the card's only. */
export const retryTool = (call: ToolCallRecord, page: PageContext) =>
  request<ToolCallRecord>('/chat/tool', json('POST', { name: call.name, args: call.args, page }))

export const examples = () => request<Example[]>('/examples')

// --- Dashboard (A04)

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type CveStatus = 'open' | 'fixed' | 'not_affected' | 'accepted'

// Not affected needs one of these VEX justifications (A16b); OpenVEX uses the same names.
export type Justification =
  | 'component_not_present'
  | 'vulnerable_code_not_present'
  | 'vulnerable_code_not_in_execute_path'
  | 'vulnerable_code_cannot_be_controlled_by_adversary'
  | 'inline_mitigations_already_exist'

/** One decision record (A16b): what, why, when and who. Appended to the CVE's history, never edited. */
export interface Decision {
  status: CveStatus
  justification: Justification | null // not affected
  reason: string | null // accepted
  note: string | null // fixed, reopen, not affected; "recorded before decision records" for an old status
  review_date: string | null // accepted
  compensating_control: string | null // accepted, optional
  decided_at: string | null // ISO date and time (UTC); null for a status saved before decision records
  decided_by: string | null // "owner" until there are users
  via: 'page' | 'chat' | null
  proposal?: string // the proposal you approved, for a change Patch proposed in the chat (B21)
  sources?: ProposalSource[] // what that proposal cited (B22)
}

/** What the user enters when changing a status. Which fields a status takes is checked by the backend. */
export type DecisionInput = { status: CveStatus } & Partial<
  Pick<Decision, 'justification' | 'reason' | 'note' | 'review_date' | 'compensating_control'>
>

export interface Product {
  id: string
  name: string
}

export interface Dashboard {
  as_of: string
  watchlist: string[] // product ids
  products: Product[] // every product in the snapshot: the watchlist is chosen from these
  filter: string[] // the product filter applied (A15b): watched ids in watchlist order; [] = every watched product
  watched: WatchedCounts[] // one per watched product, whatever the filter: the filter's chips
  kpis: {
    open: number
    critical: number
    kev: number
    // The open KEV CVE with the earliest due date (A16: your due date, which may be CISA's KEV deadline)
    kev_next_due: { cve: string; due: string; overdue: boolean; no_fix: boolean } | null
    kev_overdue: number // open KEV CVEs past their due date
    overdue: number // open CVEs past their due date that have a fix (A16b)
    no_fix: number // open CVEs with no fixed version in OSV: "no fix yet" (A16b)
    review_due: number // accepted CVEs whose review date has come: back in open (A16b)
    accepted: number // accepted and not yet due for review
    new_30d: number
    new_since: string // the first of those 30 days, YYYY-MM-DD: the tile's link filters on it
  }
  by_product: ProductCounts[] // open CVEs per watched product, in watchlist order
  per_month: { month: string; count: number }[] // all statuses, by publication month (YYYY-MM)
  by_owasp: { code: string; title: string; count: number }[] // open CVEs per OWASP web category
  owasp_unmapped: number // open CVEs whose CWE isn't in OWASP's lists
  latest_incidents: Incident[] // the 5 latest MITRE ATLAS incidents
  freshness: SnapshotSource[] // one per snapshot source
  data: DataStatus // B02: Live or Snapshot, and the last check, for the freshness panel
}

/** A watched product's open CVEs and how many of them are in CISA KEV (A15b: the dashboard filter's chips). */
export interface WatchedCounts {
  product: string
  name: string
  open: number
  kev: number
}

export type ProductCounts = { product: string; name: string; total: number } & Record<Severity, number>

export interface Incident {
  id: string
  name: string
  date: string
  url: string
  summary: string
}

/** One source of the snapshot, for the freshness panel. Not a chat answer's Source. */
export interface SnapshotSource {
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
  kev_deadline: string | null // CISA's remediation date: a fact, not your due date
  new: boolean // new since the user's previous check (B05): the "New" chip
  status: CveStatus
  summary: string
  url: string
  epss: Epss | null
  possible_match: boolean // product guessed from the description and not confirmed by OSV
  // Am I affected? (A15): the version check's advice from the product's usage and version. Never the status.
  verdict: Verdict
  verdict_reason: string // e.g. "1.2.0 is before the fixed version 1.3.0 (langflow)", or why it's unknown
  fixed_version: string | null
  who_acts: WhoActs
  usage: ProductUsage
  version: string | null
  internet_facing: boolean
  // Priority by rules (A16): the level, its reasons, and your due date from your policy. Rules decide the order.
  priority: PriorityLevel
  priority_reasons: string[] // e.g. ["in KEV", "EPSS 99th percentile", "internet-facing"]
  priority_rule: number // the rule table's row that matched
  alert_priority: 5 | 4 | 3 | 2 // the level as an alert priority (spec B)
  due_date: string
  due_from: string // "KEV deadline", "published + 90 days", "added to KEV + 7 days"
  overdue: boolean // open, a fix exists, and past the due date at the as-of date (A16b)
  // Your decision (A16b). `open`: status open, or accepted with its review due. "No fix yet": OSV lists no fixed
  // version, so it can't be overdue; the due date is the "decide by" date.
  open: boolean
  review_due: boolean
  review_date: string | null
  decision: Decision | null // the newest record; null when never decided
  history: Decision[] // oldest first
  no_fix: boolean
  open_days: number // since publication, at the as-of date
}

export type PriorityLevel = 'urgent' | 'high' | 'normal' | 'low'

export type Verdict = 'affected' | 'not_affected' | 'unknown'
export type WhoActs = 'you' | 'upstream' | 'vendor'
export type ProductUsage = 'self_hosted' | 'library' | 'transitive' | 'hosted'

/** How you run one product (A15). `coverage` says whether OSV has versions for it at all. */
export interface ProductFields {
  product: string
  usage: ProductUsage
  version: string | null
  internet_facing: boolean
}

export interface WatchedProduct extends ProductFields {
  name: string
  watched: boolean
  coverage: 'package' | 'commits' | 'none'
  ecosystem: 'PyPI' | 'npm' | 'Go' | null
}

export interface Watchlist {
  watchlist: string[]
  products: WatchedProduct[] // every product: watched first, in watchlist order
}

export interface CvePage {
  total: number
  rows: CveRow[]
}

function json(method: string, body: unknown): RequestInit {
  return { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

/** products: the dashboard's filter (A15b); unknown or unwatched ones are ignored by the backend. */
export const dashboard = (products: string[] = []) =>
  request<Dashboard>(products.length ? `/dashboard?${new URLSearchParams({ product: products.join(',') })}` : '/dashboard')

/** One page of the CVE view's rows: the view's names are the query's (cveView.ts). */
export const cves = (view: CveView, limit: number, offset = 0) => request<CvePage>(cvesQuery(view, limit, offset))

// --- Live data (B02): Check now. The backend's app/refresh.py has the same shapes (RefreshResult, CheckReply).

export interface RefreshCounts {
  new: number // CVEs not there before
  updated: number // CVEs whose record changed (rescored and added to KEV included)
  kev_added: number // CVEs newly in CISA KEV
  rescored: number // CVEs whose severity or CVSS score changed
}

/** One feed's step in a refresh (B20): it answered, or why it didn't. */
export interface FeedResult {
  source: string // nvd, kev, osv or epss
  ok: boolean
  message: string | null
}

export interface RefreshResult {
  trigger: string // button, chat, schedule or cli
  started: string // ISO 8601, UTC
  finished: string
  ok: boolean // true: a version was written (every feed answered, or some did: see status); false: nothing changed
  counts: RefreshCounts
  new_cves: string[]
  version: number | null
  errors: { source: string; message: string }[] // the feeds that failed, and failed alerts (source "alerts")
  alerts?: Record<string, AlertLogEntry[]> // per user id, this run's alerts (B04)
  status: 'ok' | 'partial' | 'failed' // B20: every feed answered, some did (and were written), or none did
  feeds: FeedResult[] // B20: each feed's step, in the order asked; empty in runs logged before B20
}

export interface CheckReply {
  ran: boolean
  result: RefreshResult | null // this run's result; when refused, the last run's (null before any run)
  refusal: { reason: 'too_soon' | 'running'; next_allowed: string; message: string } | null
}

export const checkNow = () => request<CheckReply>('/refresh', { method: 'POST' })

export const setStatus = (id: string, body: DecisionInput) =>
  request<{ id: string; status: CveStatus; decision: Decision }>(`/cves/${encodeURIComponent(id)}`, json('PATCH', body))

// Changes Patch proposes (B21): nothing changes until you approve. Approving again returns the first result.
/** Your corrections to a proposal: a status's decision fields, or a product's usage, version, internet-facing. */
export type ProposalEdit =
  | DecisionInput
  | { usage?: ProductUsage; version?: string; internet_facing?: boolean }
const proposalPath = (id: string) => `/proposals/${encodeURIComponent(id)}`
export const getProposal = (id: string) => request<Proposal>(proposalPath(id))
export const approveProposal = (id: string) => request<Proposal>(`${proposalPath(id)}/approve`, { method: 'POST' })
export const cancelProposal = (id: string) => request<Proposal>(`${proposalPath(id)}/cancel`, { method: 'POST' })
export const editProposal = (id: string, body: ProposalEdit) => request<Proposal>(proposalPath(id), json('PATCH', body))

export const getWatchlist = () => request<Watchlist>('/watchlist')

/** Replace the watchlist. A plain id keeps that product's saved fields; an object replaces them. */
export const setWatchlist = (products: (string | ProductFields)[]) =>
  request<Watchlist>('/watchlist', json('PUT', { products }))

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

/** Your policy (A16): days per priority level, and whether KEV CVEs take CISA's KEV deadline. */
export interface PolicySettings {
  urgent_days: number
  high_days: number
  normal_days: number
  low_days: number
  adopt_kev_deadline: boolean
}

export interface AppSettings {
  alerts: AlertSettings
  explain_level: ExplainLevel
  policy: PolicySettings
  priority: { epss_percentile: number } // the rule table's threshold (row 2), 50-99
}

export interface ChannelStatus {
  configured: boolean
  detail: string // how it's set up, or how to set it up; never a secret
}

export interface SettingsReply {
  settings: AppSettings
  channels: Record<Channel, ChannelStatus>
  alert_tz?: string // the time zone of quiet hours (ALERT_TZ, B04)
}

export interface AlertMessage {
  title: string
  body: string
  priority: number
  tags: string[]
  click: string | null
}

// The alert reasons (B04; the table in ALERTS-PLAN.md)
export type AlertReason = 'kev' | 'kev_recheck' | 'new' | 'new_unscored' | 'now_critical' | 'due_soon' | 'overdue'

/** One channel's result for one message: sent, recorded only (not sent, no error), not set up, or failed. */
export interface ChannelResult {
  channel: Channel | 'preview'
  sent: boolean
  error: string | null
  error_code: 'not_configured' | 'notify_failed' | null
}

/** One message in the alerts log (app/alerts.py): one alert, a digest of several, a test alert from Settings, or
 * (in a refresh result only) an alert held through quiet hours. */
export interface AlertLogEntry extends AlertMessage {
  at: string // ISO time, UTC
  kind: 'alert' | 'digest' | 'held' | 'test'
  cve: string | null // one alert's CVE; null for a digest or a test
  reason: AlertReason | null
  alerts: { cve: string; reason: AlertReason; priority: number }[]
  channels: ChannelResult[]
  in_app_only?: boolean // B09: another user's alert: recorded and shown here, never sent (the channels are the owner's)
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

/** One OpenRouter model this key may use that takes tools (A11.10). Prices are USD per million tokens; null =
 *  variable (unknown). `check` = its latest model-check run, if any. */
export interface OpenRouterModel {
  id: string
  name: string
  input_per_m: number | null
  output_per_m: number | null
  context_length: number | null
  check: { passed: number; total: number; run: string } | null
}

/** Cheapest input first. Empty with a plain `reason` when there's no key or OpenRouter can't be asked. */
export const devOpenRouterModels = () =>
  request<{ models: OpenRouterModel[]; reason: string | null }>('/dev/openrouter-models')
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

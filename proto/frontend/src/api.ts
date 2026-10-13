// Typed client for the backend. Types are written by hand from backend/app/schemas.py (A1, A2).

export const API_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type Role = "user" | "assistant";

export interface Turn {
  role: Role;
  content: string;
}

export type Provider = "fake" | "openrouter" | "local";
export type Channel = "ntfy" | "email" | "desktop";

export type DocType = "owasp_llm" | "owasp_web" | "atlas_technique" | "atlas_mitigation" | "atlas_case" | "cve";
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

export interface Source {
  n: number;
  chunk_id: string;
  doc_id: string;
  doc_type: DocType;
  title: string;
  section: string | null;
  date: string | null;
  url: string;
  snippet: string;
  score: number | null; // null for a CVE added by lookup_cve
  product: string | null;
  severity: Severity | null;
  cvss: number | null;
  kev: boolean | null;
}

export interface QueryInfo {
  original: string;
  semantic_query: string;
  rewrites: string[];
  filters: Record<string, string>;
  dropped_filters: string[];
  relaxed: boolean;
}

export interface ToolError {
  code: string;
  message: string;
}

export interface ToolCallRecord {
  id: string;
  name: string;
  args: Record<string, unknown>;
  status: "ok" | "error";
  result: Record<string, unknown> | null;
  error: ToolError | null;
  duration_ms: number;
}

export interface Usage {
  input_tokens: number;
  output_tokens: number;
  llm_calls: number;
  estimated: boolean;
}

export interface ChatReply {
  answer: string;
  sources: Source[];
  tool_calls: ToolCallRecord[];
  query: QueryInfo | null;
  usage: Usage;
  steps: number;
  flags: string[]; // V2: "injection_phrasing"
}

export interface Example {
  id: string;
  question: string;
}

export interface Health {
  status: "ok";
  llm: Provider;
  as_of: string;
  dev_panel: boolean;
  model: string;
}

// --- Settings page and dev panel (G1–G4, X1–X4)

export interface AlertSettings {
  enabled: boolean;
  min_severity: Severity;
  kev: boolean;
  kev_recheck: boolean;
  unscored: boolean;
  now_critical: boolean;
  digest_over: number;
  schedule_hours: 1 | 3 | 6 | 12 | 24;
  quiet_start: string | null;
  quiet_end: string | null;
  channels: Channel[];
}

export interface DevSettings {
  provider: Provider;
  model: string;
  local_base_url: string;
  local_model: string;
  temperature: number;
  max_steps: number;
  top_n: number;
  per_query_k: number;
  per_doc_cap: number;
  rrf_k: number;
  use_rewrites: boolean;
  use_filters: boolean;
}

export interface AppSettings {
  alerts: AlertSettings;
  dev: DevSettings;
}

export interface SettingsReply {
  settings: AppSettings;
  env: {
    llm_provider: Provider;
    env_model: string;
    openrouter_key: boolean;
    local_hosts: string[];
    channels: Record<Channel, { configured: boolean; detail: string }>;
    dev_panel: boolean;
  };
}

export interface AlertMessage {
  title: string;
  body: string;
  priority: number;
  tags: string[];
  click: string | null;
  at?: string;
  channel?: string;
  sent?: boolean;
  error?: string | null;
}

export interface EvalRow {
  id: string;
  question: string;
  checks: Record<string, boolean>;
  passed: boolean;
  tools: string[];
  answer: string;
  seconds: number;
  tokens_in: number;
  tokens_out: number;
  steps: number;
  error: string | null;
}

export interface EvalSummary {
  questions: number;
  passed: number;
  checks_passed: number;
  checks_total: number;
  errors: number;
  avg_seconds: number | null;
  tokens_in: number;
  tokens_out: number;
}

export interface EvalRun {
  id: string;
  status: "running" | "done" | "failed";
  model: string;
  provider: Provider;
  started: string;
  total: number;
  results: EvalRow[];
  error: string | null;
  summary?: EvalSummary;
}

export interface DevInfo {
  chunks: number;
  by_doc_type: Record<string, number>;
  embedder: string;
  dim: number | null;
  word_gate: boolean;
  llm: string;
  env_model: string;
  as_of: string;
}

export interface DevSearch {
  query: QueryInfo;
  lists: { query: string; hits: { chunk_id: string; title: string; doc_type: DocType; score: number }[] }[];
  fused: { chunk_id: string; title: string; rrf: number }[];
  final: Source[];
  map: { query: string; x: number; y: number }[];
}

export interface MapPoint {
  id: string;
  doc_id: string;
  title: string;
  type: DocType;
  x: number;
  y: number;
}

// --- Dashboard (D1–D4)

export type CveStatus = "open" | "fixed" | "not_affected";

export interface Kpis {
  open: number;
  critical: number;
  kev: number;
  kev_next_due: { cve: string; due: string } | null;
  new_30d: number;
}

export type ProductCounts = { product: string; name: string; total: number } & Record<Severity, number>;

export interface Dashboard {
  as_of: string;
  watchlist: string[];
  products: { id: string; name: string }[];
  kpis: Kpis;
  by_product: ProductCounts[];
  per_month: { month: string; count: number }[];
  by_owasp: { code: string; title: string; count: number }[];
  owasp_unmapped: number;
  latest_incidents: { id: string; name: string; date: string; url: string; summary: string }[];
  freshness: { name: string; licence: string; url: string; retrieved: string; count: number }[];
}

export interface CveRow {
  id: string;
  product: string;
  product_name: string;
  severity: Severity | null;
  cvss: number | null;
  published: string;
  owasp: string | null;
  owasp_title: string | null;
  kev: boolean;
  kev_due: string | null;
  status: CveStatus;
  summary: string;
  url: string;
}

export interface CveQuery {
  product?: string;
  severity_min?: Severity;
  status?: CveStatus | "all";
  limit?: number;
  offset?: number;
}

/** An error from the API, or from not reaching it, with a message a person can read (U7). */
export class ApiError extends Error {
  readonly code: string;
  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, init);
  } catch {
    throw new ApiError("network_error", `Can't reach the backend at ${API_URL}. Is it running?`);
  }
  const body: unknown = await res.json().catch(() => null);
  if (!res.ok) {
    // The backend sends {error: {code, message}} (V1, V6). Anything else gets a generic message.
    const err = (body as { error?: ToolError } | null)?.error;
    throw new ApiError(err?.code ?? `http_${res.status}`, err?.message ?? `The backend replied with HTTP ${res.status}.`);
  }
  return body as T;
}

export function chat(message: string, history: Turn[]): Promise<ChatReply> {
  return request<ChatReply>("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history }),
  });
}

export const examples = () => request<Example[]>("/examples");
export const health = () => request<Health>("/health");
export const dashboard = () => request<Dashboard>("/dashboard");

export function cves(q: CveQuery): Promise<{ total: number; rows: CveRow[] }> {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(q)) if (v !== undefined && v !== "") params.set(k, String(v));
  return request(`/cves?${params}`);
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const setStatus = (id: string, status: CveStatus) =>
  request<{ id: string; status: CveStatus }>(`/cves/${encodeURIComponent(id)}`, json("PATCH", { status }));

export const getSettings = () => request<SettingsReply>("/settings");
export const saveSettings = (s: AppSettings) => request<{ settings: AppSettings }>("/settings", json("PUT", s));
export const alertsLog = () => request<{ alerts: AlertMessage[] }>("/alerts");
export const testAlert = (channel: Channel | "preview") =>
  request<{ alert: AlertMessage; notifier: string; sent: boolean; note: string }>("/alerts/test", json("POST", { channel }));
export const resetState = () => request<{ reset: boolean; watchlist: string[] }>("/state/reset", json("POST", { confirm: "reset" }));
export const devInfo = () => request<DevInfo>("/dev/info");
export const devMap = () => request<{ explained: [number, number]; points: MapPoint[] }>("/dev/map");
export const devModels = (baseUrl: string) =>
  request<{ models: string[] }>(`/dev/models?base_url=${encodeURIComponent(baseUrl)}`);
export const startEval = () => request<EvalRun>("/dev/eval", json("POST", {}));
export const getEval = (id: string) => request<EvalRun>(`/dev/eval/${encodeURIComponent(id)}`);
export const evalHistory = () =>
  request<{ runs: Pick<EvalRun, "id" | "model" | "provider" | "started" | "status" | "summary">[] }>("/dev/evals");
export const devSearch = (query: string) => request<DevSearch>("/dev/search", json("POST", { query }));

export const setWatchlist = (products: string[]) =>
  request<{ watchlist: string[] }>("/watchlist", json("PUT", { products }));

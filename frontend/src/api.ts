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

// --- Chat (A06). Shapes written by hand from backend/app/schemas.py.

export type Role = 'user' | 'assistant'
export type DocType = 'owasp_llm' | 'owasp_web' | 'atlas_technique' | 'atlas_mitigation' | 'atlas_case' | 'cve'
export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

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
}

export interface ChatReply {
  answer: string
  sources: Source[]
  tool_calls: ToolCallRecord[]
  query: QueryInfo | null
  usage: Usage
  steps: number
  flags: string[] // "injection_phrasing": flagged, still answered
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

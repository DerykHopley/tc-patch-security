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

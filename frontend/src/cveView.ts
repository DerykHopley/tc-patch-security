import type { CveStatus, PageContext, Severity, Verdict } from './api.ts'
import { SEVERITIES, sevLabel } from './severity.ts'
import { VERDICT_LABEL, VERDICTS } from './verdict.ts'

// The CVE view: what the CVEs page shows, its filters. One set of names everywhere: the page's URL
// (`/cves?product=langflow&severity=CRITICAL&status=all&verdict=affected&kev=1&since=2026-09-14&new=1`), the /cves
// query and the page context Patch is told (A18) all say product, severity, status, verdict, kev, since, new, the same names as
// the backend's CveView (app/cve_filters.py). Plain TypeScript, so it runs under node --test (cveView.test.ts).

export type StatusFilter = CveStatus | 'all'

export interface CveView {
  product?: string // one id, or several comma-separated from a dashboard link (A15b): `langflow,ollama`
  severity?: Severity // this or worse
  status: StatusFilter
  verdict?: Verdict // A15
  kev?: true // only CVEs in CISA KEV (the KEV tile's link)
  since?: string // YYYY-MM-DD, published on or after (the "new in 30 days" tile's link)
  new?: true // only CVEs new since the last check (B05)
}

/** The defaults: every watched product, any severity, open. They need no parameters. */
export const OPEN_VIEW: CveView = { status: 'open' }

/** A product id, as the backend checks it (app/cve_filters.py: at most 40 characters); ids only, lower case. */
export const PRODUCT_ID = /^[a-z0-9][a-z0-9.-]{0,39}$/
const MAX_PRODUCTS = 20 // as the backend: more than the snapshot tracks
const DATE = /^\d{4}-\d{2}-\d{2}$/

// Your CVE status in words (A16b): the CVEs page's filter, the decision records, the chat's tool cards and chip.
export const STATUS_LABEL: Record<CveStatus, string> = {
  open: 'Open',
  fixed: 'Fixed',
  not_affected: 'Not affected',
  accepted: 'Accepted',
}
/** The status filter's options, in order: the statuses, then all of them ("All"; the chip says "All statuses"). */
export const STATUS_FILTERS: StatusFilter[] = ['open', 'fixed', 'not_affected', 'accepted', 'all']
export const statusFilterLabel = (s: StatusFilter) => (s === 'all' ? 'All' : STATUS_LABEL[s])

/** Product ids from a `product` parameter: malformed ones dropped (the URL is text from outside), no repeats. */
export function productIds(value: string | null): string[] {
  const ids = (value ?? '').split(',').filter((p) => PRODUCT_ID.test(p))
  return [...new Set(ids)].slice(0, MAX_PRODUCTS)
}

/** The view in a query string. Anything malformed is dropped: the URL is text from outside. */
export function viewFromSearch(search: string): CveView {
  const p = new URLSearchParams(search)
  const product = productIds(p.get('product')).join(',')
  const severity = (p.get('severity') ?? '').toUpperCase() as Severity
  const status = p.get('status') as StatusFilter
  const verdict = p.get('verdict') as Verdict
  const since = p.get('since') ?? ''
  return {
    status: STATUS_FILTERS.includes(status) ? status : 'open',
    ...(product && { product }),
    ...(SEVERITIES.includes(severity) && { severity }),
    ...(VERDICTS.includes(verdict) && { verdict }),
    ...(p.get('kev') === '1' && { kev: true as const }),
    ...(DATE.test(since) && { since }),
    ...(p.get('new') === '1' && { new: true as const }),
  }
}

function params(v: CveView): URLSearchParams {
  const p = new URLSearchParams()
  if (v.product) p.set('product', v.product)
  if (v.severity) p.set('severity', v.severity)
  if (v.status !== 'open') p.set('status', v.status)
  if (v.verdict) p.set('verdict', v.verdict)
  if (v.kev) p.set('kev', '1')
  if (v.since) p.set('since', v.since)
  if (v.new) p.set('new', '1')
  return p
}

// Several products stay readable: product=langflow,ollama (the ids are checked, so the comma is safe)
const readable = (p: URLSearchParams) => p.toString().replaceAll('%2C', ',')

/** The query string for the view; the defaults need none: `?product=langflow&kev=1` or ''. */
export function viewToSearch(v: CveView): string {
  const s = readable(params(v))
  return s ? `?${s}` : ''
}

/** The /cves request for the view: the same names as the URL, plus the page. */
export function cvesQuery(v: CveView, limit: number, offset: number): string {
  const p = params(v)
  p.set('limit', String(limit))
  p.set('offset', String(offset))
  return `/cves?${readable(p)}`
}

/** The view as page context (A18): the same names, so it's the view's set filters, with the status always said. */
export function viewToContext(v: CveView): PageContext {
  return {
    ...(v.product && { product: v.product }),
    ...(v.severity && { severity: v.severity }),
    status: v.status,
    ...(v.verdict && { verdict: v.verdict }),
    ...(v.kev && { kev: true }),
    ...(v.since && { since: v.since }),
    ...(v.new && { new: true }),
  }
}

/** The page context in words, for the chat header's chip: "Langflow · High or worse · CVE-2025-3248". */
export function contextWords(ctx: PageContext, productName?: string): string[] {
  return [
    ctx.product && (productName ?? ctx.product),
    ctx.severity && `${sevLabel(ctx.severity)} or worse`,
    ctx.status && ctx.status !== 'open' && (ctx.status === 'all' ? 'All statuses' : STATUS_LABEL[ctx.status]),
    ctx.verdict && VERDICT_LABEL[ctx.verdict],
    ctx.kev && 'In KEV',
    ctx.since && `Since ${ctx.since}`,
    ctx.new && 'New since last check',
    ctx.cve,
  ].filter((w): w is string => !!w)
}

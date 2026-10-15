import type { CveQuery, PageContext, Severity, Verdict } from './api.ts'
import { VERDICT_LABEL } from './components/Verdict.tsx'
import type { Page } from './route.ts'
import { sevLabel } from './severity.ts'

// Page context (A18): what Patch knows about the view under the chat. Fixed fields only (the page, the CVEs page's
// filters, the selected CVE; on the dashboard its product filter, A15b); the backend checks each against fixed lists
// and drops anything else. Never free text.

export type CveFilters = Omit<CveQuery, 'limit' | 'offset'>

/** What the CVEs page (or the dashboard) shows: its filters, and the products' display names for the chip. */
export interface CveView {
  filters: CveFilters
  productName?: string
}

/** The view's filters as one comparable string (the product's display name left out): changes when a filter does. */
export function filtersKey(view: CveView): string {
  return JSON.stringify(Object.entries(view.filters).filter(([, v]) => v != null && v !== '').toSorted())
}

/** The context sent with a message. Filters and the selected CVE only on the CVEs page; the dashboard sends its
 *  product filter (several products: `langflow,ollama`), and nothing more, since its tiles mix statuses. */
export function pageContext(page: Page, view: CveView | null, selected: string | null): PageContext {
  if (page === 'dashboard' && view?.filters.product) return { page, product: view.filters.product }
  if (page !== 'cves' || !view) return { page }
  const f = view.filters
  return {
    page,
    ...(f.product && { product: f.product }),
    ...(f.severity_min && { severity: f.severity_min }),
    status: f.status,
    ...(f.verdict && { verdict: f.verdict }),
    ...(f.kev && { kev: true }),
    ...(f.published_since && { since: f.published_since }),
    ...(selected && { cve: selected }),
  }
}

const STATUS_WORD = { open: 'Open', fixed: 'Fixed', not_affected: 'Not affected', accepted: 'Accepted', all: 'All statuses' }

/** The context in words, for the chat header's chip: "Langflow · High or worse · CVE-2025-3248". */
export function contextWords(ctx: PageContext, productName?: string): string[] {
  return [
    ctx.product && (productName ?? ctx.product),
    ctx.severity && `${sevLabel(ctx.severity as Severity)} or worse`,
    ctx.status && ctx.status !== 'open' && STATUS_WORD[ctx.status],
    ctx.verdict && VERDICT_LABEL[ctx.verdict as Verdict],
    ctx.kev && 'In KEV',
    ctx.since && `Since ${ctx.since}`,
    ctx.cve,
  ].filter((w): w is string => !!w)
}

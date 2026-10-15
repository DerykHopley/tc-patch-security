import type { PageContext } from './api.ts'
import { contextWords, viewToContext, type CveView } from './cveView.ts'
import type { Page } from './route.ts'

// Page context (A18): what Patch knows about the view under the chat. Fixed fields only (the page, the CVEs page's
// filters, the selected CVE; on the dashboard its product filter, A15b); the backend checks each against fixed lists
// and drops anything else. Never free text.
// The rules (a new visit clears the view; a filter change clears the selection; no selection while a reply is pending)
// live here as a pure reducer, tested in pageContext.test.ts. usePageContext.ts is the thin React hook over it.

/** What the CVEs page (or the dashboard) shows: its CVE view, and the products' display names for the chip. */
export interface ShownView {
  filters: CveView
  productName?: string
}

/** The page context's state. The view and the selected CVE belong to one visit of one page (`route.visit` counts
 *  navigations): leave the page, or follow a link to it again, and the next visit starts with neither, so its first
 *  render can't show the last visit's filters. */
export interface PageContextState {
  page: Page
  visit: number
  view: ShownView | null // what the page reported last (CVEs page or dashboard), during this visit
  selected: string | null // the CVE last asked about with "Ask about this" (CVEs page), under the current filters
}

export type PageContextAction =
  | { type: 'visit'; page: Page; visit: number } // a navigation: another page, or the same page again
  | { type: 'view'; visit: number; view: ShownView } // a page reports its view (on every filter change)
  | { type: 'select'; cve: string; pending: boolean } // "Ask about this"; pending: a reply is still coming

export function startPageContext(page: Page, visit: number): PageContextState {
  return { page, visit, view: null, selected: null }
}

export function reducePageContext(s: PageContextState, a: PageContextAction): PageContextState {
  switch (a.type) {
    case 'visit':
      return startPageContext(a.page, a.visit)
    case 'view': {
      if (a.visit !== s.visit) return s // from a visit that has ended
      // The selection belongs to the filters it was made under: any filter change clears it.
      const changed = s.view !== null && filtersKey(s.view) !== filtersKey(a.view)
      return { ...s, view: a.view, selected: changed ? null : s.selected }
    }
    case 'select':
      // While a reply is still coming the chat takes no new question, so nothing is selected either.
      if (a.pending || s.page !== 'cves') return s
      return { ...s, selected: a.cve }
  }
}

/** What the chat sends with a message now. */
export function currentContext(s: PageContextState): PageContext {
  return pageContext(s.page, s.view, s.selected)
}

/** The current context in words, for the chat header's chip. */
export function chipWords(s: PageContextState): string[] {
  return contextWords(currentContext(s), s.view?.productName)
}

/** The view's filters as one comparable string (the product's display name left out): changes when a filter does. */
function filtersKey(view: ShownView): string {
  return JSON.stringify(Object.entries(view.filters).filter(([, v]) => v != null && v !== '').toSorted())
}

/** The context sent with a message. Filters and the selected CVE only on the CVEs page; the dashboard sends its
 *  product filter (several products: `langflow,ollama`), and nothing more, since its tiles mix statuses. */
function pageContext(page: Page, view: ShownView | null, selected: string | null): PageContext {
  if (page === 'dashboard' && view?.filters.product) return { page, product: view.filters.product }
  if (page !== 'cves' || !view) return { page }
  return { page, ...viewToContext(view.filters), ...(selected && { cve: selected }) }
}

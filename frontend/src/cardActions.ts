// Buttons on tool cards (B24, DESIGN.md §6.7): which buttons a card offers, and where its link goes. Plain
// TypeScript, so it runs under node --test (cardActions.test.ts). The buttons themselves: chat/CardActions.tsx.
import type { RefineFilter } from './api.ts'
import { viewToSearch } from './cveView.ts'
import type { Filters } from './toolResults.ts'

/** "Open in CVEs page": the fix-first card's view (open CVEs, its filters), as the CVEs page's own URL. */
export function fixFirstHref(f: Filters): string {
  return `/cves${viewToSearch({
    status: 'open',
    ...(f.product && { product: f.product }),
    ...(f.severity && { severity: f.severity }),
    ...(f.verdict && { verdict: f.verdict }),
    ...(f.kev && { kev: true as const }),
    ...(f.since && { since: f.since }),
  })}`
}

export type ChangeButton = 'watch' | 'set_version' | 'not_affected'
type WatchStatus = 'open' | 'fixed' | 'not_affected' | 'accepted' | 'not_watched'

/** The change buttons for one CVE's card (lookup, am I affected?), by its status: only changes that would change
 *  something. A product that isn't watched gets "Watch this product" only: its version and status don't count yet. */
export function changeButtons(status: WatchStatus): ChangeButton[] {
  if (status === 'not_watched') return ['watch']
  return status === 'open' || status === 'accepted' ? ['set_version', 'not_affected'] : ['set_version']
}

const REFINES: { id: RefineFilter; label: string }[] = [
  { id: 'only_cves', label: 'Show only CVEs' },
  { id: 'only_critical', label: 'Only critical' },
]

/** The search card's refine buttons not applied yet; each sends what's applied so far plus its own filter. */
export function refineButtons(applied: RefineFilter[]): { label: string; filters: RefineFilter[] }[] {
  return REFINES.filter((r) => !applied.includes(r.id)).map((r) => ({ label: r.label, filters: [...applied, r.id] }))
}

import { useCallback, useEffect, useState, type MouseEvent } from 'react'

// Each page has a path, so a link (a tile, "See all CVEs", an alert) opens the right page and a reload stays on it.
// The CVEs page also keeps its filters in the query string (A04b): `/cves?product=langflow&severity=CRITICAL`.
// One CVE has its own page under CVEs (B35): `/cves/CVE-2025-3248`, so a link to it can be shared, Back works, and
// alerts and the chat link straight to it.
// No router library: a handful of paths and the browser's history are all the app needs.

export type Page = 'dashboard' | 'cves' | 'settings' | 'dev'

export const PATHS: Record<Page, string> = { dashboard: '/', cves: '/cves', settings: '/settings', dev: '/dev' }

const CVE_ID = /^CVE-\d{4}-\d{4,7}$/i
const SHOWN = 40 // characters of a CVE path segment kept: it's only shown back ("No such CVE")

export const isCveId = (id: string) => CVE_ID.test(id)

/** The link to one CVE's page (B35). */
export function cvePath(id: string): string {
  return `${PATHS.cves}/${encodeURIComponent(id.toUpperCase())}`
}

/** The page a path shows, and the CVE for /cves/<id>. Any segment there opens the CVE page: a malformed or unknown
 *  id gets "No such CVE" with a link back to the list, not the dashboard. */
export function locate(pathname: string): { page: Page; cve: string | null } {
  const path = pathname.replace(/\/+$/, '') || '/'
  const one = path.match(/^\/cves\/([^/]+)$/)
  if (one) return { page: 'cves', cve: decoded(one[1]).toUpperCase().slice(0, SHOWN) }
  const page = (Object.keys(PATHS) as Page[]).find((p) => PATHS[p] === path) ?? 'dashboard'
  return { page, cve: null }
}

function decoded(segment: string): string {
  try {
    return decodeURIComponent(segment)
  } catch {
    return segment
  }
}

/** An alert sent before B35 links to `#cve=CVE-…` on any path: it now opens that CVE's page. Only a well-formed id
 *  is followed: the hash is text from outside. */
export function alertLinkPath(hash: string): string | null {
  const m = /^#cve=(.+)$/i.exec(hash)
  return m && CVE_ID.test(m[1]) ? cvePath(m[1]) : null
}

/** The history state of a CVE page opened from the CVEs list (B35): its back link then steps back to the list, in
 *  place, instead of opening the list again at the top. */
export const FROM_LIST = { cveFromList: true }
export const openedFromList = () => (history.state as { cveFromList?: boolean } | null)?.cveFromList === true

export interface Route {
  page: Page
  cve: string | null // on /cves/<id>: the CVE whose page is open (B35); null on the list and every other page
  search: string // the query string when the page was opened: the CVEs page reads its filters from it
  visit: number // counts navigations, so a page opened again with other filters starts from them
}

function current(visit: number): Route {
  // An old alert link is replaced (not pushed): Back leaves the app as it would have before.
  const alert = alertLinkPath(window.location.hash)
  if (alert) history.replaceState(null, '', alert)
  return { ...locate(window.location.pathname), search: window.location.search, visit }
}

/** The page in the address bar, and a function that opens another one (a new history entry; Back returns). */
export function useRoute(): [Route, (href: string) => void] {
  const [route, setRoute] = useState(() => current(0))

  useEffect(() => {
    const onPop = () => setRoute((r) => current(r.visit + 1))
    window.addEventListener('popstate', onPop)
    window.addEventListener('hashchange', onPop) // an alert link followed while the app is open
    return () => {
      window.removeEventListener('popstate', onPop)
      window.removeEventListener('hashchange', onPop)
    }
  }, [])

  const navigate = useCallback((href: string) => {
    history.pushState(null, '', href)
    window.scrollTo(0, 0)
    setRoute((r) => current(r.visit + 1))
  }, [])

  return [route, navigate]
}

/** Opens an in-app path from a part that has no `navigate` (the chat's proposal card, B21; a CVE link, B35): a new
 *  history entry, then the popstate useRoute listens to, so the page follows as for Back. `state`: the new entry's
 *  history state (a CVE page opened from the list knows Back returns there). */
export function openPath(href: string, state: unknown = null): void {
  history.pushState(state, '', href)
  window.scrollTo(0, 0)
  window.dispatchEvent(new PopStateEvent('popstate'))
}

/** Follows an in-app link without a page load; a modified click (new tab, new window) is left to the browser. */
export function followLink(e: MouseEvent<HTMLAnchorElement>, navigate: (href: string) => void): void {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  e.preventDefault()
  navigate(e.currentTarget.getAttribute('href') ?? '/')
}

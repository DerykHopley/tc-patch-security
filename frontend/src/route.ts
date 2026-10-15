import { useCallback, useEffect, useState, type MouseEvent } from 'react'

// Each page has a path, so a link (a tile, "See all CVEs", an alert) opens the right page and a reload stays on it.
// The CVEs page also keeps its filters in the query string (A04b): `/cves?product=langflow&severity=CRITICAL`.
// No router library: four paths and the browser's history are all the app needs.

export type Page = 'dashboard' | 'cves' | 'settings' | 'dev'

export const PATHS: Record<Page, string> = { dashboard: '/', cves: '/cves', settings: '/settings', dev: '/dev' }

function pageOf(pathname: string): Page {
  const path = pathname.replace(/\/+$/, '') || '/'
  return (Object.keys(PATHS) as Page[]).find((p) => PATHS[p] === path) ?? 'dashboard'
}

export interface Route {
  page: Page
  search: string // the query string when the page was opened: the CVEs page reads its filters from it
  visit: number // counts navigations, so a page opened again with other filters starts from them
}

function current(visit: number): Route {
  return { page: pageOf(window.location.pathname), search: window.location.search, visit }
}

/** The page in the address bar, and a function that opens another one (a new history entry; Back returns). */
export function useRoute(): [Route, (href: string) => void] {
  const [route, setRoute] = useState(() => current(0))

  useEffect(() => {
    const onPop = () => setRoute((r) => current(r.visit + 1))
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [])

  const navigate = useCallback((href: string) => {
    history.pushState(null, '', href)
    window.scrollTo(0, 0)
    setRoute((r) => current(r.visit + 1))
  }, [])

  return [route, navigate]
}

/** Follows an in-app link without a page load; a modified click (new tab, new window) is left to the browser. */
export function followLink(e: MouseEvent<HTMLAnchorElement>, navigate: (href: string) => void): void {
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return
  e.preventDefault()
  navigate(e.currentTarget.getAttribute('href') ?? '/')
}

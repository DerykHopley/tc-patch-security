import { useCallback, useLayoutEffect, useRef, useState } from 'react'
import type { PageContext } from './api.ts'
import {
  chipWords,
  currentContext,
  reducePageContext,
  startPageContext,
  type ShownView,
  type PageContextAction,
} from './pageContext.ts'
import { isCveId, type Route } from './route.ts'

/** The page context (A18) for the app shell: the rules live in pageContext.ts's reducer; this hook only follows the
 *  route and keeps the latest state for the chat. */
export interface PageContextHandle {
  words: string[] // what Patch is told now, in words, for the chat header's chip
  selected: string | null // the selected CVE, highlighted on the CVEs page
  current: () => PageContext // what the chat sends: the context at the moment of asking, including a CVE selected in the same click
  reportView: (view: ShownView) => void // a page reports its view (filters, products' names) on every change
  select: (cve: string, pending: boolean) => void // "Ask about this"; does nothing while a reply is pending
}

export function usePageContext(route: Route): PageContextHandle {
  // One CVE's page (B35): Patch is told its CVE, when the id is one (a malformed one would be dropped as crafted)
  const cvePage = route.cve && isCveId(route.cve) ? route.cve : null
  const [state, setState] = useState(() => startPageContext(route.page, route.visit, cvePage))
  // A navigation starts a new visit. Applied during render (React's "adjust state when a prop changes"), so the new
  // page's first render never shows the last visit's view.
  let now = state
  if (state.visit !== route.visit) {
    now = reducePageContext(state, { type: 'visit', page: route.page, visit: route.visit, cve: cvePage })
    setState(now)
  }
  const latest = useRef(now)
  useLayoutEffect(() => {
    latest.current = now
  })
  const act = useCallback((a: PageContextAction) => {
    latest.current = reducePageContext(latest.current, a)
    setState(latest.current)
  }, [])

  const visit = route.visit
  const reportView = useCallback((view: ShownView) => act({ type: 'view', visit, view }), [act, visit])
  const select = useCallback((cve: string, pending: boolean) => act({ type: 'select', cve, pending }), [act])
  const current = useCallback(() => currentContext(latest.current), [])
  return { words: chipWords(now), selected: now.selected, current, reportView, select }
}

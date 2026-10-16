import type { ReactNode } from 'react'
import { httpHref } from '../toolCalls.ts'

/** A link that opens in a new tab, only for an http(s) URL; anything else (a `javascript:` URL from a web page)
 *  shows its text without a link. */
export function ExternalLink({ href, children }: { href: string | null | undefined; children: ReactNode }) {
  const safe = httpHref(href)
  if (!safe) return <span>{children}</span>
  return (
    <a href={safe} target="_blank" rel="noreferrer">
      {children}
    </a>
  )
}

// What the chat's cards need to know about a tool call, in one place.
import type { ToolCallRecord } from './api.ts'
import type { Proposal } from './toolResults.ts'

/** The change a tool call proposes (B21 update_watchlist, B22 propose_decision), or null. Known by the result's
 *  shape (a `proposal_id`), not a list of tool names, so a new tool that proposes needs no change here. */
export function proposalOf(call: Pick<ToolCallRecord, 'result'>): Proposal | null {
  const r: unknown = call.result
  return r !== null && typeof r === 'object' && 'proposal_id' in r ? (r as Proposal) : null
}

/** A URL a card may link to: http or https only, or null. Web results come from the open web, so a `javascript:` or
 *  `data:` URL must never become an href (the backend drops them too: app/web_research.py `web_link`). */
export function httpHref(url: string | null | undefined): string | null {
  if (!url) return null
  try {
    const u = new URL(url) // an absolute URL only: a relative one throws
    return u.protocol === 'http:' || u.protocol === 'https:' ? url : null
  } catch {
    return null
  }
}

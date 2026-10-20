// What the chat's cards need to know about a tool call, in one place.
import type { ToolCallRecord } from './api.ts'
import { JUSTIFICATION_LABEL, STATUS_LABEL } from './cveView.ts'
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

/** A proposal's "after" value as the card shows it (B49 C3, #96): a status change reads "Accepted, review 2026-11-17"
 *  or "Not affected, vulnerable code not present", and the free text (reason or note, the compensating control) goes
 *  on lines of its own under it. The backend's one string, "Accepted (No fix yet; review 2026-11-17)", put a sentence
 *  in brackets inside the value. Other proposals keep the backend's words. */
export function proposalAfter(p: Pick<Proposal, 'action' | 'after' | 'fields'>): { after: string; lines: string[] } {
  const f = p.fields
  if (p.action !== 'set_status' || !f.status) return { after: p.after, lines: [] }
  const head = [STATUS_LABEL[f.status]]
  if (f.justification) head.push(JUSTIFICATION_LABEL[f.justification].toLowerCase())
  if (f.review_date) head.push(`review ${f.review_date}`)
  const lines = [f.reason, f.note, f.compensating_control && `Control: ${f.compensating_control}`]
  return { after: head.join(', '), lines: lines.filter((x): x is string => Boolean(x)) }
}

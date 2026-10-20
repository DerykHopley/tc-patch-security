// Check now's one piece of logic (B59, #103, DESIGN.md §5.10 and §5.12). The dashboard's Data freshness card and
// Settings' Refresh runs card both press it, so both say the same words and wait the same way. A plain function, so
// `npm test` checks it without a browser; components/CheckNow.tsx wraps it in a hook.
import type { CheckReply, RefreshResult } from './api.ts'
import { replyLine, type Tone } from './freshness.ts'

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

export interface CheckOutcome {
  line: { tone: Tone; text: string }
  ran: boolean // the server ran a check (ok, partial or failed); false for a refusal or no answer
  result: RefreshResult | null // that run's result when it ran
}

/** Ask the server for a check. After a run that wrote data (ok: partial too) every view on screen loads again
 *  before the line is said, so the cards above the button have their new size before the next click (#67).
 *  `owner` false (B50): anyone else's alerts are in Patch only, and the line says so. Never throws. */
export async function runCheck(
  deps: { checkNow: () => Promise<CheckReply>; announce: () => Promise<void> },
  owner = true,
): Promise<CheckOutcome> {
  try {
    const reply = await deps.checkNow()
    if (reply.ran && reply.result?.ok) await deps.announce()
    return { line: replyLine(reply, owner), ran: reply.ran, result: reply.ran ? reply.result : null }
  } catch (e) {
    return { line: { tone: 'error', text: message(e) }, ran: false, result: null }
  }
}

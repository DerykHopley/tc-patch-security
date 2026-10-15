import type { Verdict } from './api.ts'

// The version check's verdicts and their words (A15). Plain TypeScript, so the page context can use them under
// node --test; components/Verdict.tsx re-exports them next to the chip.
export const VERDICTS: Verdict[] = ['affected', 'not_affected', 'unknown']
export const VERDICT_LABEL: Record<Verdict, string> = {
  affected: 'Affected',
  not_affected: 'Not affected',
  unknown: 'Unknown',
}

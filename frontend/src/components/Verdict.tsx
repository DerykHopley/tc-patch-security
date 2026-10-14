import type { ProductUsage, Verdict, WhoActs } from '../api.ts'

// Am I affected? (A15): the version check's verdict, shown the same way on the CVEs page and in Patch's cards.
// The verdict is advice; the CVE's status stays the user's decision. Never colour alone: the chip carries the word.

export const VERDICTS: Verdict[] = ['affected', 'not_affected', 'unknown']
export const VERDICT_LABEL: Record<Verdict, string> = {
  affected: 'Affected',
  not_affected: 'Not affected',
  unknown: 'Unknown',
}
export const WHO_ACTS_LABEL: Record<WhoActs, string> = { you: 'you', upstream: 'upstream', vendor: 'the vendor' }
export const WHO_ACTS_TITLE: Record<WhoActs, string> = {
  you: 'You run it yourself: upgrade it.',
  upstream: 'It comes in through another package: that package has to update.',
  vendor: 'A hosted service: the vendor has to fix it.',
}
export const USAGES: ProductUsage[] = ['self_hosted', 'library', 'transitive', 'hosted']
export const USAGE_LABEL: Record<ProductUsage, string> = {
  self_hosted: 'Self-hosted app',
  library: 'Library',
  transitive: 'Comes in through another package',
  hosted: 'Hosted service',
}

export function VerdictChip({ verdict }: { verdict: Verdict }) {
  return <span className={`chip verdict ${verdict}`}>{VERDICT_LABEL[verdict]}</span>
}

/** The reason, the fixed version and who acts, under the chip. */
export function VerdictFacts({ reason, fixed, who }: { reason: string; fixed: string | null; who: WhoActs }) {
  return (
    <>
      <span className="verdict-reason">{reason}</span>
      {fixed && <span className="verdict-fact">Fixed in {fixed}</span>}
      <span className="verdict-fact" title={WHO_ACTS_TITLE[who]}>
        Who acts: {WHO_ACTS_LABEL[who]}
      </span>
    </>
  )
}

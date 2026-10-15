import type { Severity } from '../api.ts'
import { sevLabel } from '../severity.ts'

// Severity as a word plus a swatch from the severity ramp (DESIGN.md §3.2), so it never relies on colour alone.
// The one badge for every page and the chat: the CVEs table, the dashboard's Top 5, sources and tool cards.
export function SeverityBadge({ severity, cvss }: { severity: Severity | 'NONE' | null; cvss?: number | null }) {
  return (
    <span className={`sev sev-${(severity ?? 'none').toLowerCase()}`}>
      <span className="swatch" aria-hidden="true" />
      {severity ? sevLabel(severity) : 'Unscored'}
      {cvss != null && <span className="cvss">{cvss.toFixed(1)}</span>}
    </span>
  )
}

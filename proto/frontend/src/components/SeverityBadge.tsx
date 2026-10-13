import type { Severity } from "../api";

// Severity as text plus a ramp swatch, so it never relies on colour alone.
export function SeverityBadge({ severity, cvss }: { severity: Severity | null; cvss?: number | null }) {
  const label = severity ? severity[0] + severity.slice(1).toLowerCase() : "Unscored";
  return (
    <span className={`sev sev-${(severity ?? "none").toLowerCase()}`}>
      <span className="swatch" aria-hidden="true" />
      {label}
      {cvss != null && <span className="cvss">{cvss.toFixed(1)}</span>}
    </span>
  );
}

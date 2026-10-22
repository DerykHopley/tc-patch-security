// How Patch pitches an answer (A19). Same facts and sources at every level; only the wording changes.
// Its own module (no API calls), so pure modules and their node tests can import it; api.ts re-exports it.
export type ExplainLevel = 'simple' | 'normal' | 'deep_dive'

export const EXPLAIN_LEVELS: { id: ExplainLevel; label: string; what: string }[] = [
  { id: 'simple', label: 'Simple', what: 'Plain words and everyday comparisons.' },
  { id: 'normal', label: 'Normal', what: 'Clear and direct, for developers.' },
  { id: 'deep_dive', label: 'Deep dive', what: 'The technical detail: CWE, attack path, CVSS vector.' },
]

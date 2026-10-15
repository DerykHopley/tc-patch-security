import type { Severity } from './api.ts'

// Worst first: the order of the severity filter, the stacked bars and their legend.
export const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
// NONE: NVD scored the CVE and found nothing to score (tool results carry it as is).
export const sevLabel = (s: Severity | 'NONE') => s[0] + s.slice(1).toLowerCase()

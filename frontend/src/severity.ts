import type { Severity } from './api.ts'

// Worst first: the order of the severity filter, the stacked bars and their legend.
export const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
export const sevLabel = (s: Severity) => s[0] + s.slice(1).toLowerCase()

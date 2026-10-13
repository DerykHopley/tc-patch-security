import type { Severity } from "./api";

export const SEVERITIES: Severity[] = ["CRITICAL", "HIGH", "MEDIUM", "LOW"];
export const sevLabel = (s: Severity) => s[0] + s.slice(1).toLowerCase();

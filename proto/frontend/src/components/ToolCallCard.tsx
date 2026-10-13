import type { Severity, ToolCallRecord } from "../api";
import { SeverityBadge } from "./SeverityBadge";

interface CveResult {
  id: string; product: string; published: string; severity: Severity | null; cvss: number | null;
  cwes: string[]; owasp: { code: string; title: string; url: string } | null; url: string;
  kev: { date_added: string; due: string; ransomware: string } | null;
  watch_status: "open" | "fixed" | "not_affected" | "not_watched";
}

interface WeaknessResult {
  kind: "cwe" | "atlas_technique"; id: string; url: string; name?: string;
  category?: { code: string; title: string; url: string } | null; cves_in_snapshot?: number;
  tactics?: string[]; maturity?: string;
  mitigations?: { id: string; name: string }[];
  cited_by_llm_top10?: { code: string; title: string }[];
}

const STATUS_LABEL = { open: "Open", fixed: "Fixed", not_affected: "Not affected", not_watched: "Not watched" };

function CveCard({ r }: { r: CveResult }) {
  return (
    <div className="result-card">
      <p className="result-title">
        <a href={r.url} target="_blank" rel="noreferrer">{r.id}</a> · {r.product}
      </p>
      <div className="badges">
        <SeverityBadge severity={r.severity} cvss={r.cvss} />
        {r.kev && <span className="chip kev">CISA KEV · due {r.kev.due}</span>}
        <span className="chip">{STATUS_LABEL[r.watch_status]}</span>
      </div>
      <p className="meta">
        Published {r.published} · {r.cwes.join(", ") || "no CWE"}
        {r.owasp && <> · <a href={r.owasp.url} target="_blank" rel="noreferrer">{r.owasp.title}</a></>}
      </p>
    </div>
  );
}

function WeaknessCard({ r }: { r: WeaknessResult }) {
  if (r.kind === "cwe") {
    return (
      <div className="result-card">
        <p className="result-title"><a href={r.url} target="_blank" rel="noreferrer">{r.id}</a></p>
        <p className="meta">
          {r.category ? <>OWASP 2025: <a href={r.category.url} target="_blank" rel="noreferrer">{r.category.title}</a></>
            : "Not in any OWASP Top 10 2025 category"} · {r.cves_in_snapshot} CVEs in the snapshot
        </p>
      </div>
    );
  }
  return (
    <div className="result-card">
      <p className="result-title"><a href={r.url} target="_blank" rel="noreferrer">{r.id} {r.name}</a></p>
      <p className="meta">{r.tactics?.join(", ")} · {r.maturity}</p>
      {!!r.cited_by_llm_top10?.length && (
        <p className="meta">Cited by: {r.cited_by_llm_top10.map((c) => c.title).join(", ")}</p>
      )}
      {!!r.mitigations?.length && (
        <ul className="compact">{r.mitigations.map((m) => <li key={m.id}>{m.id} {m.name}</li>)}</ul>
      )}
    </div>
  );
}

// U4, T6: one card per tool call with its name, arguments, status and result. Errors in red.
export function ToolCallCard({ call }: { call: ToolCallRecord }) {
  const r = call.result;
  let body = null;
  if (r && call.name === "lookup_cve") body = <CveCard r={r as unknown as CveResult} />;
  else if (r && call.name === "explain_weakness") body = <WeaknessCard r={r as unknown as WeaknessResult} />;
  else if (r && call.name === "update_watchlist") body = <p className="result-title">{String(r.message)}</p>;
  return (
    <article className={`tool-card ${call.status}`}>
      <header>
        <code>{call.name}</code>
        <span className={`status ${call.status}`}>{call.status}</span>
        <span className="meta">{call.duration_ms.toFixed(1)} ms</span>
      </header>
      <pre className="args">{JSON.stringify(call.args, null, 2)}</pre>
      {call.error && (
        <p className="tool-error"><strong>{call.error.code}</strong>: {call.error.message}</p>
      )}
      {body}
      {r && (
        <details>
          <summary>Raw result</summary>
          <pre>{JSON.stringify(r, null, 2)}</pre>
        </details>
      )}
    </article>
  );
}

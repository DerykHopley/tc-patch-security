import type { DocType, Source } from "../api";
import { SeverityBadge } from "./SeverityBadge";

const DOC_LABEL: Record<DocType, string> = {
  owasp_llm: "OWASP LLM Top 10",
  owasp_web: "OWASP Top 10",
  atlas_technique: "ATLAS technique",
  atlas_mitigation: "ATLAS mitigation",
  atlas_case: "ATLAS case study",
  cve: "CVE",
};

// U3: the numbered sources behind the selected answer. Ids match the [n] links in the answer.
export function SourcesPanel({ sources, idPrefix = "source-" }: { sources: Source[]; idPrefix?: string }) {
  return (
    <section className="panel">
      <h2>Sources</h2>
      {sources.length === 0 ? (
        <p className="muted">No sources for this answer.</p>
      ) : (
        <ol className="sources">
          {sources.map((s) => (
            <li key={s.chunk_id} id={`${idPrefix}${s.n}`} className="source">
              <div className="source-head">
                <span className="badge">{s.n}</span>
                <a href={s.url} target="_blank" rel="noreferrer">{s.title}</a>
              </div>
              <div className="meta">
                {DOC_LABEL[s.doc_type]}
                {s.section && <> · {s.section}</>}
                {s.date && <> · {s.date}</>}
                {s.score !== null && <> · score {s.score.toFixed(3)}</>}
              </div>
              {s.doc_type === "cve" && (
                <div className="badges">
                  <SeverityBadge severity={s.severity} cvss={s.cvss} />
                  {s.kev && <span className="chip kev">CISA KEV</span>}
                </div>
              )}
              <p className="snippet">{s.snippet}</p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

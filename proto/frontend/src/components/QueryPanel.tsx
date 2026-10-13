import type { QueryInfo } from "../api";

// U5: how search_security translated the question: rewrites (Q-T3) and filters (S1, S3, S4).
export function QueryPanel({ query }: { query: QueryInfo }) {
  const filters = Object.entries(query.filters);
  return (
    <section className="panel">
      <h2>Query</h2>
      <dl className="query">
        <dt>Semantic query</dt>
        <dd>{query.semantic_query}</dd>
        <dt>Rewrites</dt>
        <dd>
          <ul>
            {query.rewrites.map((r) => <li key={r}>{r}</li>)}
          </ul>
        </dd>
        <dt>Filters</dt>
        <dd>
          {filters.length === 0
            ? <span className="muted">none</span>
            : filters.map(([k, v]) => <span key={k} className="chip">{k}: {v}</span>)}
        </dd>
        {query.dropped_filters.length > 0 && (
          <>
            <dt>Dropped filters</dt>
            <dd>{query.dropped_filters.map((f) => <span key={f} className="chip warn">{f}</span>)}</dd>
          </>
        )}
      </dl>
      {query.relaxed && (
        <p className="notice">Relaxed: the filters left no results, so search ran again without them.</p>
      )}
    </section>
  );
}

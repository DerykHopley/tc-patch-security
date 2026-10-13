import { useCallback, useEffect, useState } from "react";
import {
  ApiError, cves as fetchCves, dashboard as fetchDashboard, setStatus, setWatchlist,
  type CveQuery, type CveRow, type CveStatus, type Dashboard as DashboardData, type Severity,
} from "../api";
import { SEVERITIES, sevLabel } from "../severity";
import { Bars, ChartCard, Columns, SeverityLegend, StackedBars, Tooltip, type Tip } from "./charts";
import { SeverityBadge } from "./SeverityBadge";

const PAGE = 25;
const STATUS_LABEL: Record<CveStatus, string> = { open: "Open", fixed: "Fixed", not_affected: "Not affected" };

// U7–U10: the open-CVE dashboard for the watchlist.
export function Dashboard({ onAsk }: { onAsk: (question: string) => void }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [rows, setRows] = useState<{ total: number; rows: CveRow[] } | null>(null);
  const [query, setQuery] = useState<CveQuery>({ status: "open", offset: 0 });
  const [error, setError] = useState<string | null>(null);
  const [tip, setTip] = useState<Tip | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const fail = (e: unknown) => setError(e instanceof ApiError ? e.message : "Something went wrong. Try again.");

  const loadSummary = useCallback(() => fetchDashboard().then(setData).catch(fail), []);
  const loadRows = useCallback(() => fetchCves({ ...query, limit: PAGE }).then(setRows).catch(fail), [query]);

  useEffect(() => { loadSummary(); }, [loadSummary]);
  useEffect(() => { loadRows(); }, [loadRows]);

  async function mark(id: string, status: CveStatus) {
    setBusy(id);
    try {
      await setStatus(id, status);
      await Promise.all([loadSummary(), loadRows()]);
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  }

  const filter = (patch: Partial<CveQuery>) => setQuery((q) => ({ ...q, ...patch, offset: 0 }));

  if (error && !data) return <p className="dash-error">{error}</p>;
  if (!data) return <p className="muted dash-loading"><span className="spinner" /> Loading the dashboard…</p>;

  const k = data.kpis;
  const overdue = k.kev_next_due && k.kev_next_due.due < data.as_of;
  const watchedNames = data.watchlist.map((id) => data.products.find((p) => p.id === id)?.name ?? id);

  return (
    <div className="dashboard">
      {error && <p className="dash-error" role="alert">{error} <button onClick={() => setError(null)}>Dismiss</button></p>}
      <p className="meta">
        Watching {watchedNames.join(", ") || "nothing"} · data as of {data.as_of}
      </p>

      <div className="tiles">
        <div className="tile">
          <span className="tile-value">{k.open}</span>
          <span className="tile-label">Open CVEs</span>
        </div>
        <div className="tile">
          <span className="tile-value">{k.critical}</span>
          <span className="tile-label">Open and critical</span>
        </div>
        <div className={`tile${k.kev ? " alert" : ""}`}>
          <span className="tile-value">{k.kev}</span>
          <span className="tile-label">Open and exploited in the wild (CISA KEV)</span>
          {k.kev_next_due && (
            <span className="tile-note">
              {overdue ? "⚠ Overdue since" : "Next due"} {k.kev_next_due.due} ({k.kev_next_due.cve})
            </span>
          )}
        </div>
        <div className="tile">
          <span className="tile-value">{k.new_30d}</span>
          <span className="tile-label">New in the last 30 days</span>
        </div>
      </div>

      <div className="dash-grid">
        <div className="dash-main">
          <ChartCard
            title="Open CVEs by product and severity"
            legend={<SeverityLegend />}
            table={
              <table className="data">
                <thead><tr><th>Product</th>{SEVERITIES.map((s) => <th key={s}>{sevLabel(s)}</th>)}<th>Total</th></tr></thead>
                <tbody>{data.by_product.map((p) => (
                  <tr key={p.product}><td>{p.name}</td>{SEVERITIES.map((s) => <td key={s}>{p[s]}</td>)}<td>{p.total}</td></tr>
                ))}</tbody>
              </table>
            }
          >
            <StackedBars rows={data.by_product} onTip={setTip} />
          </ChartCard>

          <ChartCard
            title="CVEs per month, watched products"
            note="All statuses, by publication date."
            table={
              <table className="data">
                <thead><tr><th>Month</th><th>CVEs</th></tr></thead>
                <tbody>{data.per_month.map((m) => <tr key={m.month}><td>{m.month}</td><td>{m.count}</td></tr>)}</tbody>
              </table>
            }
          >
            <Columns data={data.per_month} onTip={setTip} />
          </ChartCard>

          <ChartCard
            title="Open CVEs by OWASP Top 10 category"
            note={data.owasp_unmapped ? `${data.owasp_unmapped} open CVEs have no CWE in OWASP's lists.` : undefined}
            table={
              <table className="data">
                <thead><tr><th>Category</th><th>Open CVEs</th></tr></thead>
                <tbody>{data.by_owasp.map((o) => <tr key={o.code}><td>{o.title}</td><td>{o.count}</td></tr>)}</tbody>
              </table>
            }
          >
            <Bars data={data.by_owasp.map((o) => ({ label: o.title.replace(":2025", ""), count: o.count }))} onTip={setTip} />
          </ChartCard>

          <CveTable rows={rows} query={query} products={data.products.filter((p) => data.watchlist.includes(p.id))}
            busy={busy} onFilter={filter} onPage={(offset) => setQuery((q) => ({ ...q, offset }))}
            onMark={mark} onAsk={(id) => onAsk(`Explain ${id} and how to defend against it.`)} />
        </div>

        <aside className="dash-side">
          {/* key: a new saved watchlist resets the editor's unsaved picks */}
          <WatchlistEditor key={data.watchlist.join()} data={data} onSaved={() => Promise.all([loadSummary(), loadRows()])} onError={fail} />
          <section className="panel">
            <h2>Latest AI incidents (MITRE ATLAS)</h2>
            <ul className="incidents">
              {data.latest_incidents.map((c) => (
                <li key={c.id}>
                  <a href={c.url} target="_blank" rel="noreferrer">{c.name}</a>
                  <span className="meta">{c.date} · {c.id}</span>
                </li>
              ))}
            </ul>
          </section>
          <section className="panel">
            <h2>Data freshness</h2>
            <ul className="freshness">
              {data.freshness.map((s) => (
                <li key={s.name}>
                  <a href={s.url} target="_blank" rel="noreferrer">{s.name}</a>
                  <span className="meta">{s.count.toLocaleString()} items · {s.licence} · retrieved {s.retrieved}</span>
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
      <Tooltip tip={tip} />
    </div>
  );
}

function CveTable({ rows, query, products, busy, onFilter, onPage, onMark, onAsk }: {
  rows: { total: number; rows: CveRow[] } | null;
  query: CveQuery;
  products: { id: string; name: string }[];
  busy: string | null;
  onFilter: (patch: Partial<CveQuery>) => void;
  onPage: (offset: number) => void;
  onMark: (id: string, status: CveStatus) => void;
  onAsk: (id: string) => void;
}) {
  const offset = query.offset ?? 0;
  return (
    <section className="panel">
      <h2>CVEs on your watchlist</h2>
      <div className="filters">
        <label>Product
          <select id="f-product" value={query.product ?? ""} onChange={(e) => onFilter({ product: e.target.value || undefined })}>
            <option value="">All watched</option>
            {products.map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
        </label>
        <label>Severity
          <select id="f-severity" value={query.severity_min ?? ""}
            onChange={(e) => onFilter({ severity_min: (e.target.value || undefined) as Severity | undefined })}>
            <option value="">Any</option>
            {SEVERITIES.map((s) => <option key={s} value={s}>{sevLabel(s)} or worse</option>)}
          </select>
        </label>
        <label>Status
          <select id="f-status" value={query.status ?? "open"} onChange={(e) => onFilter({ status: e.target.value as CveQuery["status"] })}>
            <option value="open">Open</option>
            <option value="fixed">Fixed</option>
            <option value="not_affected">Not affected</option>
            <option value="all">All</option>
          </select>
        </label>
        <span className="meta">{rows ? `${rows.total} CVEs · KEV first, then highest score` : "Loading…"}</span>
      </div>
      <div className="table-scroll">
        <table className="cves">
          <thead>
            <tr><th>CVE</th><th>Product</th><th>Severity</th><th>Published</th><th>OWASP</th><th>Status</th><th>Actions</th></tr>
          </thead>
          <tbody>
            {rows?.rows.map((r) => (
              <tr key={r.id} className={r.kev ? "kev-row" : undefined}>
                <td>
                  <a href={r.url} target="_blank" rel="noreferrer">{r.id}</a>
                  {r.kev && <span className="chip kev" title={`CISA KEV, remediation due ${r.kev_due}`}>KEV</span>}
                  <div className="summary">{r.summary}</div>
                </td>
                <td>{r.product_name}</td>
                <td><SeverityBadge severity={r.severity} cvss={r.cvss} /></td>
                <td className="num">{r.published}</td>
                <td title={r.owasp_title ?? undefined}>{r.owasp ?? "—"}</td>
                <td>{STATUS_LABEL[r.status]}</td>
                <td className="actions">
                  {r.status === "open" ? (
                    <>
                      <button disabled={busy === r.id} onClick={() => onMark(r.id, "fixed")}>Mark fixed</button>
                      <button disabled={busy === r.id} onClick={() => onMark(r.id, "not_affected")}>Not affected</button>
                    </>
                  ) : (
                    <button disabled={busy === r.id} onClick={() => onMark(r.id, "open")}>Reopen</button>
                  )}
                  <button onClick={() => onAsk(r.id)}>Ask about this</button>
                </td>
              </tr>
            ))}
            {rows && rows.rows.length === 0 && (
              <tr><td colSpan={7} className="muted">No CVEs match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      {rows && rows.total > PAGE && (
        <div className="pager">
          <button disabled={offset === 0} onClick={() => onPage(Math.max(0, offset - PAGE))}>Previous</button>
          <span className="meta">{offset + 1}–{Math.min(offset + PAGE, rows.total)} of {rows.total}</span>
          <button disabled={offset + PAGE >= rows.total} onClick={() => onPage(offset + PAGE)}>Next</button>
        </div>
      )}
    </section>
  );
}

function WatchlistEditor({ data, onSaved, onError }: {
  data: DashboardData; onSaved: () => Promise<unknown>; onError: (e: unknown) => void;
}) {
  const [picked, setPicked] = useState<string[]>(data.watchlist);
  const [saving, setSaving] = useState(false);
  const changed = picked.slice().sort().join() !== data.watchlist.slice().sort().join();

  async function save() {
    setSaving(true);
    try {
      await setWatchlist(picked);
      await onSaved();
    } catch (e) {
      onError(e);
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="panel">
      <h2>Watchlist</h2>
      <ul className="watchlist">
        {data.products.map((p) => (
          <li key={p.id}>
            <label>
              <input type="checkbox" id={`watch-${p.id}`} checked={picked.includes(p.id)}
                onChange={(e) => setPicked((w) => (e.target.checked ? [...w, p.id] : w.filter((x) => x !== p.id)))} />
              {p.name}
            </label>
          </li>
        ))}
      </ul>
      <button type="submit" disabled={!changed || saving} onClick={save}>{saving ? "Saving…" : "Save watchlist"}</button>
    </section>
  );
}

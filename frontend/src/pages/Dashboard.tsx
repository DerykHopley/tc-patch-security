import { useCallback, useEffect, useState, type FormEvent, type MouseEvent } from 'react'
import {
  cves as fetchCves,
  dashboard as fetchDashboard,
  setWatchlist,
  type CveRow,
  type Dashboard as DashboardData,
} from '../api.ts'
import { SeverityBadge } from '../chat/SeverityBadge.tsx'
import { Bars, ChartCard, Columns, SeverityLegend, StackedBars, Tooltip, type Tip } from '../components/charts.tsx'
import { WarningIcon } from '../components/Icons.tsx'
import { PossibleMatch } from '../components/SnapshotFacts.tsx'
import { WelcomeBanner } from '../components/WelcomeBanner.tsx'
import { followLink } from '../route.ts'
import { SEVERITIES, sevLabel } from '../severity.ts'
import '../styles/dashboard.css'

// The dashboard (DESIGN.md §5): "how exposed am I?". Patch's welcome banner, four candy tiles (each a link to the
// CVEs page with its filter), three charts and the top 5 open CVEs; beside them the watchlist editor, the latest
// ATLAS incidents and the data's freshness. The full CVE table is the CVEs page (A04b).
// Every change goes to the backend's one state module, which the chat's tools share; then tiles and charts reload.

type Note = { ok: boolean; text: string }
const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

// onNavigate: opens an in-app link (a tile, "See all CVEs"). onAskPatch: the welcome banner's "Ask Patch".
export function DashboardPage({ onNavigate, onAskPatch }: {
  onNavigate: (href: string) => void
  onAskPatch: () => void
}) {
  const [data, setData] = useState<DashboardData | null>(null)
  const [top, setTop] = useState<CveRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [watchNote, setWatchNote] = useState<Note | null>(null) // kept here: saving remounts the editor
  const [tip, setTip] = useState<Tip | null>(null)

  // The top 5 come from the table's own endpoint, so they are always the CVEs page's first 5 rows.
  const load = useCallback(
    () =>
      Promise.all([
        fetchDashboard().then(setData),
        fetchCves({ status: 'open', limit: 5, offset: 0 }).then((p) => setTop(p.rows)),
      ]),
    [],
  )

  useEffect(() => {
    load().catch((e: unknown) => setError(message(e)))
  }, [load])

  async function saveWatchlist(products: string[]) {
    setWatchNote(null)
    try {
      await setWatchlist(products)
      await load()
      setWatchNote({ ok: true, text: 'Saved.' })
    } catch (e) {
      setWatchNote({ ok: false, text: message(e) })
    }
  }

  if (!data) {
    return (
      <div className="page dashboard">
        <WelcomeBanner onAsk={onAskPatch} />
        {error ? (
          <p className="dash-error" role="alert">
            {error}
          </p>
        ) : (
          <p className="meta">Loading the dashboard…</p>
        )}
      </div>
    )
  }

  return (
    <div className="page dashboard">
      <WelcomeBanner onAsk={onAskPatch} />
      {error && (
        <p className="dash-error" role="alert">
          {error}{' '}
          <button type="button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </p>
      )}
      <Tiles data={data} onNavigate={onNavigate} />
      <div className="dash-grid">
        <div className="dash-main">
          <ChartCard
            id="chart-product"
            title="Open CVEs by product and severity"
            legend={<SeverityLegend />}
            table={
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">Product</th>
                    {SEVERITIES.map((s) => (
                      <th key={s} scope="col">
                        {sevLabel(s)}
                      </th>
                    ))}
                    <th scope="col">Total</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_product.map((p) => (
                    <tr key={p.product}>
                      <th scope="row">{p.name}</th>
                      {SEVERITIES.map((s) => (
                        <td key={s}>{p[s]}</td>
                      ))}
                      <td>{p.total}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            }
          >
            <StackedBars rows={data.by_product} onTip={setTip} />
          </ChartCard>
          <ChartCard
            id="chart-month"
            title="CVEs per month"
            note="Watched products, all statuses, by publication date."
            table={
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">Month</th>
                    <th scope="col">CVEs</th>
                  </tr>
                </thead>
                <tbody>
                  {data.per_month.map((m) => (
                    <tr key={m.month}>
                      <th scope="row">{m.month}</th>
                      <td>{m.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            }
          >
            <Columns data={data.per_month} onTip={setTip} />
          </ChartCard>
          <ChartCard
            id="chart-owasp"
            title="Open CVEs by OWASP category"
            note={
              data.owasp_unmapped > 0 ? `${data.owasp_unmapped} open CVEs have no CWE in OWASP's lists.` : undefined
            }
            table={
              <table className="data">
                <thead>
                  <tr>
                    <th scope="col">Category</th>
                    <th scope="col">Open CVEs</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_owasp.map((o) => (
                    <tr key={o.code}>
                      <th scope="row">{o.title}</th>
                      <td>{o.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            }
          >
            <Bars data={data.by_owasp.map((o) => ({ label: o.title.replace(':2025', ''), count: o.count }))} onTip={setTip} />
          </ChartCard>
          <TopCves rows={top} onNavigate={onNavigate} />
        </div>
        <aside className="dash-side" aria-label="Dashboard side panels">
          {/* key: a newly saved watchlist resets the editor's unsaved picks */}
          <WatchlistEditor key={data.watchlist.join()} data={data} note={watchNote} onSave={saveWatchlist} />
          <section className="card" aria-labelledby="incidents-title">
            <h2 id="incidents-title">Latest AI incidents (MITRE ATLAS)</h2>
            <ul className="side-list">
              {data.latest_incidents.map((c) => (
                <li key={c.id}>
                  <a href={c.url} target="_blank" rel="noreferrer">
                    {c.name}
                  </a>
                  <span className="meta">
                    {c.date} · {c.id}
                  </span>
                </li>
              ))}
            </ul>
          </section>
          <section className="card" aria-labelledby="freshness-title">
            <h2 id="freshness-title">Data freshness</h2>
            <ul className="side-list">
              {data.freshness.map((s) => (
                <li key={s.id}>
                  <a href={s.url} target="_blank" rel="noreferrer">
                    {s.name}
                  </a>
                  <span className="meta">
                    {s.count.toLocaleString('en')} items · {s.licence} ·{' '}
                    {s.as_of && s.as_of !== s.retrieved ? `as of ${s.as_of}, ` : ''}retrieved {s.retrieved}
                  </span>
                  <span className="meta attribution">{s.attribution}</span>
                  {s.notice && <span className="meta freshness-notice">{s.notice}</span>}
                </li>
              ))}
            </ul>
          </section>
        </aside>
      </div>
      <Tooltip tip={tip} />
    </div>
  )
}

// Each tile links to the CVEs page with the tile's filter (A04b), so the number leads to its rows.
function Tiles({ data, onNavigate }: { data: DashboardData; onNavigate: (href: string) => void }) {
  const k = data.kpis
  const overdue = k.kev_next_due !== null && k.kev_next_due.due < data.as_of
  const go = (e: MouseEvent<HTMLAnchorElement>) => followLink(e, onNavigate)
  return (
    <section className="tiles" aria-label="Summary">
      <a className="tile tile-open" href="/cves" onClick={go}>
        <span className="tile-value">{k.open}</span>
        <span className="tile-label">Open CVEs</span>
      </a>
      <a className="tile tile-critical" href="/cves?severity=CRITICAL" onClick={go}>
        <span className="tile-value">{k.critical}</span>
        <span className="tile-label">Open and critical</span>
      </a>
      {/* Wiggles (DESIGN.md §7.1) only while open KEV CVEs exist. */}
      <a className={`tile tile-kev${k.kev > 0 ? ' alert' : ''}`} href="/cves?kev=1" onClick={go}>
        <span className="tile-value">{k.kev}</span>
        <span className="tile-label">Open and exploited in the wild (CISA KEV)</span>
        {k.kev_next_due && (
          <span className="tile-note">
            {overdue && <WarningIcon />}
            {overdue ? 'Overdue since' : 'Next due'} {k.kev_next_due.due} ({k.kev_next_due.cve})
          </span>
        )}
      </a>
      <a className="tile tile-new" href={`/cves?status=all&since=${k.new_since}`} onClick={go}>
        <span className="tile-value">{k.new_30d}</span>
        <span className="tile-label">New in the last 30 days</span>
      </a>
    </section>
  )
}

// The work list's head: the CVEs page's first 5 rows, in its order, with a link to the rest.
function TopCves({ rows, onNavigate }: { rows: CveRow[] | null; onNavigate: (href: string) => void }) {
  return (
    <section className="card top-cves" aria-labelledby="top-cves-title">
      <h2 id="top-cves-title">Top 5 open CVEs</h2>
      {rows === null ? (
        <p className="meta">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="meta">No open CVEs on your watchlist.</p>
      ) : (
        <ol>
          {rows.map((r) => (
            <li key={r.id}>
              <span className="top-id">
                <a className="cve-id" href={r.url} target="_blank" rel="noreferrer">
                  {r.id}
                </a>
                {r.kev && (
                  <span className="chip kev" title={`CISA KEV, remediation due ${r.kev_due}`}>
                    KEV
                  </span>
                )}
                {r.possible_match && <PossibleMatch />}
              </span>
              <span className="top-product">{r.product_name}</span>
              <SeverityBadge severity={r.severity} cvss={r.cvss} />
            </li>
          ))}
        </ol>
      )}
      <a className="see-all" href="/cves" onClick={(e) => followLink(e, onNavigate)}>
        See all CVEs <span aria-hidden="true">→</span>
      </a>
    </section>
  )
}

function WatchlistEditor({
  data,
  note,
  onSave,
}: {
  data: DashboardData
  note: Note | null
  onSave: (products: string[]) => Promise<void>
}) {
  const [picked, setPicked] = useState<string[]>(data.watchlist)
  const [saving, setSaving] = useState(false)
  const changed = picked.toSorted().join() !== data.watchlist.toSorted().join()

  async function save(e: FormEvent) {
    e.preventDefault()
    setSaving(true)
    await onSave(picked) // never throws: failures come back as the note
    setSaving(false)
  }

  return (
    <section className="card" aria-labelledby="watchlist-title">
      <h2 id="watchlist-title">Watchlist</h2>
      <p className="meta">The products you use. The tiles and the table count only these.</p>
      <form onSubmit={save}>
        <ul className="watchlist">
          {data.products.map((p) => (
            <li key={p.id}>
              <label>
                <input
                  type="checkbox"
                  checked={picked.includes(p.id)}
                  onChange={(e) =>
                    setPicked((w) => (e.target.checked ? [...w, p.id] : w.filter((x) => x !== p.id)))
                  }
                />
                {p.name}
              </label>
            </li>
          ))}
        </ul>
        <button type="submit" disabled={!changed || saving}>
          {saving ? 'Saving…' : 'Save watchlist'}
        </button>
        {note && (
          <p className={note.ok ? 'meta save-note' : 'dash-error save-note'} role={note.ok ? 'status' : 'alert'}>
            {note.text}
          </p>
        )}
      </form>
    </section>
  )
}

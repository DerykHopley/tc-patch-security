import { useCallback, useEffect, useRef, useState, type MouseEvent } from 'react'
import { cves as fetchCves, dashboard as fetchDashboard, type CveRow, type Dashboard as DashboardData } from '../api.ts'
import { SeverityBadge } from '../components/SeverityBadge.tsx'
import { Bars, ChartCard, Columns, SeverityLegend, StackedBars, Tooltip, type Tip } from '../components/charts.tsx'
import { WarningIcon } from '../components/Icons.tsx'
import { OverdueMark, PriorityChip, PriorityReasons } from '../components/Priority.tsx'
import { NoFixMark } from '../components/Decision.tsx'
import { PossibleMatch } from '../components/SnapshotFacts.tsx'
import type { Variant } from '../components/patchPose.ts'
import { WelcomeBanner } from '../components/WelcomeBanner.tsx'
import { OPEN_VIEW, productIds, viewToSearch, type CveView } from '../cveView.ts'
import type { ShownView } from '../pageContext.ts'
import { followLink } from '../route.ts'
import { SEVERITIES, sevLabel } from '../severity.ts'
import { useWatchlistChanged } from '../watchlistEvents.ts'
import '../styles/dashboard.css'

// The dashboard (DESIGN.md §5): "how exposed am I?". Patch's welcome banner, four candy tiles (each a link to the
// CVEs page with its filter), three charts and the top 5 open CVEs; beside them the watchlist as a product filter,
// the latest ATLAS incidents and the data's freshness. The full CVE table is the CVEs page (A04b).
// The watchlist is edited on Settings (A15b); here its chips narrow the tiles, charts and Top 5 to some products.
// The filter lives in the URL only (`/?product=langflow,ollama`): a fresh dashboard shows every watched product.

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

/** The product filter in a query string. Malformed ids are dropped: the URL is text from outside. */
const filterFromSearch = (search: string) => productIds(new URLSearchParams(search).get('product'))

/** The view with the product filter: `{ status: 'open', product: 'a,b' }`. */
const withFilter = (view: CveView, filter: string[]): CveView => ({ ...view, product: filter.join(',') || undefined })

/** A link to the CVEs page for a view, with the filter added: `/cves?product=a,b&kev=1`. */
const cvesLink = (view: CveView, filter: string[]) => `/cves${viewToSearch(withFilter(view, filter))}`

// search: the query string the page was opened with. onNavigate: opens an in-app link (a tile, "See all CVEs").
// onAskPatch: the welcome banner's "Ask Patch". onView: the product filter Patch is told about (A15b).
// patchVariant: Patch's idle animation in the banner, picked on page load (DESIGN.md §8.3).
export function DashboardPage({ search, onNavigate, onAskPatch, onView, patchVariant }: {
  search: string
  onNavigate: (href: string) => void
  onAskPatch: () => void
  onView?: (view: ShownView) => void
  patchVariant: Variant
}) {
  const [filter, setFilter] = useState<string[]>(() => filterFromSearch(search))
  const [data, setData] = useState<DashboardData | null>(null)
  const [top, setTop] = useState<CveRow[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [tip, setTip] = useState<Tip | null>(null)
  const latest = useRef(0) // a quick second click must not be overwritten by the first click's late reply

  // Replace, not push: a filter change isn't a new page for Back, but a reload keeps it.
  const choose = useCallback((next: string[]) => {
    setFilter(next)
    history.replaceState(null, '', window.location.pathname + viewToSearch(withFilter(OPEN_VIEW, next)) + window.location.hash)
  }, [])

  // The backend applies only watched products; the URL follows what it applied, so a product removed from the
  // watchlist (on Settings or by Patch) drops out of the filter. The top 5 come from the table's own endpoint, so
  // they are always the CVEs page's first 5 rows for the same filter.
  const load = useCallback(() => {
    const call = ++latest.current
    return fetchDashboard(filter).then((d) =>
      fetchCves(withFilter(OPEN_VIEW, d.filter), 5).then((page) => {
        if (call !== latest.current) return
        setData(d)
        setTop(page.rows)
        if (d.filter.join() !== filter.join()) choose(d.filter)
      }),
    )
  }, [filter, choose])

  useEffect(() => {
    load().then(
      () => setError(null),
      (e: unknown) => setError(message(e)),
    )
  }, [load])
  useWatchlistChanged(() => {
    load().catch((e: unknown) => setError(message(e)))
  })

  const names = data ? filter.flatMap((id) => data.watched.find((w) => w.product === id)?.name ?? []) : []
  const productName = names.join(' + ')
  useEffect(() => {
    onView?.({ filters: withFilter(OPEN_VIEW, filter), productName })
  }, [filter, productName, onView])

  if (!data) {
    return (
      <div className="page dashboard">
        <WelcomeBanner onAsk={onAskPatch} variant={patchVariant} />
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
      <WelcomeBanner onAsk={onAskPatch} variant={patchVariant} />
      {error && (
        <p className="dash-error" role="alert">
          {error}{' '}
          <button type="button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </p>
      )}
      <Tiles data={data} filter={filter} onNavigate={onNavigate} />
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
            note={`${names.length ? names.join(', ') : 'Watched products'}, all statuses, by publication date.`}
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
          <TopCves rows={top} filter={filter} onNavigate={onNavigate} />
        </div>
        <aside className="dash-side" aria-label="Dashboard side panels">
          <ProductFilter data={data} filter={filter} onChoose={choose} onNavigate={onNavigate} />
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
// With a product filter, each link carries it (A15b), so the CVEs page shows the tile's number.
function Tiles({ data, filter, onNavigate }: {
  data: DashboardData
  filter: string[]
  onNavigate: (href: string) => void
}) {
  const k = data.kpis
  const overdue = k.kev_next_due?.overdue ?? false // against your due date (A16), not CISA's deadline
  const go = (e: MouseEvent<HTMLAnchorElement>) => followLink(e, onNavigate)
  return (
    <section className="tiles" aria-label="Summary">
      <a className="tile tile-open" href={cvesLink(OPEN_VIEW, filter)} onClick={go}>
        <span className="tile-value">{k.open}</span>
        <span className="tile-label">Open CVEs</span>
      </a>
      <a className="tile tile-critical" href={cvesLink({ status: 'open', severity: 'CRITICAL' }, filter)} onClick={go}>
        <span className="tile-value">{k.critical}</span>
        <span className="tile-label">Open and critical</span>
      </a>
      {/* Wiggles (DESIGN.md §7.1) only while open KEV CVEs exist. */}
      <a className={`tile tile-kev${k.kev > 0 ? ' alert' : ''}`} href={cvesLink({ status: 'open', kev: true }, filter)} onClick={go}>
        <span className="tile-value">{k.kev}</span>
        <span className="tile-label">Open and exploited in the wild (CISA KEV)</span>
        {k.kev_next_due && (
          <span className="tile-note">
            {overdue && <WarningIcon />}
            {overdue ? 'Overdue since' : k.kev_next_due.no_fix ? 'No fix yet, decide by' : 'Next due'}{' '}
            {k.kev_next_due.due} ({k.kev_next_due.cve})
          </span>
        )}
      </a>
      <a className="tile tile-new" href={cvesLink({ status: 'all', since: k.new_since }, filter)} onClick={go}>
        <span className="tile-value">{k.new_30d}</span>
        <span className="tile-label">New in the last 30 days</span>
      </a>
    </section>
  )
}

// The work list's head: the CVEs page's first 5 rows, in its order, with a link to the rest.
function TopCves({ rows, filter, onNavigate }: {
  rows: CveRow[] | null
  filter: string[]
  onNavigate: (href: string) => void
}) {
  return (
    <section className="card top-cves" aria-labelledby="top-cves-title">
      <h2 id="top-cves-title">Top 5 open CVEs</h2>
      {rows === null ? (
        <p className="meta">Loading…</p>
      ) : rows.length === 0 ? (
        <p className="meta">{filter.length ? 'No open CVEs for these products.' : 'No open CVEs on your watchlist.'}</p>
      ) : (
        <ol>
          {rows.map((r) => (
            <li key={r.id}>
              <span className="top-id">
                <a className="cve-id" href={r.url} target="_blank" rel="noreferrer">
                  {r.id}
                </a>
                {r.kev && (
                  <span className="chip kev" title={`In CISA KEV: known exploited. KEV deadline ${r.kev_deadline}`}>
                    KEV
                  </span>
                )}
                {r.possible_match && <PossibleMatch />}
              </span>
              <PriorityChip level={r.priority} />
              <span className="top-product">{r.product_name}</span>
              <SeverityBadge severity={r.severity} cvss={r.cvss} />
              <span className="top-due" title={`Your due date: ${r.due_from}`}>
                {r.no_fix ? 'Decide by' : 'Due'} <span className="num">{r.due_date}</span>
                {r.overdue && <OverdueMark />}
                {r.no_fix && <NoFixMark days={r.open_days} />}
              </span>
              <PriorityReasons reasons={r.priority_reasons} />
            </li>
          ))}
        </ol>
      )}
      <a className="see-all" href={cvesLink(OPEN_VIEW, filter)} onClick={(e) => followLink(e, onNavigate)}>
        See all CVEs <span aria-hidden="true">→</span>
      </a>
    </section>
  )
}

// The watchlist as a filter (A15b): "All" and a toggle chip per watched product. Picking every product is the
// same as All, so the URL stays clean. A red dot (and words in its name and title) marks products with open KEV CVEs.
// Editing the watchlist is on Settings.
function Tick({ on }: { on: boolean }) {
  // Picked isn't told by colour alone; aria-pressed says it to screen readers, so the tick is hidden from them.
  return on ? (
    <span className="tick" aria-hidden="true">
      ✓
    </span>
  ) : null
}

function ProductFilter({ data, filter, onChoose, onNavigate }: {
  data: DashboardData
  filter: string[]
  onChoose: (next: string[]) => void
  onNavigate: (href: string) => void
}) {
  function toggle(id: string) {
    const next = new Set(filter)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    const ids = data.watchlist.filter((p) => next.has(p))
    onChoose(ids.length === data.watchlist.length ? [] : ids)
  }
  return (
    <section className="card filter-card" aria-labelledby="watchlist-title">
      <h2 id="watchlist-title">Watchlist</h2>
      {data.watched.length === 0 ? (
        <p className="meta">Your watchlist is empty: add the products you use.</p>
      ) : (
        <fieldset className="product-chips">
          <legend className="meta">Show the tiles, charts and Top 5 for</legend>
          <button type="button" className="product-chip" aria-pressed={filter.length === 0} onClick={() => onChoose([])}>
            <Tick on={filter.length === 0} />
            All
          </button>
          {data.watched.map((p) => {
            const on = filter.includes(p.product)
            const kev = p.kev > 0 ? `${p.name}: open CVEs in CISA KEV` : undefined
            return (
              <button
                key={p.product}
                type="button"
                className="product-chip"
                aria-pressed={on}
                aria-label={kev}
                title={kev}
                onClick={() => toggle(p.product)}
              >
                <Tick on={on} />
                {p.name}
                {kev && <span className="kev-dot" aria-hidden="true" />}
              </button>
            )
          })}
        </fieldset>
      )}
      <a className="edit-link" href="/settings" onClick={(e) => followLink(e, onNavigate)}>
        Edit watchlist in Settings <span aria-hidden="true">→</span>
      </a>
    </section>
  )
}

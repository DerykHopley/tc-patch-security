import { useCallback, useEffect, useState, type FormEvent } from 'react'
import {
  cves as fetchCves,
  dashboard as fetchDashboard,
  setStatus,
  setWatchlist,
  type CvePage,
  type CveQuery,
  type CveStatus,
  type Dashboard as DashboardData,
  type Product,
  type Severity,
} from '../api.ts'
import { WarningIcon } from '../components/Icons.tsx'
import '../styles/dashboard.css'

// The dashboard (DESIGN.md §5): four candy tiles, the CVE table with row actions, the watchlist editor.
// Every change goes to the backend's one state module, which the chat's tools share; then tiles and table reload.
// Charts, side panels and Patch's welcome banner come with ticket "Dashboard: charts and side panels".

const PAGE_SIZE = 25
const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const STATUS_LABEL: Record<CveStatus, string> = { open: 'Open', fixed: 'Fixed', not_affected: 'Not affected' }
const sevLabel = (s: Severity) => s[0] + s.slice(1).toLowerCase()
type Note = { ok: boolean; text: string }
const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

export function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null)
  const [page, setPage] = useState<CvePage | null>(null)
  const [query, setQuery] = useState<CveQuery>({ status: 'open', limit: PAGE_SIZE, offset: 0 })
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)
  const [watchNote, setWatchNote] = useState<Note | null>(null) // kept here: saving remounts the editor

  const loadSummary = useCallback(() => fetchDashboard().then(setData), [])
  const loadRows = useCallback(() => fetchCves(query).then(setPage), [query])

  useEffect(() => {
    loadSummary().catch((e: unknown) => setError(message(e)))
  }, [loadSummary])
  useEffect(() => {
    loadRows().catch((e: unknown) => setError(message(e)))
  }, [loadRows])

  async function mark(id: string, status: CveStatus) {
    setBusy(id)
    try {
      await setStatus(id, status)
      await Promise.all([loadSummary(), loadRows()])
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(null)
    }
  }

  async function saveWatchlist(products: string[]) {
    setWatchNote(null)
    try {
      const { watchlist } = await setWatchlist(products)
      // A filter on a product no longer watched would show nothing: drop it (changing the query reloads the rows).
      setQuery((q) => ({ ...q, offset: 0, product: q.product && watchlist.includes(q.product) ? q.product : undefined }))
      await loadSummary()
      setWatchNote({ ok: true, text: 'Saved.' })
    } catch (e) {
      setWatchNote({ ok: false, text: message(e) })
    }
  }

  const filter = (patch: Partial<CveQuery>) => setQuery((q) => ({ ...q, ...patch, offset: 0 }))

  if (!data) {
    return (
      <div className="page dashboard">
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

  const watched = data.products.filter((p) => data.watchlist.includes(p.id))

  return (
    <div className="page dashboard">
      {error && (
        <p className="dash-error" role="alert">
          {error}{' '}
          <button type="button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </p>
      )}
      <Tiles data={data} />
      <div className="dash-grid">
        <div className="dash-main">
          <CveTable
            page={page}
            query={query}
            products={watched}
            busy={busy}
            onFilter={filter}
            onPage={(offset) => setQuery((q) => ({ ...q, offset }))}
            onMark={mark}
          />
        </div>
        <aside className="dash-side" aria-label="Dashboard side panels">
          {/* key: a newly saved watchlist resets the editor's unsaved picks */}
          <WatchlistEditor key={data.watchlist.join()} data={data} note={watchNote} onSave={saveWatchlist} />
        </aside>
      </div>
    </div>
  )
}

function Tiles({ data }: { data: DashboardData }) {
  const k = data.kpis
  const overdue = k.kev_next_due !== null && k.kev_next_due.due < data.as_of
  return (
    <section className="tiles" aria-label="Summary">
      <div className="tile tile-open">
        <span className="tile-value">{k.open}</span>
        <span className="tile-label">Open CVEs</span>
      </div>
      <div className="tile tile-critical">
        <span className="tile-value">{k.critical}</span>
        <span className="tile-label">Open and critical</span>
      </div>
      {/* Wiggles (DESIGN.md §7.1) only while open KEV CVEs exist. */}
      <div className={`tile tile-kev${k.kev > 0 ? ' alert' : ''}`}>
        <span className="tile-value">{k.kev}</span>
        <span className="tile-label">Open and exploited in the wild (CISA KEV)</span>
        {k.kev_next_due && (
          <span className="tile-note">
            {overdue && <WarningIcon />}
            {overdue ? 'Overdue since' : 'Next due'} {k.kev_next_due.due} ({k.kev_next_due.cve})
          </span>
        )}
      </div>
      <div className="tile tile-new">
        <span className="tile-value">{k.new_30d}</span>
        <span className="tile-label">New in the last 30 days</span>
      </div>
    </section>
  )
}

function SeverityBadge({ severity, cvss }: { severity: Severity | null; cvss: number | null }) {
  // Text plus a ramp swatch: never colour alone.
  return (
    <span className={`sev sev-${(severity ?? 'none').toLowerCase()}`}>
      <span className="swatch" aria-hidden="true" />
      {severity ? sevLabel(severity) : 'Unscored'}
      {cvss !== null && <span className="cvss">{cvss.toFixed(1)}</span>}
    </span>
  )
}

function CveTable({
  page,
  query,
  products,
  busy,
  onFilter,
  onPage,
  onMark,
}: {
  page: CvePage | null
  query: CveQuery
  products: Product[]
  busy: string | null
  onFilter: (patch: Partial<CveQuery>) => void
  onPage: (offset: number) => void
  onMark: (id: string, status: CveStatus) => void
}) {
  const { offset } = query
  return (
    <section className="card" aria-labelledby="cve-table-title">
      <h2 id="cve-table-title">CVEs on your watchlist</h2>
      <div className="filters">
        <label>
          Product
          <select value={query.product ?? ''} onChange={(e) => onFilter({ product: e.target.value || undefined })}>
            <option value="">All watched</option>
            {products.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Severity
          <select
            value={query.severity_min ?? ''}
            onChange={(e) => onFilter({ severity_min: (e.target.value || undefined) as Severity | undefined })}
          >
            <option value="">Any</option>
            {SEVERITIES.map((s) => (
              <option key={s} value={s}>
                {sevLabel(s)} or worse
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={query.status} onChange={(e) => onFilter({ status: e.target.value as CveQuery['status'] })}>
            <option value="open">Open</option>
            <option value="fixed">Fixed</option>
            <option value="not_affected">Not affected</option>
            <option value="all">All</option>
          </select>
        </label>
        <span className="meta" aria-live="polite">
          {page ? `${page.total} CVEs · KEV first, then highest score, then newest` : 'Loading…'}
        </span>
      </div>
      <div className="table-scroll">
        <table className="cves">
          <thead>
            <tr>
              <th scope="col">CVE</th>
              <th scope="col">Product</th>
              <th scope="col">Severity</th>
              <th scope="col">Published</th>
              <th scope="col">OWASP</th>
              <th scope="col">Status</th>
            </tr>
          </thead>
          <tbody>
            {page?.rows.map((r) => (
              <tr key={r.id}>
                <td>
                  <a href={r.url} target="_blank" rel="noreferrer">
                    {r.id}
                  </a>
                  {r.kev && (
                    <span className="chip kev" title={`CISA KEV, remediation due ${r.kev_due}`}>
                      KEV
                    </span>
                  )}
                  <div className="summary">{r.summary}</div>
                </td>
                <td>{r.product_name}</td>
                <td>
                  <SeverityBadge severity={r.severity} cvss={r.cvss} />
                </td>
                <td className="num">{r.published}</td>
                <td title={r.owasp_title ?? undefined}>{r.owasp ?? '—'}</td>
                <td>
                  {/* Status and its actions share a column: the table fits beside the side column. */}
                  <span className="status">{STATUS_LABEL[r.status]}</span>
                  <div className="actions">
                    {r.status === 'open' ? (
                      <>
                        <button
                          type="button"
                          disabled={busy === r.id}
                          aria-label={`Mark ${r.id} fixed`}
                          onClick={() => onMark(r.id, 'fixed')}
                        >
                          Mark fixed
                        </button>
                        <button
                          type="button"
                          disabled={busy === r.id}
                          aria-label={`Mark ${r.id} not affected`}
                          onClick={() => onMark(r.id, 'not_affected')}
                        >
                          Not affected
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        disabled={busy === r.id}
                        aria-label={`Reopen ${r.id}`}
                        onClick={() => onMark(r.id, 'open')}
                      >
                        Reopen
                      </button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {page?.rows.length === 0 && (
              <tr>
                <td colSpan={6} className="meta">
                  No CVEs match these filters.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {page && page.total > PAGE_SIZE && (
        <div className="pager">
          <button
            type="button"
            aria-label="Previous page"
            disabled={offset === 0}
            onClick={() => onPage(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span className="meta">
            {offset + 1}–{Math.min(offset + PAGE_SIZE, page.total)} of {page.total}
          </span>
          <button
            type="button"
            aria-label="Next page"
            disabled={offset + PAGE_SIZE >= page.total}
            onClick={() => onPage(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      )}
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

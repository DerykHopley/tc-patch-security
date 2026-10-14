import { useCallback, useEffect, useState } from 'react'
import {
  cves as fetchCves,
  dashboard as fetchDashboard,
  setStatus,
  type CvePage,
  type CveQuery,
  type CveStatus,
  type Product,
  type Severity,
} from '../api.ts'
import { SeverityBadge } from '../chat/SeverityBadge.tsx'
import { EPSS_URL, epssPercentile, epssScore, PossibleMatch } from '../components/SnapshotFacts.tsx'
import { SEVERITIES, sevLabel } from '../severity.ts'
import '../styles/cves.css'

// The CVEs page (A04b, DESIGN.md §5.9): the CVE table at the page's full width, the work list beside the dashboard's
// "how exposed am I?". Filters live in the URL (`?product=langflow&severity=CRITICAL&status=open&kev=1&since=…`),
// so a tile or a shared link opens the page filtered and a reload keeps the filters. Narrow (a phone, or the chat
// pinned beside it) the rows become stacked cards: the row actions never need sideways scrolling.

const PAGE_SIZE = 25
const STATUSES = ['open', 'fixed', 'not_affected', 'all'] as const
const STATUS_LABEL: Record<CveStatus, string> = { open: 'Open', fixed: 'Fixed', not_affected: 'Not affected' }
const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

type Filters = Omit<CveQuery, 'limit' | 'offset'>

/** The filters in a query string. Anything malformed is dropped: the URL is text from outside. */
function filtersFromSearch(search: string): Filters {
  const p = new URLSearchParams(search)
  const product = p.get('product') ?? ''
  const severity = (p.get('severity') ?? '').toUpperCase() as Severity
  const status = p.get('status') as Filters['status']
  const since = p.get('since') ?? ''
  return {
    product: /^[a-z0-9][a-z0-9.-]{0,40}$/.test(product) ? product : undefined,
    severity_min: SEVERITIES.includes(severity) ? severity : undefined,
    status: STATUSES.includes(status) ? status : 'open',
    kev: p.get('kev') === '1' ? true : undefined,
    published_since: /^\d{4}-\d{2}-\d{2}$/.test(since) ? since : undefined,
  }
}

/** The query string for the filters; the defaults (all watched products, any severity, open) need none. */
function searchFromFilters(f: Filters): string {
  const p = new URLSearchParams()
  if (f.product) p.set('product', f.product)
  if (f.severity_min) p.set('severity', f.severity_min)
  if (f.status !== 'open') p.set('status', f.status)
  if (f.kev) p.set('kev', '1')
  if (f.published_since) p.set('since', f.published_since)
  const s = p.toString()
  return s ? `?${s}` : ''
}

// onAsk: "Ask about this" opens Patch over this page and asks about that CVE (DESIGN.md §6.4).
export function CvesPage({ search, onAsk }: { search: string; onAsk: (cveId: string) => void }) {
  const [filters, setFilters] = useState<Filters>(() => filtersFromSearch(search))
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<CvePage | null>(null)
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState<string | null>(null)

  const loadRows = useCallback(
    () => fetchCves({ ...filters, limit: PAGE_SIZE, offset }).then(setPage),
    [filters, offset],
  )

  useEffect(() => {
    fetchDashboard().then(
      (d) => setProducts(d.products.filter((p) => d.watchlist.includes(p.id))),
      (e: unknown) => setError(message(e)),
    )
  }, [])
  useEffect(() => {
    loadRows().then(
      () => setError(null),
      (e: unknown) => setError(message(e)),
    )
  }, [loadRows])

  function filter(patch: Partial<Filters>) {
    const next = { ...filters, ...patch }
    setFilters(next)
    setOffset(0)
    // Replace, not push: a filter change isn't a new page for Back, but a reload keeps it.
    history.replaceState(null, '', window.location.pathname + searchFromFilters(next) + window.location.hash)
  }

  async function mark(id: string, status: CveStatus) {
    setBusy(id)
    try {
      await setStatus(id, status)
      await loadRows()
    } catch (e) {
      setError(message(e))
    } finally {
      setBusy(null)
    }
  }

  // A product from a link that isn't on the watchlist still shows in the list, so the select says what's filtered.
  const options = filters.product && !products.some((p) => p.id === filters.product)
    ? [...products, { id: filters.product, name: filters.product }]
    : products

  return (
    <div className="page cves-page">
      {error && (
        <p className="dash-error" role="alert">
          {error}{' '}
          <button type="button" onClick={() => setError(null)}>
            Dismiss
          </button>
        </p>
      )}
      <section className="card cves-card" aria-labelledby="cve-table-title">
        <h2 id="cve-table-title">CVEs on your watchlist</h2>
        <div className="filters">
          <label>
            Product
            <select value={filters.product ?? ''} onChange={(e) => filter({ product: e.target.value || undefined })}>
              <option value="">All watched</option>
              {options.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Severity
            <select
              value={filters.severity_min ?? ''}
              onChange={(e) => filter({ severity_min: (e.target.value || undefined) as Severity | undefined })}
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
            <select value={filters.status} onChange={(e) => filter({ status: e.target.value as Filters['status'] })}>
              <option value="open">Open</option>
              <option value="fixed">Fixed</option>
              <option value="not_affected">Not affected</option>
              <option value="all">All</option>
            </select>
          </label>
          <label>
            <input
              type="checkbox"
              checked={filters.kev ?? false}
              onChange={(e) => filter({ kev: e.target.checked || undefined })}
            />
            In CISA KEV only
          </label>
          {filters.published_since && (
            <span className="chip filter-chip">
              Published since {filters.published_since}
              <button
                type="button"
                aria-label={`Clear: published since ${filters.published_since}`}
                title="Clear this filter"
                onClick={() => filter({ published_since: undefined })}
              >
                ✕
              </button>
            </span>
          )}
          <span className="meta" aria-live="polite">
            {page ? `${page.total} CVEs · KEV first, then highest score, then newest` : 'Loading…'}
          </span>
        </div>
        <CveTable page={page} busy={busy} onMark={mark} onAsk={onAsk} />
        <p className="meta epss-credit">
          EPSS by{' '}
          <a href={EPSS_URL} target="_blank" rel="noreferrer">
            FIRST
          </a>
          : the chance of exploitation in the next 30 days, and how that ranks among all scored CVEs.
        </p>
        {page && page.total > PAGE_SIZE && (
          <div className="pager">
            <button
              type="button"
              aria-label="Previous page"
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
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
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Next
            </button>
          </div>
        )}
      </section>
    </div>
  )
}

// data-label names each cell when the rows are stacked cards (the header row is hidden then).
function CveTable({ page, busy, onMark, onAsk }: {
  page: CvePage | null
  busy: string | null
  onMark: (id: string, status: CveStatus) => void
  onAsk: (id: string) => void
}) {
  return (
    <div className="table-scroll">
      <table className="cves">
        <thead>
          <tr>
            <th scope="col">CVE</th>
            <th scope="col">Product</th>
            <th scope="col">Severity</th>
            <th scope="col">Published</th>
            <th scope="col">OWASP</th>
            <th scope="col">
              <abbr title="Exploit Prediction Scoring System: the chance of exploitation in the next 30 days">EPSS</abbr>
            </th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {page?.rows.map((r) => (
            <tr key={r.id}>
              <td className="cve-cell">
                <a href={r.url} target="_blank" rel="noreferrer">
                  {r.id}
                </a>
                {r.kev && (
                  <span className="chip kev" title={`CISA KEV, remediation due ${r.kev_due}`}>
                    KEV
                  </span>
                )}
                {r.possible_match && <PossibleMatch />}
                <div className="summary">{r.summary}</div>
              </td>
              <td data-label="Product">{r.product_name}</td>
              <td data-label="Severity">
                <SeverityBadge severity={r.severity} cvss={r.cvss} />
              </td>
              <td data-label="Published" className="num">
                {r.published}
              </td>
              <td data-label="OWASP" title={r.owasp_title ?? undefined}>
                {r.owasp ?? '—'}
              </td>
              <td data-label="EPSS" className="epss num">
                {r.epss ? (
                  <>
                    {epssScore(r.epss)}
                    <span className="meta">{epssPercentile(r.epss)}</span>
                  </>
                ) : (
                  '—'
                )}
              </td>
              <td data-label="Status" className="status-cell">
                {/* Status and its actions share a column: the table stays narrow enough for the pinned chat. */}
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
                  <button type="button" aria-label={`Ask about this: ${r.id}`} onClick={() => onAsk(r.id)}>
                    Ask about this
                  </button>
                </div>
              </td>
            </tr>
          ))}
          {page?.rows.length === 0 && (
            <tr className="empty">
              <td colSpan={7} className="meta">
                No CVEs match these filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

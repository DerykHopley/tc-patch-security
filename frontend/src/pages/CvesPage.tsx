import { useCallback, useEffect, useRef, useState } from 'react'
import {
  cves as fetchCves,
  dashboard as fetchDashboard,
  markAllSeen,
  setStatus,
  type CvePage,
  type CveRow,
  type DecisionInput,
  type Product,
  type Severity,
  type Verdict,
} from '../api.ts'
import { SeverityBadge } from '../components/SeverityBadge.tsx'
import { EPSS_URL, epssPercentile, epssScore, PossibleMatch } from '../components/SnapshotFacts.tsx'
import { DueFacts, PriorityChip, PriorityReasons } from '../components/Priority.tsx'
import {
  DecisionDialog,
  DecisionHistory,
  DecisionSummary,
  type DecisionRequest,
} from '../components/Decision.tsx'
import { VERDICT_LABEL, VERDICTS, VerdictChip, VerdictFacts } from '../components/Verdict.tsx'
import { ActionButtons, SuggestNotAffected } from '../components/CveActions.tsx'
import { rowActions } from '../cveActions.ts'
import { CveLink } from '../components/CveLink.tsx'
import { Tip } from '../components/Tip.tsx'
import { SEVERITIES, sevLabel } from '../severity.ts'
import { HEADER_TIPS, owaspTip } from '../tips.ts'
import {
  filtersLabel,
  NEW_LABEL,
  NEW_TITLE,
  STATUS_FILTERS,
  STATUS_LABEL,
  statusFilterLabel,
  viewFromSearch,
  viewToSearch,
  type CveView,
  type StatusFilter,
} from '../cveView.ts'
import type { ShownView } from '../pageContext.ts'
import '../styles/cves.css'

// The CVEs page (A04b, DESIGN.md §5.9): the CVE table at the page's full width, the work list beside the dashboard's
// "how exposed am I?". Filters live in the URL, under the CVE view's names (cveView.ts:
// `?product=langflow&severity=CRITICAL&status=all&verdict=affected&kev=1&since=…&new=1`), so a tile or a shared link opens
// the page filtered and a reload keeps the filters. The product select picks one product; a dashboard link may carry
// several (A15b: `?product=langflow,ollama`), shown as one more option. Narrow (a phone, or the chat pinned beside
// it) the rows become stacked cards: the row actions never need sideways scrolling.

const PAGE_SIZE = 25

// The list's place, kept in its history entry when a CVE's page opens (B35), so Back returns to the same page of rows
// and the same scroll. The filters are in the URL already. A new visit (the sidebar, a link) starts at the top.
interface ListPlace {
  offset: number
  scrollY: number
}

function keepPlace(offset: number): void {
  const place: ListPlace = { offset, scrollY: window.scrollY }
  history.replaceState({ ...(history.state as object | null), cvesList: place }, '', window.location.href)
}

function placeKept(): ListPlace | null {
  const kept = (history.state as { cvesList?: ListPlace } | null)?.cvesList
  return kept && Number.isFinite(kept.offset) && Number.isFinite(kept.scrollY) ? kept : null
}

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

// onAsk: "Ask about this" opens Patch over this page and asks about that CVE (DESIGN.md §6.4); that row becomes the
// selected CVE. onView: the filters Patch is told about (A18), on every change.
export function CvesPage({ search, onAsk, selected = null, onView }: {
  search: string
  onAsk: (cveId: string) => void
  selected?: string | null
  onView?: (view: ShownView) => void
}) {
  const [filters, setFilters] = useState<CveView>(() => viewFromSearch(search))
  const [place] = useState(placeKept) // where Back to this list returns to (B35): its page of rows and scroll
  const [offset, setOffset] = useState(place?.offset ?? 0)
  const [page, setPage] = useState<CvePage | null>(null)
  const [products, setProducts] = useState<Product[]>([])
  const [error, setError] = useState<string | null>(null)
  const [asOf, setAsOf] = useState<string | null>(null)
  const [live, setLive] = useState(false) // live data (B02): checks happen, so "New" can mean something
  const [deciding, setDeciding] = useState<DecisionRequest | null>(null) // the open decision dialog (A16b)
  const [filtersOpen, setFiltersOpen] = useState(false) // the phone's folded filters (B44); a desktop ignores it

  const loadRows = useCallback(
    () => fetchCves(filters, PAGE_SIZE, offset).then(setPage),
    [filters, offset],
  )

  useEffect(() => {
    fetchDashboard().then(
      (d) => {
        setProducts(d.products.filter((p) => d.watchlist.includes(p.id)))
        setAsOf(d.as_of)
        setLive(d.data.mode === 'live')
      },
      (e: unknown) => setError(message(e)),
    )
  }, [])
  useEffect(() => {
    loadRows().then(
      () => setError(null),
      (e: unknown) => setError(message(e)),
    )
  }, [loadRows])
  // Back from a CVE's page: once the rows are in, scroll to where the list was (only on that first load)
  const restored = useRef(false)
  useEffect(() => {
    if (!page || !place || restored.current) return
    restored.current = true
    window.scrollTo(0, place.scrollY)
  }, [page, place])

  // "Langflow + Ollama" for several products from a dashboard link (A15b)
  const productName = filters.product
    ?.split(',')
    .map((id) => products.find((p) => p.id === id)?.name ?? id)
    .join(' + ')
  useEffect(() => {
    onView?.({ filters, productName })
  }, [filters, productName, onView])

  function filter(patch: Partial<CveView>) {
    const next = { ...filters, ...patch }
    setFilters(next)
    setOffset(0)
    // Replace, not push: a filter change isn't a new page for Back, but a reload keeps it.
    history.replaceState(null, '', window.location.pathname + viewToSearch(next) + window.location.hash)
  }

  // Every status change goes through the dialog and becomes a decision record (A16b). Its errors show in the dialog.
  async function decide(id: string, body: DecisionInput) {
    await setStatus(id, body)
    await loadRows().catch((e: unknown) => setError(message(e)))
  }

  // B40: "Mark all as seen" empties "New" (every new CVE, whatever the filters). The button goes away with them, so
  // the focus moves to the New box next to it rather than being lost.
  const newBox = useRef<HTMLInputElement>(null)
  const [marking, setMarking] = useState(false)
  async function markAll() {
    setMarking(true)
    try {
      await markAllSeen()
      await loadRows()
      newBox.current?.focus()
    } catch (e: unknown) {
      setError(message(e))
    } finally {
      setMarking(false)
    }
  }

  // A product from a link that isn't on the watchlist (or several, from the dashboard) still shows in the list, so
  // the select says what's filtered.
  const options = filters.product && productName && !products.some((p) => p.id === filters.product)
    ? [...products, { id: filters.product, name: productName }]
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
          {/* B44 L4: on a phone (or beside the pinned chat) the filters fold behind one button that says how many
              are on; the count line stays in view. On a desktop the button is hidden and the controls show as before. */}
          <button
            type="button"
            className="filters-toggle"
            aria-expanded={filtersOpen}
            aria-controls="cve-filter-controls"
            onClick={() => setFiltersOpen(!filtersOpen)}
          >
            {filtersLabel(filters)}
          </button>
          <div id="cve-filter-controls" className={`filter-controls${filtersOpen ? ' open' : ''}`}>
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
                value={filters.severity ?? ''}
                onChange={(e) => filter({ severity: (e.target.value || undefined) as Severity | undefined })}
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
              <select value={filters.status} onChange={(e) => filter({ status: e.target.value as StatusFilter })}>
                {STATUS_FILTERS.map((s) => (
                  <option key={s} value={s}>
                    {statusFilterLabel(s)}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Verdict
              <select
                value={filters.verdict ?? ''}
                onChange={(e) => filter({ verdict: (e.target.value || undefined) as Verdict | undefined })}
              >
                <option value="">Any</option>
                {VERDICTS.map((v) => (
                  <option key={v} value={v}>
                    {VERDICT_LABEL[v]}
                  </option>
                ))}
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
            {(live || filters.new) && (
              <label>
                <input
                  ref={newBox}
                  type="checkbox"
                  checked={filters.new ?? false}
                  onChange={(e) => filter({ new: e.target.checked || undefined })}
                />
                {NEW_LABEL}
              </label>
            )}
            {(live || filters.new) && page && page.new_total > 0 && (
              <button
                type="button"
                className="mark-seen"
                disabled={marking}
                title={`${page.new_total} new CVE${page.new_total === 1 ? '' : 's'} you haven't opened`}
                onClick={() => void markAll()}
              >
                Mark all as seen
              </button>
            )}
            {filters.since && (
              <span className="chip filter-chip">
                Published since {filters.since}
                <button
                  type="button"
                  aria-label={`Clear: published since ${filters.since}`}
                  title="Clear this filter"
                  onClick={() => filter({ since: undefined })}
                >
                  ✕
                </button>
              </span>
            )}
          </div>
          <span className="meta" aria-live="polite">
            {page ? `${page.total} CVEs · by priority, then due date` : 'Loading…'}
          </span>
        </div>
        <CveTable
          page={page}
          onDecide={asOf ? setDeciding : undefined}
          onAsk={onAsk}
          onOpen={() => keepPlace(offset)}
          selected={selected}
        />
        {deciding && asOf && (
          <DecisionDialog
            key={`${deciding.cve}-${deciding.status}`}
            request={deciding}
            asOf={asOf}
            onSubmit={(body) => decide(deciding.cve, body)}
            onClose={() => setDeciding(null)}
          />
        )}
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
function CveTable({ page, onDecide, onAsk, onOpen, selected }: {
  page: CvePage | null
  onOpen: () => void // a CVE's page is about to open: keep this list's place for Back (B35)
  selected: string | null // the CVE Patch is told about (A18)
  onDecide?: (r: DecisionRequest) => void // undefined until the as-of date is known (the review date needs it)
  onAsk: (id: string) => void
}) {
  return (
    <div className="table-scroll">
      <table className="cves">
        <thead>
          <tr>
            <th scope="col">CVE</th>
            <th scope="col">
              <Tip text={HEADER_TIPS.priority}>Priority</Tip>
            </th>
            <th scope="col">
              <Tip text={HEADER_TIPS.due}>Due</Tip>
            </th>
            <th scope="col">Product</th>
            <th scope="col">Severity</th>
            <th scope="col">Published</th>
            <th scope="col">
              <Tip text={HEADER_TIPS.owasp}>OWASP</Tip>
            </th>
            <th scope="col">
              <Tip text={HEADER_TIPS.epss}>EPSS</Tip>
            </th>
            <th scope="col">
              <Tip text={HEADER_TIPS.verdict}>Verdict</Tip>
            </th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          {page?.rows.map((r) => (
            <tr key={r.id} className={r.id === selected ? 'selected' : undefined}>
              <td className="cve-cell">
                <CveLink id={r.id} fromList={onOpen} />
                {r.id === selected && (
                  <span className="chip selected-chip" title="Patch knows this is the CVE you asked about">
                    Selected
                  </span>
                )}
                {r.kev && (
                  // B44 L3: the KEV deadline shows once, in the Due cell, where every date of the row is read
                  <span className="chip kev" title="In CISA KEV: known to be exploited">
                    KEV
                  </span>
                )}
                {r.new && (
                  <span className="chip new-chip" title={NEW_TITLE}>
                    New
                  </span>
                )}
                {r.possible_match && <PossibleMatch />}
                <div className="summary">{r.summary}</div>
              </td>
              <td data-label="Priority" className="priority-cell">
                <PriorityChip level={r.priority} />
                <PriorityReasons reasons={r.priority_reasons} />
              </td>
              <td data-label="Due" className="due-cell">
                <DueFacts
                  due={r.due_date}
                  from={r.due_from}
                  overdue={r.overdue}
                  kevDeadline={r.kev_deadline}
                  noFix={r.no_fix && r.open ? { days: r.open_days } : null}
                />
              </td>
              <td data-label="Product">{r.product_name}</td>
              <td data-label="Severity">
                <SeverityBadge severity={r.severity} cvss={r.cvss} />
              </td>
              <td data-label="Published" className="num">
                {r.published}
              </td>
              <td data-label="OWASP">
                <OwaspCode code={r.owasp} tip={owaspTip(r.owasp_title, r.owasp_list)} />
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
              <td data-label="Verdict" className="verdict-cell">
                <VerdictChip verdict={r.verdict} />
                <VerdictFacts reason={r.verdict_reason} fixed={r.fixed_version} who={r.who_acts} />
                {/* A suggestion only: the user's click is the decision; nothing marks a CVE on its own (A15). */}
                <SuggestNotAffected row={r} onDecide={onDecide} />
              </td>
              <td data-label="Status" className="status-cell">
                {/* Status and its actions share a column: the table stays narrow enough for the pinned chat. */}
                <span className="status">
                  {STATUS_LABEL[r.status]}
                  {r.review_due && <span className="chip review-due">Review due</span>}
                </span>
                <DecisionSummary row={r} />
                <RowActions row={r} onDecide={onDecide} onAsk={onAsk} />
                <DecisionHistory row={r} />
              </td>
            </tr>
          ))}
          {page?.rows.length === 0 && (
            <tr className="empty">
              <td colSpan={10} className="meta">
                No CVEs match these filters.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

// The OWASP code (B44 L5): "A05" alone says neither the category nor the list, so its tooltip names both. No
// category: a dash, with nothing to explain.
function OwaspCode({ code, tip }: { code: string | null; tip: string | null }) {
  if (!code) return <>—</>
  if (!tip) return <>{code}</>
  return <Tip text={tip}>{code}</Tip>
}

// A row's actions (B36, #86): the one main action in view, the rest and "Ask about this" under "More", a native
// disclosure. Four stacked buttons made each row about 147px tall, so only 4 fit on a screen. A disclosure rather
// than a pop-up menu: it opens in place inside the row, so the table's sideways-scroll box can't clip it and a phone
// never has it off-screen; the browser gives it Enter, Space and its expanded state for free. Every action also sits
// on the CVE's own page (§5.15), one click on the id away.
function RowActions({ row: r, onDecide, onAsk }: {
  row: CveRow
  onDecide?: (r: DecisionRequest) => void
  onAsk: (id: string) => void
}) {
  const { main, more } = rowActions(r)
  return (
    <div className="actions">
      <ActionButtons actions={[main]} onDecide={onDecide} />
      <details className="more-actions">
        <summary aria-label={`More actions for ${r.id}`}>More</summary>
        <div className="more-list">
          <ActionButtons actions={more} onDecide={onDecide} />
          <button type="button" aria-label={`Ask about this: ${r.id}`} onClick={() => onAsk(r.id)}>
            Ask about this
          </button>
        </div>
      </details>
    </div>
  )
}

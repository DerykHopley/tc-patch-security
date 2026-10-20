// The embedding map (DESIGN.md §5.5), ported from proto: every chunk as a point on a 2D PCA of the vectors in the
// Chroma index, with the playground's query, rewrites and final sources on top. Three groups in the validated
// categorical colours (--cat-1/2/3, §3.2), each with its own shape, so colour is never the only cue; a table view
// carries the same information. Nothing here animates.
import { useEffect, useMemo, useRef, useState, type MouseEvent } from 'react'
import type { DevSearch, DocType, EmbeddingMapData } from '../api.ts'
import { Tooltip, type Tip } from '../components/charts.tsx'
import { placeLabels } from './mapLabels.ts'

type Group = 'owasp' | 'atlas' | 'cve'
const GROUPS: { id: Group; label: string; shape: string }[] = [
  { id: 'owasp', label: 'OWASP pages', shape: 'circle' },
  { id: 'atlas', label: 'MITRE ATLAS', shape: 'square' },
  { id: 'cve', label: 'CVEs', shape: 'triangle' },
]
const groupOf = (t: DocType): Group => (t.startsWith('owasp') ? 'owasp' : t.startsWith('atlas') ? 'atlas' : 'cve')

function marker(g: Group, x: number, y: number, r: number) {
  if (g === 'owasp') return <circle cx={x} cy={y} r={r} />
  if (g === 'atlas') return <rect x={x - r * 0.9} y={y - r * 0.9} width={r * 1.8} height={r * 1.8} />
  const h = r * 1.15
  return <path d={`M${x},${y - h}L${x + h},${y + h * 0.75}L${x - h},${y + h * 0.75}Z`} />
}

function cross(x: number, y: number, r: number) {
  return `M${x - r},${y - r}L${x + r},${y + r}M${x + r},${y - r}L${x - r},${y + r}`
}

// A range around [lo, hi], padded, never narrower than 12% of the full map.
function fit(lo: number, hi: number, full: number) {
  const span = Math.max(hi - lo, full * 0.12) * 1.5
  const mid = (lo + hi) / 2
  return [mid - span / 2, mid + span / 2]
}

const queryName = (i: number) => (i === 0 ? 'Semantic query' : `Rewrite ${i}`)

export function EmbeddingMap({ data, search }: { data: EmbeddingMapData; search: DevSearch | null }) {
  const box = useRef<HTMLDivElement>(null)
  const [width, setWidth] = useState(0)
  const [hidden, setHidden] = useState<Set<Group>>(new Set())
  const [tip, setTip] = useState<Tip | null>(null)
  const [zoomed, setZoomed] = useState(true) // after a search: fit the query and its sources

  useEffect(() => {
    if (!box.current) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)))
    ro.observe(box.current)
    return () => ro.disconnect()
  }, [])

  const { points } = data
  const queries = useMemo(() => search?.map ?? [], [search])
  const finalIds = useMemo(() => search?.final.map((f) => f.chunk_id) ?? [], [search])
  const height = Math.max(300, Math.min(480, Math.round(width * 0.62)))
  const pad = 18
  const zoom = zoomed && queries.length > 0

  const { sx, sy, centroids, counts } = useMemo(() => {
    const xs = points.map((p) => p.x)
    const ys = points.map((p) => p.y)
    let [x0, x1] = [Math.min(...xs), Math.max(...xs)]
    let [y0, y1] = [Math.min(...ys), Math.max(...ys)]
    if (zoom) {
      // Fit the queries and the final sources, padded, never narrower than 12% of the full map.
      const ids = new Set(finalIds)
      const hits = points.filter((p) => ids.has(p.id))
      const fx = [...queries.map((q) => q.x), ...hits.map((p) => p.x)]
      const fy = [...queries.map((q) => q.y), ...hits.map((p) => p.y)]
      ;[x0, x1] = fit(Math.min(...fx), Math.max(...fx), x1 - x0)
      ;[y0, y1] = fit(Math.min(...fy), Math.max(...fy), y1 - y0)
    }
    const toX = (x: number) => pad + ((x - x0) / (x1 - x0 || 1)) * (width - 2 * pad)
    const toY = (y: number) => height - pad - ((y - y0) / (y1 - y0 || 1)) * (height - 2 * pad)
    const acc: Record<Group, { x: number; y: number; n: number }> = {
      owasp: { x: 0, y: 0, n: 0 },
      atlas: { x: 0, y: 0, n: 0 },
      cve: { x: 0, y: 0, n: 0 },
    }
    for (const p of points) {
      const a = acc[groupOf(p.type)]
      a.x += p.x
      a.y += p.y
      a.n += 1
    }
    // Each group's label just above its centre; zoomed to a query, a group whose centre is off the map has none.
    // placeLabels keeps them apart and inside the map (B50: they overlapped with a real embedder).
    const centres = GROUPS.filter((g) => acc[g.id].n > 0 && !hidden.has(g.id))
      .map((g) => ({ id: g.id, text: g.label, x: toX(acc[g.id].x / acc[g.id].n), y: toY(acc[g.id].y / acc[g.id].n) - 10 }))
      .filter((c) => c.x >= 0 && c.x <= width && c.y >= 0 && c.y <= height)
    const n = Object.fromEntries(GROUPS.map((g) => [g.id, acc[g.id].n])) as Record<Group, number>
    return { sx: toX, sy: toY, centroids: placeLabels(centres, width, height), counts: n }
  }, [points, width, height, zoom, queries, finalIds, hidden])

  const finalSet = new Set(finalIds)
  const byId = new Map(points.map((p) => [p.id, p]))
  const q0 = queries[0]
  const toggle = (g: Group) =>
    setHidden((h) => {
      const next = new Set(h)
      if (next.has(g)) next.delete(g)
      else next.add(g)
      return next
    })
  const show = (e: MouseEvent, text: string) => {
    const r = (e.currentTarget as Element).getBoundingClientRect()
    setTip({ x: r.left + r.width / 2, y: r.top, text })
  }
  const hide = () => setTip(null)

  return (
    <div className="emap">
      <fieldset className="plain emap-legend">
        <legend className="visually-hidden">Show or hide groups</legend>
        {GROUPS.map((g) => (
          <button key={g.id} type="button" aria-pressed={!hidden.has(g.id)} onClick={() => toggle(g.id)}>
            <svg width="14" height="14" viewBox="-7 -7 14 14" className={`grp-${g.id}`} aria-hidden="true">
              {marker(g.id, 0, 0, 5)}
            </svg>
            {g.label} <span className="count">{counts[g.id]}</span>
            <span className="visually-hidden"> ({g.shape}s)</span>
          </button>
        ))}
        {search && (
          <button type="button" className="emap-zoom" onClick={() => setZoomed((z) => !z)}>
            {zoom ? 'Show all' : 'Zoom to query'}
          </button>
        )}
        {search && (
          <span className="emap-key">
            <span aria-hidden="true">✕</span> query and rewrites · dark ring: final sources
          </span>
        )}
      </fieldset>
      <div ref={box} className="emap-box">
        {width > 0 && (
          <svg width={width} height={height}
            aria-label={`Map of ${points.length} chunks, coloured and shaped by source.${search ? ' Your query and its final sources are highlighted.' : ''}`}>
            <g className={search ? 'dimmed' : undefined}>
              {GROUPS.filter((g) => !hidden.has(g.id)).map((g) => (
                <g key={g.id} className={`grp-${g.id} pts`}>
                  {points
                    .filter((p) => groupOf(p.type) === g.id && !finalSet.has(p.id))
                    .map((p) => (
                      <g key={p.id} onMouseEnter={(e) => show(e, `${p.title} · ${p.type}`)} onMouseLeave={hide}>
                        {marker(g.id, sx(p.x), sy(p.y), 3.2)}
                      </g>
                    ))}
                </g>
              ))}
            </g>
            {centroids.map((c) => (
              <text key={c.id} x={c.x} y={c.y} className="emap-label" textAnchor="middle">
                {c.text}
              </text>
            ))}
            {search && q0 && (
              <g className="overlay">
                {finalIds.map((id) => {
                  const p = byId.get(id)
                  return p ? <line key={`l-${id}`} x1={sx(q0.x)} y1={sy(q0.y)} x2={sx(p.x)} y2={sy(p.y)} className="emap-link" /> : null
                })}
                {search.final.map((f) => {
                  const p = byId.get(f.chunk_id)
                  if (!p) return null
                  const g = groupOf(p.type)
                  return (
                    <g key={f.chunk_id} className={`grp-${g} hit`} onMouseEnter={(e) => show(e, `[${f.n}] ${p.title}`)} onMouseLeave={hide}>
                      {marker(g, sx(p.x), sy(p.y), 6)}
                    </g>
                  )
                })}
                {queries.map((q, i) => (
                  <g key={i} className={`qmark${i === 0 ? ' main' : ''}`} onMouseEnter={(e) => show(e, `${queryName(i)}: ${q.query}`)}
                    onMouseLeave={hide}>
                    <path d={cross(sx(q.x), sy(q.y), i === 0 ? 6 : 4)} />
                    <circle cx={sx(q.x)} cy={sy(q.y)} r={10} className="hit-area" />
                  </g>
                ))}
              </g>
            )}
          </svg>
        )}
      </div>
      <p className="meta">
        PCA of the {data.dim}-dimension vectors in the index ({data.embedder}): the two axes keep{' '}
        {(data.explained[0] * 100).toFixed(1)}% and {(data.explained[1] * 100).toFixed(1)}% of the variation, so nearness here
        is a hint, not the search's real ranking.
      </p>
      <details className="table-view">
        <summary>Show as table</summary>
        <table className="data">
          <caption className="visually-hidden">Chunks per group</caption>
          <thead>
            <tr>
              <th>Group</th>
              <th>Shape</th>
              <th>Chunks</th>
            </tr>
          </thead>
          <tbody>
            {GROUPS.map((g) => (
              <tr key={g.id}>
                <td>{g.label}</td>
                <td>{g.shape}</td>
                <td>{counts[g.id]}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {search && (
          <table className="data">
            <caption className="visually-hidden">The query, its rewrites and the final sources on the map</caption>
            <thead>
              <tr>
                <th>Point</th>
                <th>x</th>
                <th>y</th>
              </tr>
            </thead>
            <tbody>
              {queries.map((q, i) => (
                <tr key={`q${i}`}>
                  <td>
                    {queryName(i)}: {q.query}
                  </td>
                  <td>{q.x}</td>
                  <td>{q.y}</td>
                </tr>
              ))}
              {search.final.map((f) => {
                const p = byId.get(f.chunk_id)
                return p ? (
                  <tr key={f.chunk_id}>
                    <td>
                      [{f.n}] {p.title}
                    </td>
                    <td>{p.x}</td>
                    <td>{p.y}</td>
                  </tr>
                ) : null
              })}
            </tbody>
          </table>
        )}
      </details>
      <Tooltip tip={tip} />
    </div>
  )
}

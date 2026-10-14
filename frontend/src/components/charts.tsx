// Plain-SVG charts for the dashboard (DESIGN.md §5.4), ported from proto/. Drawn in pixels at the container's
// width, so text never scales. Colours come from tokens: --sev-* is the validated one-hue severity ramp (§3.2),
// --series-1 the single-series hue. Text always uses text tokens, never a series colour.
import { useEffect, useRef, useState, type AnimationEvent, type CSSProperties, type ReactNode } from 'react'
import type { ProductCounts } from '../api.ts'
import { SEVERITIES, sevLabel } from '../severity.ts'
import '../styles/charts.css'

export interface Tip {
  x: number
  y: number
  text: string
}
type OnTip = (tip: Tip | null) => void

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  const [width, setWidth] = useState(0)
  useEffect(() => {
    if (!ref.current) return
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)))
    ro.observe(ref.current)
    return () => ro.disconnect()
  }, [])
  return [ref, width] as const
}

// Bars grow in once, on first load (DESIGN.md §7.1): the class goes when the grow ends, so a resize, a hover or
// a reload after "Mark fixed" never starts it again.
function useGrowOnce() {
  const [growing, setGrowing] = useState(true)
  const onAnimationEnd = (e: AnimationEvent) => {
    if (e.animationName.startsWith('grow-')) setGrowing(false)
  }
  return { className: growing ? ' grow' : '', onAnimationEnd }
}

// Hover and keyboard focus show the same tooltip: above the pointer, or above the bar when focused.
function tipHandlers(text: string, onTip: OnTip) {
  const atBar = (el: Element): Tip => {
    const r = el.getBoundingClientRect()
    return { x: r.left + r.width / 2, y: r.top, text }
  }
  return {
    'aria-label': text,
    tabIndex: 0,
    onMouseMove: (e: React.MouseEvent) => onTip({ x: e.clientX, y: e.clientY, text }),
    onMouseLeave: () => onTip(null),
    onFocus: (e: React.FocusEvent) => onTip(atBar(e.currentTarget)),
    onBlur: () => onTip(null),
  }
}

// A bar with a 4px rounded data end on the right; the baseline end stays square.
function hbar(x: number, y: number, w: number, h: number, round: boolean) {
  const r = round ? Math.min(4, w, h / 2) : 0
  return `M${x},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${r - w}z`
}

export function ChartCard({
  id,
  title,
  note,
  legend,
  table,
  children,
}: {
  id: string
  title: string
  note?: ReactNode
  legend?: ReactNode
  table: ReactNode
  children: ReactNode
}) {
  return (
    <section className="card chart" aria-labelledby={`${id}-title`}>
      <h2 id={`${id}-title`}>{title}</h2>
      {note && <p className="meta">{note}</p>}
      {legend}
      {children}
      <details className="table-view">
        <summary>Show as table</summary>
        <div className="table-scroll">{table}</div>
      </details>
    </section>
  )
}

export function SeverityLegend() {
  return (
    <ul className="legend" aria-label="Severity">
      {SEVERITIES.map((s) => (
        <li key={s} className={`sev-${s.toLowerCase()}`}>
          <span className="swatch" aria-hidden="true" />
          {sevLabel(s)}
        </li>
      ))}
    </ul>
  )
}

const ROW = 26
const GAP = 2 // surface gap between touching fills

// Open CVEs per watched product, stacked by severity (critical first), the total at the end.
export function StackedBars({ rows, onTip }: { rows: ProductCounts[]; onTip: OnTip }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const grow = useGrowOnce()
  const labelW = Math.min(110, Math.max(70, width * 0.28))
  const endW = 40
  const max = Math.max(1, ...rows.map((r) => r.total))
  const plotW = Math.max(0, width - labelW - endW)
  const h = rows.length * (ROW + 10)
  return (
    <div ref={ref} className={`chart-box hbars${grow.className}`} onAnimationEnd={grow.onAnimationEnd}>
      {width > 0 && (
        <svg width={width} height={h} aria-label="Open CVEs by product and severity"
          style={{ '--x0': `${labelW}px` } as CSSProperties}>
          {rows.map((r, i) => {
            const y = i * (ROW + 10) + 4
            let x = labelW
            const segs = SEVERITIES.filter((s) => r[s] > 0)
            return (
              <g key={r.product} className="bar-row">
                <text x={labelW - 8} y={y + ROW / 2} className="axis-label" textAnchor="end" dominantBaseline="middle">
                  {r.name}
                </text>
                {segs.map((s, j) => {
                  const w = (r[s] / max) * plotW
                  const last = j === segs.length - 1
                  const d = hbar(x, y, Math.max(1, w - (last ? 0 : GAP)), ROW, last)
                  x += w
                  return (
                    <path key={s} d={d} className={`fill sev-${s.toLowerCase()}`} data-severity={s}
                      {...tipHandlers(`${r.name} · ${sevLabel(s)}: ${r[s]} open`, onTip)} />
                  )
                })}
                <text x={x + 6} y={y + ROW / 2} className="value-label" dominantBaseline="middle">
                  {r.total}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

function vbar(x: number, y: number, w: number, h: number) {
  const r = Math.min(4, w / 2, h)
  return `M${x},${y + h}v${r - h}a${r},${r} 0 0 1 ${r},${-r}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${h - r}z`
}

// CVEs per month: one series, columns, a quiet grid, value labels on the highest month and the latest one.
export function Columns({ data, onTip }: { data: { month: string; count: number }[]; onTip: OnTip }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const grow = useGrowOnce()
  const h = 180
  const pad = { l: 32, r: 8, t: 18, b: 22 }
  const max = Math.max(1, ...data.map((d) => d.count))
  const step = Math.pow(10, Math.floor(Math.log10(max)))
  const tickStep = max / step > 5 ? step * 2 : step
  const ticks = Array.from({ length: Math.floor(max / tickStep) + 1 }, (_, i) => i * tickStep)
  const top = Math.max(max, ticks[ticks.length - 1])
  const plotW = Math.max(0, width - pad.l - pad.r)
  const plotH = h - pad.t - pad.b
  const slot = data.length ? plotW / data.length : 0
  const bw = Math.max(2, slot - GAP)
  const y = (v: number) => pad.t + plotH - (v / top) * plotH
  const peak = data.reduce((a, d, i) => (d.count > data[a].count ? i : a), 0)
  const labelled = new Set([peak, data.length - 1])
  return (
    <div ref={ref} className={`chart-box vbars${grow.className}`} onAnimationEnd={grow.onAnimationEnd}>
      {width > 0 && (
        <svg width={width} height={h} aria-label="CVEs per month for watched products">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} className="grid" />
              <text x={pad.l - 6} y={y(t)} className="axis-label" textAnchor="end" dominantBaseline="middle">
                {t}
              </text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = pad.l + i * slot + GAP / 2
            return (
              <g key={d.month}>
                {d.count > 0 && <path d={vbar(x, y(d.count), bw, pad.t + plotH - y(d.count))} className="fill series-1" />}
                {/* The hover target is the whole month's slot: bigger than a thin column, and there for empty months. */}
                <rect x={pad.l + i * slot} y={pad.t} width={slot} height={plotH} className="hit"
                  {...tipHandlers(`${d.month}: ${d.count} CVEs`, onTip)} />
                {labelled.has(i) && d.count > 0 && (
                  <text x={x + bw / 2} y={y(d.count) - 4} className="value-label" textAnchor="middle">
                    {d.count}
                  </text>
                )}
                {(d.month.endsWith('-01') || i === data.length - 1) && (
                  <text x={x + bw / 2} y={h - 6} className="axis-label" textAnchor={i === data.length - 1 ? 'end' : 'start'}>
                    {d.month.endsWith('-01') ? d.month.slice(0, 4) : d.month}
                  </text>
                )}
              </g>
            )
          })}
          <line x1={pad.l} x2={width - pad.r} y1={pad.t + plotH} y2={pad.t + plotH} className="baseline" />
        </svg>
      )}
    </div>
  )
}

// Labels are 11px text: about 6.2px a character. Too narrow for the name → just the code ("A08").
function fit(label: string, px: number) {
  const max = Math.floor(px / 6.2)
  if (label.length <= max) return label
  return max >= 14 ? label.slice(0, max - 1) + '…' : label.split(' ')[0]
}

// Open CVEs per OWASP web category: one series, horizontal bars, the value at the end.
export function Bars({ data, onTip }: { data: { label: string; count: number }[]; onTip: OnTip }) {
  const [ref, width] = useWidth<HTMLDivElement>()
  const grow = useGrowOnce()
  const labelW = Math.min(230, Math.max(48, width * 0.4))
  const endW = 40
  const max = Math.max(1, ...data.map((d) => d.count))
  const plotW = Math.max(0, width - labelW - endW)
  const row = 22
  return (
    <div ref={ref} className={`chart-box hbars${grow.className}`} onAnimationEnd={grow.onAnimationEnd}>
      {width > 0 && (
        <svg width={width} height={data.length * (row + 8)} aria-label="Open CVEs by OWASP category"
          style={{ '--x0': `${labelW}px` } as CSSProperties}>
          {data.map((d, i) => {
            const y = i * (row + 8) + 2
            const w = Math.max(1, (d.count / max) * plotW)
            return (
              <g key={d.label}>
                <text x={labelW - 8} y={y + row / 2} className="axis-label" textAnchor="end" dominantBaseline="middle">
                  {fit(d.label, labelW - 12)}
                </text>
                <path d={hbar(labelW, y, w, row, true)} className="fill series-1"
                  {...tipHandlers(`${d.label}: ${d.count} open`, onTip)} />
                <text x={labelW + w + 6} y={y + row / 2} className="value-label" dominantBaseline="middle">
                  {d.count}
                </text>
              </g>
            )
          })}
        </svg>
      )}
    </div>
  )
}

export function Tooltip({ tip }: { tip: Tip | null }) {
  if (!tip) return null
  return (
    <div className="chart-tip" role="tooltip" style={{ left: tip.x, top: tip.y }}>
      {tip.text}
    </div>
  )
}

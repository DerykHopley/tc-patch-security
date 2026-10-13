// Plain-SVG charts for the dashboard (U8). Drawn in pixels at the container's width, so text never scales.
// Colours come from CSS tokens: --sev-* is a validated one-hue ordinal ramp (light and dark), --series-1 the
// single-series hue. Text always uses text tokens, never a series colour.
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { ProductCounts } from "../api";
import { SEVERITIES, sevLabel } from "../severity";

export interface Tip {
  x: number;
  y: number;
  text: string;
}
type OnTip = (tip: Tip | null) => void;

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}

const tipAt = (e: React.MouseEvent | React.FocusEvent, text: string): Tip => {
  const r = (e.currentTarget as Element).getBoundingClientRect();
  return { x: r.left + r.width / 2, y: r.top, text };
};

// A bar with a 4px rounded data end on the right; the baseline end stays square.
function hbar(x: number, y: number, w: number, h: number, round: boolean) {
  const r = round ? Math.min(4, w, h / 2) : 0;
  return `M${x},${y}h${w - r}a${r},${r} 0 0 1 ${r},${r}v${h - 2 * r}a${r},${r} 0 0 1 ${-r},${r}h${r - w}z`;
}
function vbar(x: number, y: number, w: number, h: number) {
  const r = Math.min(4, w / 2, h);
  return `M${x},${y + h}v${r - h}a${r},${r} 0 0 1 ${r},${-r}h${w - 2 * r}a${r},${r} 0 0 1 ${r},${r}v${h - r}z`;
}

export function ChartCard({ title, note, legend, table, children }: {
  title: string; note?: ReactNode; legend?: ReactNode; table: ReactNode; children: ReactNode;
}) {
  return (
    <section className="panel chart">
      <h2>{title}</h2>
      {note && <p className="meta">{note}</p>}
      {legend}
      {children}
      <details className="table-view">
        <summary>Show as table</summary>
        {table}
      </details>
    </section>
  );
}

export function SeverityLegend() {
  return (
    <ul className="legend">
      {SEVERITIES.map((s) => (
        <li key={s}><span className={`swatch sev-${s.toLowerCase()}`} aria-hidden="true" />{sevLabel(s)}</li>
      ))}
    </ul>
  );
}

const ROW = 26;
const GAP = 2; // surface gap between touching fills

// Open CVEs per watched product, stacked by severity (critical first).
export function StackedBars({ rows, onTip }: { rows: ProductCounts[]; onTip: OnTip }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const labelW = 96;
  const endW = 40;
  const max = Math.max(1, ...rows.map((r) => r.total));
  const plotW = Math.max(0, width - labelW - endW);
  const h = rows.length * (ROW + 10);
  return (
    <div ref={ref} className="chart-box hbars">
      {width > 0 && (
        <svg width={width} height={h} role="img" aria-label="Open CVEs by product and severity" style={{ "--x0": `${labelW}px` } as React.CSSProperties}>
          {rows.map((r, i) => {
            const y = i * (ROW + 10) + 4;
            let x = labelW;
            const segs = SEVERITIES.filter((s) => r[s] > 0);
            return (
              <g key={r.product}>
                <text x={labelW - 8} y={y + ROW / 2} className="axis-label" textAnchor="end" dominantBaseline="middle">
                  {r.name}
                </text>
                {segs.map((s, j) => {
                  const w = (r[s] / max) * plotW;
                  const last = j === segs.length - 1;
                  const d = hbar(x, y, Math.max(1, w - (last ? 0 : GAP)), ROW, last);
                  x += w;
                  const text = `${r.name} · ${sevLabel(s)}: ${r[s]} open`;
                  return (
                    <path key={s} d={d} className={`fill sev-${s.toLowerCase()}`} tabIndex={0} aria-label={text}
                      onMouseEnter={(e) => onTip(tipAt(e, text))} onMouseLeave={() => onTip(null)}
                      onFocus={(e) => onTip(tipAt(e, text))} onBlur={() => onTip(null)} />
                  );
                })}
                <text x={x + 6} y={y + ROW / 2} className="value-label" dominantBaseline="middle">{r.total}</text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

// CVEs per month: one series, columns, a recessive grid, a label on the highest and the latest month.
export function Columns({ data, onTip }: { data: { month: string; count: number }[]; onTip: OnTip }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const h = 180;
  const pad = { l: 32, r: 8, t: 18, b: 22 };
  const max = Math.max(1, ...data.map((d) => d.count));
  const step = Math.pow(10, Math.floor(Math.log10(max)));
  const tickStep = max / step > 5 ? step * 2 : step;
  const ticks = Array.from({ length: Math.floor(max / tickStep) + 1 }, (_, i) => i * tickStep);
  const top = Math.max(max, ticks[ticks.length - 1]);
  const plotW = Math.max(0, width - pad.l - pad.r);
  const plotH = h - pad.t - pad.b;
  const slot = data.length ? plotW / data.length : 0;
  const bw = Math.max(2, slot - GAP);
  const y = (v: number) => pad.t + plotH - (v / top) * plotH;
  const peak = data.reduce((a, d, i) => (d.count > data[a].count ? i : a), 0);
  const labelled = new Set([peak, data.length - 1]);
  return (
    <div ref={ref} className="chart-box vbars">
      {width > 0 && (
        <svg width={width} height={h} role="img" aria-label="CVEs per month for watched products">
          {ticks.map((t) => (
            <g key={t}>
              <line x1={pad.l} x2={width - pad.r} y1={y(t)} y2={y(t)} className="grid" />
              <text x={pad.l - 6} y={y(t)} className="axis-label" textAnchor="end" dominantBaseline="middle">{t}</text>
            </g>
          ))}
          {data.map((d, i) => {
            const x = pad.l + i * slot + GAP / 2;
            const text = `${d.month}: ${d.count} CVEs`;
            return (
              <g key={d.month}>
                {d.count > 0 && <path d={vbar(x, y(d.count), bw, pad.t + plotH - y(d.count))} className="fill series-1" />}
                {/* hit target: the whole column slot, bigger than the mark */}
                <rect x={pad.l + i * slot} y={pad.t} width={slot} height={plotH} className="hit" tabIndex={0}
                  aria-label={text} onMouseEnter={(e) => onTip(tipAt(e, text))} onMouseLeave={() => onTip(null)}
                  onFocus={(e) => onTip(tipAt(e, text))} onBlur={() => onTip(null)} />
                {labelled.has(i) && d.count > 0 && (
                  <text x={x + bw / 2} y={y(d.count) - 4} className="value-label" textAnchor="middle">{d.count}</text>
                )}
                {(d.month.endsWith("-01") || i === data.length - 1) && (
                  <text x={x + bw / 2} y={h - 6} className="axis-label"
                    textAnchor={i === data.length - 1 ? "end" : "start"}>
                    {d.month.endsWith("-01") ? d.month.slice(0, 4) : d.month}
                  </text>
                )}
              </g>
            );
          })}
          <line x1={pad.l} x2={width - pad.r} y1={pad.t + plotH} y2={pad.t + plotH} className="baseline" />
        </svg>
      )}
    </div>
  );
}

// Labels are 11px text: about 6.2px a character. Too narrow for the name → just the code ("A08").
function fit(label: string, px: number) {
  const max = Math.floor(px / 6.2);
  if (label.length <= max) return label;
  return max >= 14 ? label.slice(0, max - 1) + "…" : label.split(" ")[0];
}

// Open CVEs per OWASP web category: one series, horizontal bars, value at the end.
export function Bars({ data, onTip }: { data: { label: string; count: number }[]; onTip: OnTip }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const labelW = Math.min(230, Math.max(48, width * 0.4));
  const endW = 40;
  const max = Math.max(1, ...data.map((d) => d.count));
  const plotW = Math.max(0, width - labelW - endW);
  const row = 22;
  return (
    <div ref={ref} className="chart-box hbars">
      {width > 0 && (
        <svg width={width} height={data.length * (row + 8)} role="img" aria-label="Open CVEs by OWASP category" style={{ "--x0": `${labelW}px` } as React.CSSProperties}>
          {data.map((d, i) => {
            const y = i * (row + 8) + 2;
            const w = Math.max(1, (d.count / max) * plotW);
            const text = `${d.label}: ${d.count} open`;
            return (
              <g key={d.label}>
                <text x={labelW - 8} y={y + row / 2} className="axis-label" textAnchor="end" dominantBaseline="middle">
                  {fit(d.label, labelW - 12)}
                </text>
                <path d={hbar(labelW, y, w, row, true)} className="fill series-1" tabIndex={0} aria-label={text}
                  onMouseEnter={(e) => onTip(tipAt(e, text))} onMouseLeave={() => onTip(null)}
                  onFocus={(e) => onTip(tipAt(e, text))} onBlur={() => onTip(null)} />
                <text x={labelW + w + 6} y={y + row / 2} className="value-label" dominantBaseline="middle">{d.count}</text>
              </g>
            );
          })}
        </svg>
      )}
    </div>
  );
}

export function Tooltip({ tip }: { tip: Tip | null }) {
  if (!tip) return null;
  return <div className="tooltip" role="tooltip" style={{ left: tip.x, top: tip.y }}>{tip.text}</div>;
}

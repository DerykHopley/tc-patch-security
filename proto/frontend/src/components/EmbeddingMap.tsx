// X5: every chunk as a point on a 2D PCA map, with the playground's query and sources on top.
// Three groups, validated as an all-pairs categorical palette (dataviz skill) in light and dark, plus a
// shape per group and direct labels, so colour is never the only cue.
import { useEffect, useMemo, useRef, useState } from "react";
import type { DocType, MapPoint } from "../api";
import { Tooltip, type Tip } from "./charts";

type Group = "owasp" | "atlas" | "cve";
const GROUPS: { id: Group; label: string; shape: string }[] = [
  { id: "owasp", label: "OWASP pages", shape: "circle" },
  { id: "atlas", label: "MITRE ATLAS", shape: "square" },
  { id: "cve", label: "CVEs", shape: "triangle" },
];
const groupOf = (t: DocType): Group => (t.startsWith("owasp") ? "owasp" : t.startsWith("atlas") ? "atlas" : "cve");

export interface MapOverlay {
  queries: { query: string; x: number; y: number }[];
  final: string[]; // chunk ids of the final sources
}

function marker(g: Group, x: number, y: number, r: number) {
  if (g === "owasp") return <circle cx={x} cy={y} r={r} />;
  if (g === "atlas") return <rect x={x - r * 0.9} y={y - r * 0.9} width={r * 1.8} height={r * 1.8} />;
  const h = r * 1.15;
  return <path d={`M${x},${y - h}L${x + h},${y + h * 0.75}L${x - h},${y + h * 0.75}Z`} />;
}

export function EmbeddingMap({ points, explained, overlay }: {
  points: MapPoint[]; explained: [number, number]; overlay: MapOverlay | null;
}) {
  const box = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);
  const [hidden, setHidden] = useState<Set<Group>>(new Set());
  const [tip, setTip] = useState<Tip | null>(null);
  const [zoomed, setZoomed] = useState(true); // after a search: fit the query and its sources

  useEffect(() => {
    if (!box.current) return;
    const ro = new ResizeObserver(([e]) => setWidth(Math.floor(e.contentRect.width)));
    ro.observe(box.current);
    return () => ro.disconnect();
  }, []);

  const height = Math.max(300, Math.min(480, Math.round(width * 0.62)));
  const pad = 18;

  const zoom = zoomed && !!overlay?.queries.length;
  const { sx, sy, centroids, counts } = useMemo(() => {
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    let [x0, x1] = [Math.min(...xs), Math.max(...xs)];
    let [y0, y1] = [Math.min(...ys), Math.max(...ys)];
    if (zoom && overlay) {
      // Fit the queries and final sources, padded, but never narrower than 12% of the full map.
      const ids = new Set(overlay.final);
      const fx = [...overlay.queries.map((q) => q.x), ...points.filter((p) => ids.has(p.id)).map((p) => p.x)];
      const fy = [...overlay.queries.map((q) => q.y), ...points.filter((p) => ids.has(p.id)).map((p) => p.y)];
      const fit = (lo: number, hi: number, full: number) => {
        const span = Math.max(hi - lo, full * 0.12) * 1.5;
        const mid = (lo + hi) / 2;
        return [mid - span / 2, mid + span / 2];
      };
      [x0, x1] = fit(Math.min(...fx), Math.max(...fx), x1 - x0);
      [y0, y1] = fit(Math.min(...fy), Math.max(...fy), y1 - y0);
    }
    const sx = (x: number) => pad + ((x - x0) / (x1 - x0 || 1)) * (width - 2 * pad);
    const sy = (y: number) => height - pad - ((y - y0) / (y1 - y0 || 1)) * (height - 2 * pad);
    const acc: Record<Group, { x: number; y: number; n: number }> = {
      owasp: { x: 0, y: 0, n: 0 }, atlas: { x: 0, y: 0, n: 0 }, cve: { x: 0, y: 0, n: 0 },
    };
    for (const p of points) {
      const a = acc[groupOf(p.type)];
      a.x += p.x; a.y += p.y; a.n += 1;
    }
    const centroids = GROUPS.map((g) => ({ ...g, x: sx(acc[g.id].x / (acc[g.id].n || 1)), y: sy(acc[g.id].y / (acc[g.id].n || 1)) - 10 }));
    // Labels that would overlap are nudged apart vertically.
    centroids.sort((a, b) => a.y - b.y);
    for (let i = 1; i < centroids.length; i++) {
      const prev = centroids[i - 1];
      const c = centroids[i];
      if (Math.abs(c.x - prev.x) < 110 && c.y - prev.y < 18) c.y = prev.y + 18;
    }
    const counts = Object.fromEntries(GROUPS.map((g) => [g.id, acc[g.id].n])) as Record<Group, number>;
    return { sx, sy, centroids, counts };
  }, [points, width, height, zoom, overlay]);

  const finalSet = new Set(overlay?.final ?? []);
  const byId = new Map(points.map((p) => [p.id, p]));
  const q0 = overlay?.queries[0];
  const toggle = (g: Group) => setHidden((h) => { const n = new Set(h); if (n.has(g)) n.delete(g); else n.add(g); return n; });
  const show = (e: React.MouseEvent, text: string) => {
    const r = (e.currentTarget as Element).getBoundingClientRect();
    setTip({ x: r.left + r.width / 2, y: r.top, text });
  };

  return (
    <div className="emap">
      <div className="emap-legend" role="group" aria-label="Show or hide groups">
        {GROUPS.map((g) => (
          <button key={g.id} type="button" aria-pressed={!hidden.has(g.id)} onClick={() => toggle(g.id)}>
            <svg width="14" height="14" viewBox="-7 -7 14 14" className={`grp-${g.id}`} aria-hidden="true">{marker(g.id, 0, 0, 5)}</svg>
            {g.label} <span className="meta inline">{counts[g.id]}</span>
          </button>
        ))}
        {overlay && (
          <button type="button" className="emap-zoom" onClick={() => setZoomed((z) => !z)}>
            {zoom ? "Show all" : "Zoom to query"}
          </button>
        )}
        {overlay && <span className="emap-key"><span className="key-q" aria-hidden="true">✕</span> your query · <span className="key-r" aria-hidden="true">○</span> final sources</span>}
      </div>
      <div ref={box} className="emap-box">
        {width > 0 && (
          <svg width={width} height={height} role="img"
            aria-label={`Map of ${points.length} chunks, coloured and shaped by source.${overlay ? " Your query and its final sources are highlighted." : ""}`}>
            <g className={overlay ? "dimmed" : undefined}>
              {GROUPS.filter((g) => !hidden.has(g.id)).map((g) => (
                <g key={g.id} className={`grp-${g.id} pts`}>
                  {points.filter((p) => groupOf(p.type) === g.id && !finalSet.has(p.id)).map((p) => (
                    <g key={p.id} onMouseEnter={(e) => show(e, `${p.title} · ${p.type}`)} onMouseLeave={() => setTip(null)}>
                      {marker(g.id, sx(p.x), sy(p.y), 3.2)}
                    </g>
                  ))}
                </g>
              ))}
            </g>
            {centroids.filter((c) => !hidden.has(c.id)).map((c) => (
              <text key={c.id} x={c.x} y={c.y} className="emap-label" textAnchor="middle">{c.label}</text>
            ))}
            {overlay && q0 && (
              <g className="overlay">
                {overlay.final.map((id) => {
                  const p = byId.get(id);
                  return p ? <line key={`l-${id}`} x1={sx(q0.x)} y1={sy(q0.y)} x2={sx(p.x)} y2={sy(p.y)} className="emap-link" /> : null;
                })}
                {overlay.final.map((id, i) => {
                  const p = byId.get(id);
                  if (!p) return null;
                  const g = groupOf(p.type);
                  return (
                    <g key={id} className={`grp-${g} hit`} onMouseEnter={(e) => show(e, `[${i + 1}] ${p.title}`)} onMouseLeave={() => setTip(null)}>
                      {marker(g, sx(p.x), sy(p.y), 6)}
                    </g>
                  );
                })}
                {overlay.queries.map((q, i) => (
                  <g key={i} className={`qmark${i === 0 ? " main" : ""}`} onMouseEnter={(e) => show(e, `${i === 0 ? "Semantic query" : `Rewrite ${i}`}: ${q.query}`)}
                    onMouseLeave={() => setTip(null)}>
                    <path d={`M${sx(q.x) - 6},${sy(q.y) - 6}L${sx(q.x) + 6},${sy(q.y) + 6}M${sx(q.x) + 6},${sy(q.y) - 6}L${sx(q.x) - 6},${sy(q.y) + 6}`} />
                    <circle cx={sx(q.x)} cy={sy(q.y)} r={10} className="hit-area" />
                  </g>
                ))}
              </g>
            )}
          </svg>
        )}
      </div>
      <p className="meta">
        PCA of the index's vectors: the two axes keep {(explained[0] * 100).toFixed(1)}% and {(explained[1] * 100).toFixed(1)}% of
        the variation, so nearness here is a hint, not the search's real ranking. With the hash embedder, chunks sit close when
        they share words.
      </p>
      <details className="table-view">
        <summary>Show as table</summary>
        <table className="data">
          <thead><tr><th>Group</th><th>Chunks</th></tr></thead>
          <tbody>{GROUPS.map((g) => <tr key={g.id}><td>{g.label}</td><td>{counts[g.id]}</td></tr>)}</tbody>
        </table>
        {overlay && (
          <table className="data">
            <thead><tr><th>Point</th><th>x</th><th>y</th></tr></thead>
            <tbody>
              {overlay.queries.map((q, i) => <tr key={`q${i}`}><td>{i === 0 ? "Semantic query" : `Rewrite ${i}`}: {q.query}</td><td>{q.x}</td><td>{q.y}</td></tr>)}
              {overlay.final.map((id, i) => { const p = byId.get(id); return p ? <tr key={id}><td>[{i + 1}] {p.title}</td><td>{p.x}</td><td>{p.y}</td></tr> : null; })}
            </tbody>
          </table>
        )}
      </details>
      <Tooltip tip={tip} />
    </div>
  );
}

import { useEffect, useState, type FormEvent } from "react";
import { ApiError, devInfo, devMap, devModels, devSearch, type DevInfo, type DevSearch, type DevSettings, type MapPoint } from "../api";
import { EmbeddingMap } from "./EmbeddingMap";
import { ModelCheck } from "./ModelCheck";
import { SaveBar } from "./SaveBar";
import { Status } from "./Settings";
import { useSettings } from "./useSettings";

// The SPEC's values. The model default comes from the backend's env, so it isn't listed here.
const SEARCH_DEFAULTS: Omit<DevSettings, "provider" | "model" | "local_base_url" | "local_model" | "temperature"> = {
  max_steps: 4, top_n: 5, per_query_k: 10, per_doc_cap: 2, rrf_k: 60, use_rewrites: true, use_filters: true,
};

const LOCAL_PRESETS = [
  { name: "Ollama", url: "http://localhost:11434/v1" },
  { name: "LM Studio", url: "http://localhost:1234/v1" },
  { name: "llama.cpp", url: "http://localhost:8080/v1" },
];

const EXAMPLES = [
  "How do I protect a RAG app from indirect prompt injection?",
  "Which critical Langflow vulnerabilities were published in 2026?",
  "denial of service in LiteLLM",
];

function Slider({ id, label, hint, value, min, max, step = 1, onChange }: {
  id: string; label: string; hint: string; value: number; min: number; max: number; step?: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="slider-row">
      <label htmlFor={id}>{label}<span className="meta">{hint}</span></label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} />
      <output htmlFor={id}>{value}</output>
    </div>
  );
}

// X1–X4: model, agent and search settings, index facts, and a search playground.
export function DevPanel() {
  const s = useSettings();
  const [info, setInfo] = useState<DevInfo | null>(null);
  const [query, setQuery] = useState(EXAMPLES[0]);
  const [result, setResult] = useState<DevSearch | null>(null);
  const [running, setRunning] = useState(false);
  const [runError, setRunError] = useState<string | null>(null);
  const [map, setMap] = useState<{ explained: [number, number]; points: MapPoint[] } | null>(null);
  const [models, setModels] = useState<string[] | null>(null);
  const [modelsError, setModelsError] = useState<string | null>(null);
  const [finding, setFinding] = useState(false);

  useEffect(() => { devInfo().then(setInfo).catch(() => setInfo(null)); }, []);
  useEffect(() => { devMap().then(setMap).catch(() => setMap(null)); }, []);

  if (!s.draft || !s.reply) return <p className="muted page-pad">{s.error ?? "Loading…"}</p>;
  const d = s.draft.dev;
  const set = (v: Partial<DevSettings>) => s.patch("dev", v);

  async function findModels() {
    if (!s.draft) return;
    setFinding(true);
    setModelsError(null);
    try {
      setModels((await devModels(s.draft.dev.local_base_url)).models);
    } catch (err) {
      setModels(null);
      setModelsError(err instanceof ApiError ? err.message : "Couldn't ask the server for its models.");
    } finally {
      setFinding(false);
    }
  }

  const savedDev = s.reply.settings.dev;
  const modelLabel = savedDev.provider === "fake" ? "FakeLLM (scripted)"
    : savedDev.provider === "openrouter" ? `OpenRouter · ${savedDev.model}` : `local · ${savedDev.local_model || "no model chosen"}`;

  async function run(e?: FormEvent, q = query) {
    e?.preventDefault();
    if (!q.trim()) return;
    setRunning(true);
    setRunError(null);
    try {
      setResult(await devSearch(q.trim()));
    } catch (err) {
      setRunError(err instanceof ApiError ? err.message : "The search failed.");
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="settings-page">
      <header className="page-head">
        <h2 className="page-title">Dev panel</h2>
        <p className="muted">Tune the model, the agent and search, then try a query to see each step. Turn this page off with
          <code> DEV_PANEL=false</code>: it shows internals.</p>
      </header>
      {s.dirty && <p className="notice">The playground and the chat use the <strong>saved</strong> settings. Save to try your changes.</p>}

      <div className="settings-grid">
        <section className="panel">
          <div className="panel-head"><h3>Model</h3><Status kind="live" /></div>
          <fieldset>
            <legend>Who answers</legend>
            <label className="check-row">
              <input type="radio" name="provider" id="prov-fake" checked={d.provider === "fake"} onChange={() => set({ provider: "fake" })} />
              <span><strong>FakeLLM</strong> <span className="meta inline">scripted, free, the same every run</span></span>
            </label>
            <label className={`check-row${s.reply.env.openrouter_key ? "" : " disabled"}`}>
              <input type="radio" name="provider" id="prov-openrouter" checked={d.provider === "openrouter"}
                disabled={!s.reply.env.openrouter_key} onChange={() => set({ provider: "openrouter" })} />
              <span><strong>OpenRouter</strong> <span className="meta inline">{s.reply.env.openrouter_key ? "hosted models" : "needs OPENROUTER_API_KEY in backend/.env"}</span></span>
            </label>
            <label className="check-row">
              <input type="radio" name="provider" id="prov-local" checked={d.provider === "local"} onChange={() => set({ provider: "local" })} />
              <span><strong>Local model</strong> <span className="meta inline">Ollama, LM Studio or llama.cpp on this machine</span></span>
            </label>
          </fieldset>

          {d.provider === "openrouter" && (
            <div className="field-row">
              <label htmlFor="dev-model">Model</label>
              <input id="dev-model" list="dev-models" value={d.model} onChange={(e) => set({ model: e.target.value.trim() })} spellCheck={false} />
              <datalist id="dev-models"><option value={s.reply.env.env_model} /></datalist>
            </div>
          )}

          {d.provider === "local" && (
            <>
              <div className="field-row">
                <label htmlFor="dev-local-url">Server</label>
                <input id="dev-local-url" className="mono-input" value={d.local_base_url} spellCheck={false}
                  onChange={(e) => { set({ local_base_url: e.target.value.trim() }); setModels(null); }} />
              </div>
              <div className="presets">
                {LOCAL_PRESETS.map((p) => (
                  <button key={p.url} type="button" aria-pressed={d.local_base_url === p.url}
                    onClick={() => { set({ local_base_url: p.url }); setModels(null); }}>{p.name}</button>
                ))}
              </div>
              <div className="field-row">
                <label htmlFor="dev-local-model">Model</label>
                {models && models.length > 0 ? (
                  <select id="dev-local-model" value={d.local_model} onChange={(e) => set({ local_model: e.target.value })}>
                    <option value="">Choose…</option>
                    {models.map((m) => <option key={m} value={m}>{m}</option>)}
                  </select>
                ) : (
                  <input id="dev-local-model" className="mono-input" value={d.local_model} placeholder="e.g. qwen3:8b" spellCheck={false}
                    onChange={(e) => set({ local_model: e.target.value.trim() })} />
                )}
                <button type="button" onClick={findModels} disabled={finding}>{finding ? "Looking…" : "Find models"}</button>
              </div>
              {modelsError && <p className="save-error">{modelsError}</p>}
              {models && models.length === 0 && <p className="meta">The server is running but has no models loaded.</p>}
              <p className="meta">Start the server first: <code>ollama serve</code> and <code>ollama pull &lt;model&gt;</code>, or LM
                Studio's Developer tab → Start server. The backend only calls this machine.</p>
            </>
          )}
          {d.provider !== "fake" && (
            <Slider id="dev-temp" label="Temperature" hint="lower = steadier answers" value={d.temperature} min={0} max={2} step={0.1}
              onChange={(v) => set({ temperature: v })} />
          )}
          {d.provider === "fake" && <p className="meta">Scripted answers: model and temperature don't apply.</p>}
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Agent and search</h3><Status kind="live" /></div>
          <Slider id="dev-steps" label="Max agent steps" hint="tool rounds before it stops" value={d.max_steps} min={1} max={8}
            onChange={(v) => set({ max_steps: v })} />
          <Slider id="dev-topn" label="Sources per search" hint="top_n" value={d.top_n} min={1} max={10} onChange={(v) => set({ top_n: v })} />
          <Slider id="dev-k" label="Hits per query" hint="before fusion" value={d.per_query_k} min={1} max={30} onChange={(v) => set({ per_query_k: v })} />
          <Slider id="dev-cap" label="Chunks per document" hint="per-doc cap" value={d.per_doc_cap} min={1} max={5} onChange={(v) => set({ per_doc_cap: v })} />
          <Slider id="dev-rrf" label="RRF k" hint="higher = flatter fusion" value={d.rrf_k} min={1} max={200} onChange={(v) => set({ rrf_k: v })} />
          <label className="switch-row">
            <input type="checkbox" id="dev-rewrites" checked={d.use_rewrites} onChange={(e) => set({ use_rewrites: e.target.checked })} />
            <span><strong>Multi-query rewrites</strong><span className="meta">Off: one search for the semantic query only.</span></span>
          </label>
          <label className="switch-row">
            <input type="checkbox" id="dev-filters" checked={d.use_filters} onChange={(e) => set({ use_filters: e.target.checked })} />
            <span><strong>Self-query filters</strong><span className="meta">Off: the LLM's filters are shown as dropped, not applied.</span></span>
          </label>
          <button type="button" onClick={() => set(SEARCH_DEFAULTS)}>Reset to the SPEC's values</button>
        </section>

        <section className="panel">
          <div className="panel-head"><h3>Index</h3><Status kind="live" /></div>
          {info ? (
            <>
              <p><strong>{info.chunks.toLocaleString()}</strong> chunks · {info.embedder} ({info.dim} buckets) · shared-word gate {info.word_gate ? "on" : "off"} · data as of {info.as_of}</p>
              <table className="data">
                <thead><tr><th>Document type</th><th>Chunks</th></tr></thead>
                <tbody>{Object.entries(info.by_doc_type).map(([t, n]) => <tr key={t}><td><code>{t}</code></td><td>{n}</td></tr>)}</tbody>
              </table>
              <p className="meta">The hash embedder only matches shared words. Swapping in real embeddings is one class (the Embedder seam).</p>
            </>
          ) : <p className="muted">Index facts unavailable.</p>}
        </section>
      </div>

      <ModelCheck modelLabel={modelLabel} dirty={s.dirty} />

      <section className="panel playground">
        <div className="panel-head"><h3>Search playground</h3><Status kind="live" /></div>
        <form className="play-form" onSubmit={run}>
          <input id="play-query" aria-label="Search query" value={query} onChange={(e) => setQuery(e.target.value)} maxLength={500} />
          <button type="submit" disabled={running || !query.trim()}>{running ? "Running…" : "Run search"}</button>
        </form>
        <div className="play-examples">
          {EXAMPLES.map((q) => <button key={q} type="button" onClick={() => { setQuery(q); run(undefined, q); }}>{q}</button>)}
        </div>
        {runError && <p className="save-error">{runError}</p>}
        <div className="emap-wrap">
          <h4>Embedding map</h4>
          {map ? (
            <EmbeddingMap points={map.points} explained={map.explained}
              overlay={result ? { queries: result.map, final: result.final.map((f) => f.chunk_id) } : null} />
          ) : <p className="muted"><span className="spinner" /> Projecting {info?.chunks.toLocaleString() ?? ""} chunks…</p>}
        </div>
        {result && (
          <div className="play-result">
            <div className="play-plan">
              <p><span className="meta">Semantic query</span> {result.query.semantic_query}</p>
              <p><span className="meta">Filters</span> {Object.entries(result.query.filters).map(([k, v]) => <span key={k} className="chip">{k}: {v}</span>)}
                {Object.keys(result.query.filters).length === 0 && <span className="muted">none</span>}
                {result.query.dropped_filters.map((f) => <span key={f} className="chip warn">{f}</span>)}
                {result.query.relaxed && <span className="chip warn">relaxed</span>}</p>
            </div>
            <div className="play-cols">
              {result.lists.map((l, i) => (
                <div key={i} className="play-col">
                  <h4>{i === 0 ? "Semantic query" : `Rewrite ${i}`}</h4>
                  <p className="meta">{l.query}</p>
                  <ol>{l.hits.map((h) => <li key={h.chunk_id}><span className="hit-title">{h.title}</span> <span className="meta">{h.chunk_id} · {h.score}</span></li>)}</ol>
                  {l.hits.length === 0 && <p className="muted">No hits.</p>}
                </div>
              ))}
              <div className="play-col fused">
                <h4>Fused (RRF)</h4>
                <p className="meta">Σ 1/(k + rank), k = {s.reply.settings.dev.rrf_k}</p>
                <ol>{result.fused.map((f) => <li key={f.chunk_id}><span className="hit-title">{f.title}</span> <span className="meta">{f.chunk_id} · {f.rrf}</span></li>)}</ol>
              </div>
              <div className="play-col final">
                <h4>Final sources</h4>
                <p className="meta">after the per-document cap</p>
                <ol>{result.final.map((f) => <li key={f.chunk_id}><span className="hit-title">{f.title}</span> <span className="meta">{f.section ?? f.doc_type}</span></li>)}</ol>
              </div>
            </div>
          </div>
        )}
      </section>

      <SaveBar dirty={s.dirty} saving={s.saving} savedAt={s.savedAt} error={s.error} onSave={s.save} onDiscard={s.discard} />
    </div>
  );
}

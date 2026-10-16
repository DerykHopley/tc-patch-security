import { useEffect, useState, type CSSProperties, type FormEvent } from 'react'
import {
  devInfo,
  devMap,
  devModels,
  devSearch,
  reportUrl,
  type DevInfo,
  type DevSearch,
  type DevSettings,
  type EmbeddingMapData,
  type Hit,
  type SearchOptions,
} from '../api.ts'
import { SaveBar } from '../components/SaveBar.tsx'
import { Card } from '../components/StatusCard.tsx'
import { useDevSettings } from '../components/useDevSettings.ts'
import { EmbeddingMap } from '../dev/EmbeddingMap.tsx'
import { ModelCheck } from '../dev/ModelCheck.tsx'
import { OpenRouterModelField } from '../dev/OpenRouterModelField.tsx'
import { RetrievalCheck } from '../dev/RetrievalCheck.tsx'
import '../styles/dev.css'

// The Dev panel (A11, DESIGN.md §5.3, §5.5–5.7): who answers, the agent's limits and search tuning, saved and applied
// on the next call; a playground that shows every retrieval step; the embedding map. Only shown when the backend
// allows the dev panel (it shows internals).

const LOCAL_PRESETS = [
  { name: 'Ollama', url: 'http://localhost:11434/v1' },
  { name: 'LM Studio', url: 'http://localhost:1234/v1' },
  { name: 'llama.cpp', url: 'http://localhost:8080/v1' },
]

const EXAMPLES = [
  'How do I protect a RAG app from indirect prompt injection?',
  'Which critical Langflow vulnerabilities were published in 2026?',
  'Explain CVE-2024-8309',
]

const SEARCH_FIELDS: (keyof SearchOptions | 'max_steps')[] = [
  'max_steps', 'top_n', 'per_query_k', 'per_doc_cap', 'rrf_k', 'keyword_weight', 'use_rewrites', 'use_filters',
]

const RETRIEVER = { vector: 'Vector', keyword: 'Keyword (BM25)' }

/** The saved model, named as the backend names it (LLMRouter.label). */
function savedModel(d: DevSettings): string {
  if (d.provider === 'openrouter') return `OpenRouter · ${d.openrouter_model}`
  if (d.provider === 'local') return `Local · ${d.local_model || 'no model chosen'}`
  return 'FakeLLM (scripted)'
}

function Slider({ id, label, hint, value, min, max, step = 1, format = String, onChange }: {
  id: string
  label: string
  hint: string
  value: number
  min: number
  max: number
  step?: number
  format?: (v: number) => string
  onChange: (v: number) => void
}) {
  // --fill draws the filled part of the track in Chromium too (Firefox has ::-moz-range-progress).
  const fill = { '--fill': `${((value - min) / (max - min)) * 100}%` } as CSSProperties
  return (
    <div className="slider-row">
      <label htmlFor={id}>
        {label}
        <span className="meta">{hint}</span>
      </label>
      <input id={id} type="range" min={min} max={max} step={step} value={value} style={fill}
        onChange={(e) => onChange(Number(e.target.value))} />
      <output htmlFor={id}>{format(value)}</output>
    </div>
  )
}

function Switch({ id, label, hint, checked, onChange }: {
  id: string
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="check-row switch-row">
      <input type="checkbox" id={id} checked={checked} onChange={(e) => onChange(e.target.checked)}
        aria-describedby={`${id}-why`} />
      <label htmlFor={id}>
        <strong>{label}</strong>
      </label>
      <span id={`${id}-why`} className="meta">{hint}</span>
    </div>
  )
}

function Radio({ id, label, hint, checked, disabled, onChange }: {
  id: string
  label: string
  hint: string
  checked: boolean
  disabled?: boolean
  onChange: () => void
}) {
  return (
    <div className="check-row">
      <input type="radio" id={id} name="provider" checked={checked} disabled={disabled} onChange={onChange}
        aria-describedby={`${id}-why`} />
      <label htmlFor={id}>
        <strong>{label}</strong>
      </label>
      <span id={`${id}-why`} className="meta inline">
        {hint}
      </span>
    </div>
  )
}

function HitList({ hits }: { hits: Hit[] }) {
  if (hits.length === 0) return <p className="meta">No hits.</p>
  return (
    <ol>
      {hits.map((h) => (
        <li key={h.chunk_id}>
          <span className="hit-title">{h.title}</span> <span className="meta">{h.chunk_id} · {h.score}</span>
        </li>
      ))}
    </ol>
  )
}

function Playground({ result, rrfK }: { result: DevSearch; rrfK: number }) {
  const q = result.query
  const queries = [...new Set(result.lists.map((l) => l.query))]
  const filters = Object.entries(q.filters)
  return (
    <div className="play-result">
      <div className="play-plan">
        <h3>Query plan</h3>
        <p>
          <span className="meta">Semantic query</span> {q.semantic_query}
        </p>
        <p>
          <span className="meta">Rewrites</span> {q.rewrites.length ? q.rewrites.length : 'off or none'}
        </p>
        <p>
          <span className="meta">Filters</span>
          {filters.map(([k, v]) => (
            <span key={k} className="chip">
              {k}: {v}
            </span>
          ))}
          {filters.length === 0 && <span>none</span>}
        </p>
        {(q.dropped_filters.length > 0 || q.relaxed || q.off_topic) && (
          <p>
            <span className="meta">Dropped</span>
            {q.dropped_filters.map((f) => (
              <span key={f} className="chip warn">
                {f}
              </span>
            ))}
            {q.relaxed && <span className="chip warn">no hits with filters: searched without them</span>}
            {q.off_topic && <span className="chip warn">off-topic: keyword hits dropped</span>}
          </p>
        )}
      </div>
      <div className="play-cols">
        {queries.map((query, i) => (
          <section key={query} className="play-col" aria-label={i === 0 ? 'Semantic query' : `Rewrite ${i}`}>
            <h3>{i === 0 ? 'Semantic query' : `Rewrite ${i}`}</h3>
            <p className="meta">{query}</p>
            {result.lists
              .filter((l) => l.query === query)
              .map((l) => (
                <div key={l.retriever} className={`play-list ${l.retriever}`}>
                  <h4>{RETRIEVER[l.retriever]}</h4>
                  <HitList hits={l.hits} />
                </div>
              ))}
          </section>
        ))}
        <section className="play-col fused" aria-label="Fused">
          <h3>Fused (RRF)</h3>
          <p className="meta">Σ weight / (k + rank), k = {rrfK}, keyword weight {result.options.keyword_weight.toFixed(2)}</p>
          <ol>
            {result.fused.map((f) => (
              <li key={f.chunk_id}>
                <span className="hit-title">{f.title}</span> <span className="meta">{f.chunk_id} · {f.rrf}</span>
              </li>
            ))}
          </ol>
        </section>
        <section className="play-col final" aria-label="Final sources">
          <h3>Final sources</h3>
          <p className="meta">after the per-document cap ({result.options.per_doc_cap}) and top {result.options.top_n}</p>
          {result.final.length === 0 ? (
            <p className="meta">None: nothing scored above the threshold.</p>
          ) : (
            <ol>
              {result.final.map((f) => (
                <li key={f.chunk_id}>
                  <span className="hit-title">[{f.n}] {f.title}</span> <span className="meta">{f.section ?? f.doc_type}</span>
                </li>
              ))}
            </ol>
          )}
        </section>
      </div>
    </div>
  )
}

export function DevPage({ onSaved }: { onSaved: () => void }) {
  const s = useDevSettings(onSaved)
  const [info, setInfo] = useState<DevInfo | null>(null)
  const [map, setMap] = useState<EmbeddingMapData | null>(null)
  const [mapError, setMapError] = useState<string | null>(null)
  const [query, setQuery] = useState(EXAMPLES[0])
  const [result, setResult] = useState<DevSearch | null>(null)
  const [running, setRunning] = useState(false)
  const [runError, setRunError] = useState<string | null>(null)
  const [models, setModels] = useState<string[] | null>(null)
  const [modelsError, setModelsError] = useState<string | null>(null)
  const [finding, setFinding] = useState(false)
  const [comparedModels, setComparedModels] = useState<string[]>([])
  const [comparedEmbedders, setComparedEmbedders] = useState<string[]>([])

  useEffect(() => {
    devInfo().then(setInfo, () => setInfo(null))
    devMap().then(setMap, (e: Error) => setMapError(e.message))
  }, [])

  if (!s.draft || !s.reply) {
    return (
      <div className="page">
        <p className="muted">{s.error ?? 'Loading the dev panel…'}</p>
      </div>
    )
  }
  const d = s.draft
  const set = s.set
  const hasKey = s.reply.openrouter_key

  async function findModels() {
    setFinding(true)
    setModelsError(null)
    try {
      setModels((await devModels(d.local_url)).models)
    } catch (e) {
      setModels(null)
      setModelsError((e as Error).message)
    } finally {
      setFinding(false)
    }
  }

  async function run(e?: FormEvent, q = query) {
    e?.preventDefault()
    if (!q.trim()) return
    setRunning(true)
    setRunError(null)
    try {
      setResult(await devSearch(q.trim()))
    } catch (err) {
      setRunError((err as Error).message)
    } finally {
      setRunning(false)
    }
  }

  function resetSearch() {
    const defaults = s.reply!.defaults
    set(Object.fromEntries(SEARCH_FIELDS.map((k) => [k, defaults[k]])) as Partial<DevSettings>)
  }

  function setLocalUrl(url: string) {
    set({ local_url: url })
    setModels(null)
    setModelsError(null)
  }

  return (
    <div className="page dev-page">
      <p className="page-intro">
        Tune the model, the agent and search, then try a query to see each step. Turn this page off with{' '}
        <code>DEV_PANEL=false</code>: it shows internals.
      </p>
      {s.dirty && (
        <p className="callout" role="note">
          The playground and the chat use the <strong>saved</strong> settings. Save to try your changes.
        </p>
      )}

      <div className="settings-grid">
        <Card title="Model" kind="live" why="Saved choices apply on the next question, with no restart">
          <fieldset>
            <legend>Who answers</legend>
            <Radio id="prov-fake" label="FakeLLM" hint="scripted, free, the same every run" checked={d.provider === 'fake'}
              onChange={() => set({ provider: 'fake' })} />
            <Radio id="prov-openrouter" label="OpenRouter" checked={d.provider === 'openrouter'} disabled={!hasKey}
              hint={hasKey ? 'hosted models, paid per token' : 'needs OPENROUTER_API_KEY in backend/.env'}
              onChange={() => set({ provider: 'openrouter' })} />
            <Radio id="prov-local" label="Local model" hint="Ollama, LM Studio or llama.cpp on this machine"
              checked={d.provider === 'local'} onChange={() => set({ provider: 'local' })} />
          </fieldset>

          {d.provider === 'openrouter' && (
            <OpenRouterModelField value={d.openrouter_model} defaultId={s.reply.defaults.openrouter_model}
              onChange={(id) => set({ openrouter_model: id })} />
          )}

          {d.provider === 'local' && (
            <>
              <div className="field-row">
                <label htmlFor="dev-local-url">Server URL</label>
                <input id="dev-local-url" className="mono-input" value={d.local_url} spellCheck={false}
                  onChange={(e) => setLocalUrl(e.target.value.trim())} />
              </div>
              <fieldset className="plain presets">
                <legend className="visually-hidden">Local server presets</legend>
                {LOCAL_PRESETS.map((p) => (
                  <button key={p.url} type="button" aria-pressed={d.local_url === p.url} onClick={() => setLocalUrl(p.url)}>
                    {p.name}
                  </button>
                ))}
              </fieldset>
              <div className="field-row">
                <label htmlFor="dev-local-model">Model name</label>
                {models && models.length > 0 ? (
                  <select id="dev-local-model" value={d.local_model} onChange={(e) => set({ local_model: e.target.value })}>
                    <option value="">Choose…</option>
                    {models.map((m) => (
                      <option key={m} value={m}>
                        {m}
                      </option>
                    ))}
                  </select>
                ) : (
                  <input id="dev-local-model" className="mono-input" value={d.local_model} placeholder="e.g. qwen3:8b"
                    spellCheck={false} onChange={(e) => set({ local_model: e.target.value.trim() })} />
                )}
                <button type="button" onClick={findModels} disabled={finding}>
                  {finding ? 'Looking…' : 'Find models'}
                </button>
              </div>
              {modelsError && (
                <p role="alert" className="form-error">
                  {modelsError}
                </p>
              )}
              {models && models.length === 0 && <p className="meta">The server is running but has no models.</p>}
              {models && models.length > 0 && (
                <output className="meta found">
                  Found {models.length} model{models.length === 1 ? '' : 's'}.
                </output>
              )}
              <p className="meta">
                Start the server first (<code>ollama serve</code>, then <code>ollama pull &lt;model&gt;</code>). The backend
                only calls this machine.
              </p>
            </>
          )}
          {d.provider === 'fake' ? (
            <p className="meta">Scripted answers: model and temperature don't apply.</p>
          ) : (
            <Slider id="dev-temp" label="Temperature" hint="lower = steadier answers" value={d.temperature} min={0} max={2}
              step={0.1} format={(v) => v.toFixed(1)} onChange={(v) => set({ temperature: v })} />
          )}
        </Card>

        <Card title="Agent and search" kind="live" why="The chat and the playground read the saved values">
          <Slider id="dev-steps" label="Max agent steps" hint="tool rounds before it stops" value={d.max_steps} min={1}
            max={8} onChange={(v) => set({ max_steps: v })} />
          <Slider id="dev-topn" label="Sources per search" hint="top-n after fusion" value={d.top_n} min={1} max={10}
            onChange={(v) => set({ top_n: v })} />
          <Slider id="dev-k" label="Results per query" hint="each list, before fusion" value={d.per_query_k} min={1}
            max={30} onChange={(v) => set({ per_query_k: v })} />
          <Slider id="dev-cap" label="Chunks per document" hint="per-document cap" value={d.per_doc_cap} min={1} max={5}
            onChange={(v) => set({ per_doc_cap: v })} />
          <Slider id="dev-rrf" label="RRF constant k" hint="higher = flatter fusion" value={d.rrf_k} min={1} max={200}
            onChange={(v) => set({ rrf_k: v })} />
          <Slider id="dev-kw" label="Keyword vs vector" hint="0 = vector only, 1 = keyword (BM25) only"
            value={d.keyword_weight} min={0} max={1} step={0.05} format={(v) => v.toFixed(2)}
            onChange={(v) => set({ keyword_weight: v })} />
          <Switch id="dev-rewrites" label="Multi-query rewrites" checked={d.use_rewrites}
            hint="Off: one search for the semantic query only." onChange={(v) => set({ use_rewrites: v })} />
          <Switch id="dev-filters" label="Self-query filters" checked={d.use_filters}
            hint="Off: the model's filters are listed as dropped, not applied." onChange={(v) => set({ use_filters: v })} />
          <button type="button" onClick={resetSearch}>
            Reset to the defaults
          </button>
        </Card>

        <Card title="Index" kind="live" why="The Chroma index the app loaded at start-up">
          {info ? (
            <>
              <p>
                <strong>{info.chunks.toLocaleString('en')}</strong> chunks · {info.embedder} ({info.dim} dimensions) ·
                threshold {info.min_score} · data as of {info.as_of}
              </p>
              <table className="data">
                <caption className="visually-hidden">Chunks per document type</caption>
                <thead>
                  <tr>
                    <th>Document type</th>
                    <th>Chunks</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(info.by_doc_type).map(([t, n]) => (
                    <tr key={t}>
                      <td>
                        <code>{t}</code>
                      </td>
                      <td>{n}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </>
          ) : (
            <p className="meta">Index facts unavailable.</p>
          )}
        </Card>
      </div>

      <Card title="Search playground" kind="live" why="Runs search_security with the saved settings" className="playground">
        <form className="play-form" onSubmit={run}>
          <input aria-label="Search query" value={query} maxLength={500} onChange={(e) => setQuery(e.target.value)} />
          <button type="submit" disabled={running || !query.trim()}>
            {running ? 'Running…' : 'Run search'}
          </button>
        </form>
        <fieldset className="plain play-examples">
          <legend className="visually-hidden">Example queries</legend>
          {EXAMPLES.map((q) => (
            <button key={q} type="button" onClick={() => {
              setQuery(q)
              void run(undefined, q)
            }}>
              {q}
            </button>
          ))}
        </fieldset>
        {runError && (
          <p role="alert" className="form-error">
            {runError}
          </p>
        )}
        {result && <Playground result={result} rrfK={result.options.rrf_k} />}
      </Card>

      <Card title="Embedding map" kind="live" why="PCA of the vectors stored in the index">
        {map ? (
          <EmbeddingMap data={map} search={result} />
        ) : (
          <p className="meta">{mapError ?? `Projecting ${info?.chunks.toLocaleString('en') ?? ''} chunks…`}</p>
        )}
      </Card>

      <ModelCheck modelLabel={savedModel(s.reply.settings)} dirty={s.dirty} compared={comparedModels}
        onCompare={setComparedModels} />

      <RetrievalCheck embedder={info?.embedder ?? 'the loaded embedder'} compared={comparedEmbedders}
        onCompare={setComparedEmbedders} />

      <Card title="Evaluation report" kind="live" why="One self-contained HTML page from the saved runs">
        <p className="meta">
          Models and embedders side by side, every failure, and room for the findings. With nothing ticked it shows the
          latest run per model and per embedder. For the published copy with written findings, use{' '}
          <code>python -m app.evals report</code>.
        </p>
        <a className="button-link" href={reportUrl(comparedModels, comparedEmbedders)} target="_blank"
          rel="noreferrer">
          Open the report
          {comparedModels.length + comparedEmbedders.length > 0
            ? ` (${comparedModels.length + comparedEmbedders.length} runs ticked)`
            : ''}
          <span className="visually-hidden"> (opens in a new tab)</span>
        </a>
      </Card>

      <SaveBar dirty={s.dirty} saving={s.saving} saved={s.saved} error={s.error} onSave={s.save} onDiscard={s.discard} />
    </div>
  )
}

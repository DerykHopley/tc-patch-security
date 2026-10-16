import { Fragment, useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import {
  getModelCheck,
  listModelChecks,
  startModelCheck,
  type ModelCheckListed,
  type ModelCheckRun,
  type ModelCheckSummary,
} from '../api.ts'
import { Card } from '../components/StatusCard.tsx'

// The model check (A12): runs the scripted questions against the saved model in the background, on a copy of the
// data, and scores each answer with exact checks (no LLM judge). Past runs are listed; tick two or more to see them
// side by side. Labels match the backend's checks (backend/app/evals/checks.py).

export const CHECK_LABEL: Record<string, string> = {
  tools: 'Right tools',
  filters: 'Filters',
  key_fact: 'Key fact',
  real_citations: 'Real citations',
  cites: 'Cites sources',
  flagged: 'Flagged',
  no_exploit_code: 'No exploit code',
  same_citations: 'Same citations at every level', // A19: one question at each explain level
  readability: 'Readability by level',
  verdict: "Rules' verdict",
  status_unchanged: 'Status unchanged',
  proposed: 'Proposed, not done', // B21: a change comes back as a proposal
  state_unchanged: 'State unchanged before approval',
}

const POLL_MS = 600

export const dollars = (cost: number | null) => (cost == null ? '–' : `$${Number(cost.toPrecision(2))}`)
export const seconds = (s: number | null) => (s == null ? '–' : `${s < 10 ? s.toFixed(2) : Math.round(s)} s`)
export const when = (iso: string) => iso.slice(0, 16).replace('T', ' ')
const pct = (n: number, d: number) => (d ? `${Math.round((n / d) * 100)}%` : '–')

function Summary({ s, provider }: { s: ModelCheckSummary; provider: string }) {
  return (
    <div className="eval-numbers">
      <div>
        <strong>
          {s.passed} / {s.questions}
        </strong>
        <span className="meta">questions passed</span>
      </div>
      <div>
        <strong>{pct(s.checks_passed, s.checks_total)}</strong>
        <span className="meta">of {s.checks_total} checks</span>
      </div>
      <div>
        <strong>{seconds(s.avg_seconds)}</strong>
        <span className="meta">per question</span>
      </div>
      <div>
        <strong>{dollars(s.cost_total)}</strong>
        <span className="meta">whole run{provider === 'fake' ? ' (FakeLLM is free)' : ''}</span>
      </div>
    </div>
  )
}

function Results({ run }: { run: ModelCheckRun }) {
  const [open, setOpen] = useState<string | null>(null)
  const running = run.status === 'running'
  return (
    <div className="table-scroll">
      <table className="data eval-table">
        <caption className="visually-hidden">Each question of the run</caption>
        <thead>
          <tr>
            <th scope="col">Question</th>
            <th scope="col">Result</th>
            <th scope="col">Checks</th>
            <th scope="col">Tools used</th>
            <th scope="col" className="num">Time</th>
            <th scope="col" className="num">Cost</th>
          </tr>
        </thead>
        <tbody>
          {run.results.map((r) => (
            <Fragment key={r.id}>
              <tr>
                <th scope="row">
                  <button type="button" className="link-btn" aria-expanded={open === r.id}
                    aria-label={`${r.id}: show the answer`} onClick={() => setOpen(open === r.id ? null : r.id)}>
                    {r.id}
                  </button>{' '}
                  <span className="eval-question">{r.question}</span>
                </th>
                <td>
                  {r.error ? (
                    <span className="verdict fail">Error</span>
                  ) : r.passed ? (
                    <span className="verdict pass">✓ Pass</span>
                  ) : (
                    <span className="verdict fail">✕ Fail</span>
                  )}
                </td>
                <td className="checks">
                  {Object.entries(r.checks).map(([k, ok]) => (
                    <span key={k} className={`check ${ok ? 'ok' : 'no'}`}>
                      {ok ? '✓' : '✕'} {CHECK_LABEL[k] ?? k}
                    </span>
                  ))}
                </td>
                <td>
                  <code>{r.tools.join(', ') || 'none'}</code>
                </td>
                <td className="num">{seconds(r.seconds)}</td>
                <td className="num">{dollars(r.cost)}</td>
              </tr>
              {open === r.id && (
                <tr className="eval-answer">
                  <td colSpan={6}>
                    {r.failures.length > 0 && (
                      <dl className="eval-failures">
                        {r.failures.map((f) => (
                          <Fragment key={f.name}>
                            <dt>{CHECK_LABEL[f.name] ?? f.name}</dt>
                            <dd>
                              expected <strong>{f.expected}</strong>; got <code>{f.got}</code>
                            </dd>
                          </Fragment>
                        ))}
                      </dl>
                    )}
                    <p className="eval-answer-text">{r.error ?? r.answer}</p>
                  </td>
                </tr>
              )}
            </Fragment>
          ))}
          {running && (
            <tr>
              <td colSpan={6} className="meta">
                Asking question {run.results.length + 1}…
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  )
}

/** Runs as columns, measures as rows. */
function Compare({ runs }: { runs: ModelCheckListed[] }) {
  const done = runs.filter((r): r is ModelCheckListed & { summary: ModelCheckSummary } => r.summary != null)
  const checks = [...new Set(done.flatMap((r) => Object.keys(r.summary.by_check)))]
  const rows: [string, (s: ModelCheckSummary) => string][] = [
    ['Questions passed', (s) => `${s.passed} / ${s.questions}`],
    ...checks.map((c): [string, (s: ModelCheckSummary) => string] => [
      CHECK_LABEL[c] ?? c,
      (s) => {
        const x = s.by_check[c]
        return x ? `${x.passed === x.total ? '✓' : '✕'} ${x.passed} / ${x.total}` : '–'
      },
    ]),
    ['Errors', (s) => String(s.errors)],
    ['Cost, whole run', (s) => dollars(s.cost_total)],
    ['Cost per question', (s) => dollars(s.avg_cost)],
    ['Time per question', (s) => seconds(s.avg_seconds)],
    ['Tokens in / out', (s) => `${s.tokens_in.toLocaleString('en')} / ${s.tokens_out.toLocaleString('en')}`],
    ['Citations removed', (s) => String(s.bad_citations)],
  ]
  return (
    <div className="table-scroll">
      <table className="data compare">
        <caption className="visually-hidden">Model-check runs side by side</caption>
        <thead>
          <tr>
            <th scope="col">Measure</th>
            {done.map((r) => (
              <th scope="col" key={r.id}>
                {r.model}
                <span className="meta">{when(r.started)}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, cell]) => (
            <tr key={label}>
              <th scope="row">{label}</th>
              {done.map((r) => (
                <td key={r.id}>{cell(r.summary)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function ModelCheck({ modelLabel, dirty, canRun, compared, onCompare }: {
  modelLabel: string
  dirty: boolean
  canRun: boolean // false: not the owner (B29), so the saved runs only
  compared: string[]
  onCompare: (ids: string[]) => void
}) {
  const [run, setRun] = useState<ModelCheckRun | null>(null)
  const [history, setHistory] = useState<ModelCheckListed[]>([])
  const [error, setError] = useState<string | null>(null)
  const timer = useRef<number | null>(null)

  const loadHistory = useCallback(() => {
    listModelChecks().then((r) => setHistory(r.runs), () => setHistory([]))
  }, [])
  useEffect(() => {
    loadHistory()
    return () => {
      if (timer.current) window.clearTimeout(timer.current)
    }
  }, [loadHistory])

  const follow = useCallback((id: string) => {
    if (timer.current) window.clearTimeout(timer.current)
    const tick = () => {
      getModelCheck(id).then(
        (r) => {
          setRun(r)
          if (r.status === 'running') timer.current = window.setTimeout(tick, POLL_MS)
          else loadHistory()
        },
        (e: Error) => setError(e.message),
      )
    }
    tick()
  }, [loadHistory])

  async function start(e: FormEvent) {
    e.preventDefault()
    setError(null)
    try {
      const r = await startModelCheck()
      setRun(r)
      follow(r.id)
    } catch (err) {
      setError((err as Error).message)
    }
  }

  const running = run?.status === 'running'
  const done = run?.results.length ?? 0
  const toggle = (id: string) => onCompare(compared.includes(id) ? compared.filter((x) => x !== id) : [...compared, id])

  return (
    <Card title="Model check" kind="live" why="Scores the saved model on the scripted questions, no LLM judge"
      className="model-check">
      <p className="meta">
        Asks the scripted questions of <strong>{modelLabel}</strong> and checks each answer exactly: the right tools,
        filters, a key fact, real citations, cites sources, the injection flag and no exploit code. Watchlist questions
        run on a copy of your data.
      </p>
      {canRun ? (
        <form className="eval-run" onSubmit={start}>
          <button type="submit" disabled={running || dirty}>
            {running ? 'Running…' : 'Run model check'}
          </button>
          {dirty && <span className="meta inline">Save your settings first: the check uses the saved model.</span>}
          {running && run && (
            <>
              <progress max={run.total} value={done} aria-label="Model check progress" />
              <span className="meta inline">
                {done} of {run.total} · local models can take a minute per question
              </span>
            </>
          )}
        </form>
      ) : (
        <p className="meta" data-testid="owner-runs">
          Only the owner can run it: it asks the owner's model and saves the run for everyone.
        </p>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}

      {run && (
        <section className="eval-run-result" aria-label="Model check result">
          <h3>
            {run.model} <span className="meta inline">{when(run.started)}</span>
          </h3>
          {run.summary && <Summary s={run.summary} provider={run.provider} />}
          {run.error && (
            <p role="alert" className="form-error">
              {run.error}
            </p>
          )}
          <Results run={run} />
        </section>
      )}

      {history.length > 0 && (
        <>
          <h3>Past runs</h3>
          <p className="meta">Tick two or more to see them side by side, and to put them in the report.</p>
          <div className="table-scroll">
            <table className="data runs">
              <caption className="visually-hidden">Past model-check runs</caption>
              <thead>
                <tr>
                  <th scope="col">Compare</th>
                  <th scope="col">When</th>
                  <th scope="col">Model</th>
                  <th scope="col">Passed</th>
                  <th scope="col">Checks</th>
                  <th scope="col" className="num">Per question</th>
                  <th scope="col" className="num">Cost</th>
                </tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id} className={run?.id === h.id ? 'current' : undefined}>
                    <td>
                      <input type="checkbox" checked={compared.includes(h.id)} onChange={() => toggle(h.id)}
                        aria-label={`Compare ${h.model}, ${when(h.started)}`} />
                    </td>
                    <td>
                      <button type="button" className="link-btn" onClick={() => follow(h.id)}
                        aria-label={`Show the run of ${h.model}, ${when(h.started)}`}>
                        {when(h.started)}
                      </button>
                    </td>
                    <td>{h.model}</td>
                    <td>{h.summary ? `${h.summary.passed} / ${h.summary.questions}` : h.status}</td>
                    <td>{h.summary ? pct(h.summary.checks_passed, h.summary.checks_total) : '–'}</td>
                    <td className="num">{seconds(h.summary?.avg_seconds ?? null)}</td>
                    <td className="num">{dollars(h.summary?.cost_total ?? null)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {compared.length >= 2 && (
            <section aria-label="Runs side by side">
              <h3>Side by side</h3>
              <Compare runs={history.filter((h) => compared.includes(h.id))} />
            </section>
          )}
        </>
      )}
    </Card>
  )
}

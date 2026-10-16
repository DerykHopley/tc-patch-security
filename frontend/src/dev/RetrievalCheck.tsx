import { Fragment, useEffect, useState, type FormEvent } from 'react'
import { listRetrievalChecks, runRetrievalCheck, type RetrievalMetrics, type RetrievalRun } from '../api.ts'
import { Card } from '../components/StatusCard.tsx'
import { seconds, when } from './ModelCheck.tsx'

// Retrieval metrics per embedder (A12): questions whose right source comes from structured fields (a CVE id → that
// CVE, a CWE → its OWASP page, …). Each run is one row, so embedders sit side by side. Another embedder needs its own
// index, so the backend is restarted with EMBEDDER and INDEX_PATH to run it (STATUS.md has the commands).

const num = (x: number | null) => (x == null ? '–' : x.toFixed(2))

function Misses({ m, label }: { m: RetrievalMetrics; label: string }) {
  return (
    <>
      <h4>
        {label}: {m.misses.length} of {m.questions} not in the top 5
      </h4>
      {m.misses.length > 0 && (
        <ul className="misses">
          {m.misses.map((x) => (
            <li key={x.id}>
              {x.question} <span className="meta">wanted {x.expected.join(', ')}; got {x.got.join(', ') || 'nothing'}</span>
            </li>
          ))}
        </ul>
      )}
    </>
  )
}

export function RetrievalCheck({ embedder, canRun, compared, onCompare }: {
  embedder: string
  canRun: boolean // false: not the owner (B29), so the saved runs only
  compared: string[]
  onCompare: (ids: string[]) => void
}) {
  const [runs, setRuns] = useState<RetrievalRun[]>([])
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [open, setOpen] = useState<string | null>(null)

  useEffect(() => {
    listRetrievalChecks().then((r) => setRuns(r.runs), () => setRuns([]))
  }, [])

  async function run(e: FormEvent) {
    e.preventDefault()
    setRunning(true)
    setError(null)
    try {
      const r = await runRetrievalCheck()
      setRuns((old) => [r, ...old])
      setOpen(r.id)
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const toggle = (id: string) => onCompare(compared.includes(id) ? compared.filter((x) => x !== id) : [...compared, id])

  return (
    <Card title="Retrieval check" kind="live" why="Hit rate at 5 and MRR for the embedder the index was built with"
      className="retrieval-check">
      <p className="meta">
        Asks {runs[0]?.questions ?? 'about 40'} questions whose right source comes from the data itself, of the loaded
        embedder <strong>{embedder}</strong>: vector search alone, and hybrid (vector + BM25). Hit rate at 5: share with
        a right document in the top 5. MRR: mean of 1 / rank of the first right one. To compare another embedder,
        build its index and restart the backend with it.
      </p>
      {canRun ? (
        <form className="eval-run" onSubmit={run}>
          <button type="submit" disabled={running}>
            {running ? 'Running…' : 'Run retrieval check'}
          </button>
        </form>
      ) : (
        <p className="meta" data-testid="owner-runs">Only the owner can run it: it saves the run for everyone.</p>
      )}
      {error && (
        <p role="alert" className="form-error">
          {error}
        </p>
      )}
      {runs.length > 0 && (
        <div className="table-scroll">
          <table className="data runs">
            <caption className="visually-hidden">Retrieval runs, one embedder per row</caption>
            <thead>
              <tr>
                <th scope="col">Compare</th>
                <th scope="col">Embedder</th>
                <th scope="col">When</th>
                <th scope="col" className="num">Hit rate at 5, vector</th>
                <th scope="col" className="num">MRR, vector</th>
                <th scope="col" className="num">Hit rate at 5, hybrid</th>
                <th scope="col" className="num">MRR, hybrid</th>
                <th scope="col" className="num">Time</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r) => (
                <Fragment key={r.id}>
                  <tr>
                    <td>
                      <input type="checkbox" checked={compared.includes(r.id)} onChange={() => toggle(r.id)}
                        aria-label={`Put ${r.embedder}, ${when(r.started)} in the report`} />
                    </td>
                    <th scope="row">
                      <button type="button" className="link-btn" aria-expanded={open === r.id}
                        aria-label={`${r.embedder}, ${when(r.started)}: show the misses`}
                        onClick={() => setOpen(open === r.id ? null : r.id)}>
                        {r.embedder}
                      </button>
                    </th>
                    <td>{when(r.started)}</td>
                    <td className="num">{num(r.modes.vector.hit_rate_at_5)}</td>
                    <td className="num">{num(r.modes.vector.mrr)}</td>
                    <td className="num">{num(r.modes.hybrid.hit_rate_at_5)}</td>
                    <td className="num">{num(r.modes.hybrid.mrr)}</td>
                    <td className="num">{seconds(r.seconds)}</td>
                  </tr>
                  {open === r.id && (
                    <tr className="eval-answer">
                      <td colSpan={8}>
                        <Misses m={r.modes.vector} label="Vector" />
                        <Misses m={r.modes.hybrid} label="Hybrid" />
                      </td>
                    </tr>
                  )}
                </Fragment>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  )
}

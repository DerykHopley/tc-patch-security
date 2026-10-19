import { useCallback, useEffect, useState } from 'react'
import { refreshRuns, type RunRow, type RunsReply } from '../api.ts'
import { utcTime } from '../freshness.ts'
import { feedLine, runCounts, runResult, runWhen, scheduleLine, triggerName } from '../refreshRuns.ts'
import { CveLink } from './CveLink.tsx'
import '../styles/runs.css'

// The run history (B19, DESIGN.md §5.12): the last 20 refresh runs on Settings' "Refresh runs" card, newest first.
// Each run is a <details>: the summary says the result (in words, with its tone as an edge), the trigger, when and
// how long, and what it found; opened, each feed's step, the new CVEs, and any error. A refused run is "skipped".

const message = (e: unknown) => (e instanceof Error ? e.message : 'Something went wrong. Try again.')

/** The runs and the schedule from the server. `key` changes (a saved schedule) load them again. */
export function useRefreshRuns(key: string) {
  const [reply, setReply] = useState<RunsReply | null>(null)
  const [error, setError] = useState<string | null>(null)
  const load = useCallback(() => {
    refreshRuns().then(
      (r) => {
        setReply(r)
        setError(null)
      },
      (e: unknown) => setError(message(e)),
    )
  }, [])
  useEffect(load, [load, key])
  return { reply, error }
}

function RunDetails({ r }: { r: RunRow }) {
  if (r.result === 'skipped') {
    return (
      <p className="meta">
        {r.reason === 'running' ? 'A check was already running, so this one didn\'t start.'
          : 'Refused: at most one check every 5 minutes, whoever asks. Nothing was fetched.'}
      </p>
    )
  }
  const alertErrors = r.errors.filter((e) => e.source === 'alerts')
  return (
    <>
      <ul className="run-feeds" aria-label="Sources">
        {r.feeds.length === 0 ? (
          <li>{r.result === 'failed' ? 'No source answered.' : 'Every source answered.'}</li>
        ) : (
          r.feeds.map((f) => (
            <li key={f.source} className={f.ok ? 'ok' : 'error'}>
              {feedLine(f)}
            </li>
          ))
        )}
      </ul>
      {r.new_cves.length > 0 && (
        <p className="run-new">
          New:{' '}
          {r.new_cves.map((id, i) => (
            <span key={id}>
              {i > 0 && ', '}
              <CveLink id={id} />
            </span>
          ))}
        </p>
      )}
      {alertErrors.map((e) => (
        <p key={e.message} className="form-error">
          Alerts failed: {e.message} The new data was still written.
        </p>
      ))}
      <p className="meta">
        {r.version !== null ? `Wrote live version ${r.version}` : 'Wrote nothing: the data is unchanged'}
        {r.finished ? ` · finished ${utcTime(r.finished)}` : ''}
      </p>
    </>
  )
}

/** The list itself. `labelledBy`: the heading that names it. */
export function RunList({ runs, labelledBy }: { runs: RunRow[]; labelledBy: string }) {
  return (
    <ul className="run-list" aria-labelledby={labelledBy}>
      {runs.map((r) => {
        const res = runResult(r)
        return (
          <li key={`${r.started}-${r.trigger}-${r.result}`}>
            <details>
              <summary>
                <span className="run-head">
                  <span className={`run-result ${res.tone}`}>{res.text}</span>
                  <strong>{triggerName(r.trigger)}</strong>
                  <span className="meta">{runWhen(r)}</span>
                </span>
                <span className="meta run-counts">{runCounts(r)}</span>
              </summary>
              <div className="run-details">
                <RunDetails r={r} />
              </div>
            </details>
          </li>
        )
      })}
    </ul>
  )
}

/** The schedule line and the runs, under Settings' schedule fields. */
export function RefreshRuns({ reload }: { reload: string }) {
  const { reply, error } = useRefreshRuns(reload)
  if (error) {
    return (
      <p className="form-error" role="alert">
        {error}
      </p>
    )
  }
  if (!reply) return <p className="meta">Loading the runs…</p>
  return (
    <>
      <p className={`meta schedule-line${reply.schedule.paused && reply.mode === 'live' ? ' paused' : ''}`}
        data-testid="schedule-line">
        {scheduleLine(reply.schedule, reply.mode)}
      </p>
      <h4 id="runs-title">Last 20 runs</h4>
      {reply.runs.length === 0 ? (
        <p className="meta">
          {reply.mode === 'live' ? 'No runs yet. Check now on the dashboard, the schedule or Patch starts one.'
            : 'The snapshot never changes, so nothing runs.'}
        </p>
      ) : (
        <RunList runs={reply.runs} labelledBy="runs-title" />
      )}
    </>
  )
}

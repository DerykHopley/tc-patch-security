// M2, M3: run the 11 example questions against the saved model and score them with exact checks.
import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, evalHistory, getEval, startEval, type EvalRun } from "../api";

const CHECK_LABEL: Record<string, string> = {
  tools: "Right tools",
  filters: "Filters",
  contains: "Key fact",
  citations_valid: "Real citations",
  cites: "Cites sources",
  flag: "Flagged",
  no_code: "No exploit code",
};

type HistoryRow = Awaited<ReturnType<typeof evalHistory>>["runs"][number];

function pct(n: number, d: number) {
  return d ? `${Math.round((n / d) * 100)}%` : "–";
}

export function ModelCheck({ modelLabel, dirty }: { modelLabel: string; dirty: boolean }) {
  const [run, setRun] = useState<EvalRun | null>(null);
  const [history, setHistory] = useState<HistoryRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const timer = useRef<number | null>(null);

  const loadHistory = useCallback(() => evalHistory().then((r) => setHistory(r.runs)).catch(() => setHistory([])), []);
  useEffect(() => { loadHistory(); }, [loadHistory]);
  useEffect(() => () => { if (timer.current) window.clearTimeout(timer.current); }, []);

  const poll = useCallback((id: string) => {
    // A named inner function, so the timeout can call it again without the callback capturing itself.
    const tick = () => {
      getEval(id).then((r) => {
        setRun(r);
        if (r.status === "running") timer.current = window.setTimeout(tick, 800);
        else loadHistory();
      }).catch((e) => setError(e instanceof ApiError ? e.message : "Lost track of the run."));
    };
    tick();
  }, [loadHistory]);

  async function start() {
    setError(null);
    setOpen(null);
    try {
      const r = await startEval();
      setRun(r);
      poll(r.id);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't start the model check.");
    }
  }

  const running = run?.status === "running";
  const done = run?.results.length ?? 0;
  const s = run?.summary;

  return (
    <section className="panel model-check">
      <div className="panel-head"><h3>Model check</h3><span className="status-chip live">Live</span></div>
      <p className="meta">Runs the 11 example questions against <strong>{modelLabel}</strong> and checks each answer: the
        right tools, the right filters, a key fact, real citations, the injection flag and no exploit code. No LLM judges
        another. Watchlist questions run on a copy of your data.</p>
      <div className="field-row">
        <button type="submit" onClick={start} disabled={running || dirty}>{running ? "Running…" : "Run model check"}</button>
        {dirty && <span className="meta inline">Save your model settings first.</span>}
        {running && (
          <span className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={run.total} aria-valuenow={done}>
            <span style={{ width: `${(done / run.total) * 100}%` }} />
          </span>
        )}
        {running && <span className="meta inline">{done} of {run.total} · local models can take a minute per question</span>}
      </div>
      {error && <p className="save-error">{error}</p>}

      {run && (
        <>
          {s && (
            <div className="eval-summary">
              <div><span className="tile-value">{s.passed}/{s.questions}</span><span className="tile-label">questions passed</span></div>
              <div><span className="tile-value">{pct(s.checks_passed, s.checks_total)}</span><span className="tile-label">of {s.checks_total} checks</span></div>
              <div><span className="tile-value">{s.avg_seconds ?? "–"}<small> s</small></span><span className="tile-label">per question</span></div>
              <div><span className="tile-value">{(s.tokens_in + s.tokens_out).toLocaleString()}</span><span className="tile-label">tokens{run.provider === "fake" ? " (estimated)" : ""}</span></div>
            </div>
          )}
          {run.error && <p className="save-error">{run.error}</p>}
          <div className="table-scroll">
            <table className="data eval-table">
              <thead><tr><th>Question</th><th>Result</th><th>Checks</th><th>Tools used</th><th>Time</th></tr></thead>
              <tbody>
                {run.results.map((r) => (
                  <Fragment key={r.id}>
                    <tr className={r.passed ? "pass" : "fail"}>
                      <td><button type="button" className="link-btn" onClick={() => setOpen(open === r.id ? null : r.id)}
                        aria-expanded={open === r.id}>{r.id}</button> {r.question}</td>
                      <td>{r.error ? <span className="verdict fail">Error</span> : r.passed ? <span className="verdict pass">✓ Pass</span> : <span className="verdict fail">✕ Fail</span>}</td>
                      <td className="checks">
                        {Object.entries(r.checks).map(([k, ok]) => (
                          <span key={k} className={`check ${ok ? "ok" : "no"}`}>{ok ? "✓" : "✕"} {CHECK_LABEL[k] ?? k}</span>
                        ))}
                      </td>
                      <td><code>{r.tools.join(", ") || "none"}</code></td>
                      <td className="num">{r.seconds}s</td>
                    </tr>
                    {open === r.id && (
                      <tr className="eval-answer"><td colSpan={5}>{r.error ?? r.answer}</td></tr>
                    )}
                  </Fragment>
                ))}
                {running && <tr><td colSpan={5} className="muted"><span className="spinner" /> Asking question {done + 1}…</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}

      {history.length > 0 && (
        <>
          <h4>Past runs</h4>
          <div className="table-scroll">
            <table className="data">
              <thead><tr><th>When</th><th>Model</th><th>Passed</th><th>Checks</th><th>Per question</th></tr></thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.id} className={run?.id === h.id ? "current" : undefined}>
                    <td><button type="button" className="link-btn" onClick={() => poll(h.id)}>{h.started?.replace("T", " ").slice(0, 16)}</button></td>
                    <td>{h.model}</td>
                    <td>{h.summary ? `${h.summary.passed}/${h.summary.questions}` : h.status}</td>
                    <td>{h.summary ? pct(h.summary.checks_passed, h.summary.checks_total) : "–"}</td>
                    <td>{h.summary?.avg_seconds != null ? `${h.summary.avg_seconds}s` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

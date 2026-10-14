"""The evaluation report: one self-contained HTML page from saved runs, to read and discuss in the review.

Models side by side (scores per check, cost, time, every failure with what the model did and what was expected),
embedders side by side (hit rate at 5, MRR, misses), placeholders for the explain-level readability (A19) and
"what to fix first" (A18) results, and a findings section a person writes (A20). Styled with the design tokens from
frontend/src/styles/tokens.css, inlined: the page loads nothing from anywhere, so it can be opened from disk or
published as one file. Everything from a model or the data is escaped: answers are untrusted text.
"""
import datetime as dt
from html import escape
from pathlib import Path

from app.config import ROOT
from app.errors import InputError
from app.evals.checks import LABELS
from app.evals.runs import RunStore

TOKENS = ROOT.parent / "frontend" / "src" / "styles" / "tokens.css"
MODES = {"vector": "vector only", "hybrid": "hybrid (vector + BM25)"}
KIND_LABELS = {"cve": "CVE id → that CVE", "cwe": "CWE → its OWASP page", "llm_risk": "risk name → its LLM Top 10 page",
               "llm_to_atlas": "LLM risk → its ATLAS techniques"}
MISSES_SHOWN = 15

STYLE = """
body { padding: 1.5rem 1rem 3rem; }
main { max-width: 1280px; margin: 0 auto; display: grid; gap: 1.2rem; }
header.top { display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem; max-width: 1280px;
  margin: 0 auto 1.2rem; }
header.top h1 { font-size: 1.5rem; color: var(--accent); }
.meta { color: var(--muted); font-size: 0.82rem; margin: 0.2rem 0; }
.card { background: var(--surface); border-radius: var(--radius-card); box-shadow: var(--shadow-card);
  padding: 1.1rem 1.3rem; min-width: 0; }
.card h2 { margin-bottom: 0.4rem; }
.card h3 { font-size: 0.95rem; font-weight: 600; color: var(--accent); margin: 1rem 0 0.3rem; }
.nested { background: var(--nested-fill); border-radius: var(--radius-nested); padding: 0.7rem 0.9rem; margin: 0.6rem 0; }
.placeholder { border: 2px dashed var(--border); border-radius: var(--radius-nested); padding: 0.7rem 0.9rem;
  color: var(--muted); }
.table-scroll { overflow-x: auto; margin: 0.4rem 0; }
table { border-collapse: collapse; font-size: 0.88rem; min-width: 100%; }
th, td { text-align: left; padding: 0.35rem 0.6rem; border-bottom: 1px solid var(--border); vertical-align: top; }
thead th { color: var(--muted); font-size: 0.78rem; font-weight: 700; }
tbody th { font-weight: 600; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; white-space: nowrap; }
.pass { color: var(--ok); font-weight: 700; }
.fail { color: var(--error); font-weight: 700; }
.chip { display: inline-block; padding: 0 0.5rem; border-radius: var(--radius-pill); background: var(--accent-soft);
  color: var(--text); font-size: 0.75rem; font-weight: 700; }
code { font-size: 0.85em; overflow-wrap: anywhere; }
dl.failure { display: grid; grid-template-columns: max-content 1fr; gap: 0.15rem 0.8rem; margin: 0; font-size: 0.88rem; }
dl.failure dt { color: var(--muted); font-weight: 700; }
dl.failure dd { margin: 0; overflow-wrap: anywhere; }
nav.toc { display: flex; flex-wrap: wrap; gap: 0.4rem; }
nav.toc a { padding: 0.15rem 0.7rem; border-radius: var(--radius-pill); background: var(--surface); text-decoration: none;
  font-weight: 700; font-size: 0.82rem; }
#theme { flex: none; width: 36px; height: 36px; padding: 0; }
"""

THEME_SCRIPT = """
const root = document.documentElement, button = document.getElementById('theme');
function setTheme(t) {
  root.dataset.theme = t;
  button.setAttribute('aria-label', t === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
  button.textContent = t === 'dark' ? '\\u2600' : '\\u263E';
}
setTheme(matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
button.addEventListener('click', () => setTheme(root.dataset.theme === 'dark' ? 'light' : 'dark'));
"""


def store_of(settings) -> RunStore:
    return RunStore.for_settings(settings)


# --- Formatting

def _e(value) -> str:
    return escape(str(value))


def _pct(n: int, d: int) -> str:
    return f"{round(100 * n / d)}%" if d else "–"


def _cost(x: float | None) -> str:
    """Dollars to two significant figures, like the chat's usage line: $0.00061; $0 for free models."""
    if x is None:
        return "–"
    return "$0" if x == 0 else f"${x:.2g}" if x < 1 else f"${x:.2f}"


def _secs(x: float | None) -> str:
    return "–" if x is None else f"{x:.2f} s" if x < 10 else f"{x:.0f} s"


def _num(x: float | None) -> str:
    return "–" if x is None else f"{x:.2f}"


def _day(iso: str | None) -> str:
    return (iso or "")[:16].replace("T", " ")


def _table(caption: str, head: list[str], rows: list[list[str]], text_cols: int = 1) -> str:
    """Cells are HTML already (escaped by the caller). The first column names the row; columns after `text_cols`
    are numbers (right-aligned)."""
    cls = lambda i: ' class="num"' if i >= text_cols else ""  # noqa: E731
    ths = "".join(f'<th scope="col"{cls(i)}>{h}</th>' for i, h in enumerate(head))
    body = ""
    for row in rows:
        cells = "".join(f'<th scope="row">{c}</th>' if i == 0 else f"<td{cls(i)}>{c}</td>" for i, c in enumerate(row))
        body += f"<tr>{cells}</tr>"
    return (f'<div class="table-scroll"><table><caption class="visually-hidden">{_e(caption)}</caption>'
            f"<thead><tr>{ths}</tr></thead><tbody>{body}</tbody></table></div>")


def _run_head(run: dict, name: str) -> str:
    return f'{_e(name)}<br><span class="meta">{_e(_day(run.get("started")))} · {_e(run["id"])}</span>'


# --- Sections

def _models(runs: list[dict]) -> str:
    if not runs:
        return '<p class="meta">No model-check runs saved yet. Run one on the Dev page or with the command line.</p>'
    used = {name for r in runs for name in r["summary"]["by_check"]}
    checks = [n for n in LABELS if n in used] + sorted(used - set(LABELS))  # a later check without a label still shows
    rows = []
    s = [r["summary"] for r in runs]
    rows.append(["Questions passed"] + [f'{x["passed"]} / {x["questions"]}' for x in s])
    for name in checks:
        cells = []
        for x in s:
            c = x["by_check"].get(name)
            cells.append("–" if not c else
                         f'<span class="{"pass" if c["passed"] == c["total"] else "fail"}">'
                         f'{"✓" if c["passed"] == c["total"] else "✕"} {c["passed"]} / {c["total"]}</span>')
        rows.append([_e(LABELS.get(name, name))] + cells)
    rows.append(["All checks"] + [f'{x["checks_passed"]} / {x["checks_total"]} ({_pct(x["checks_passed"], x["checks_total"])})'
                                  for x in s])
    rows.append(["Errors"] + [str(x["errors"]) for x in s])
    rows.append(["Cost, whole run"] + [_cost(x["cost_total"]) for x in s])
    rows.append(["Cost per question"] + [_cost(x["avg_cost"]) for x in s])
    rows.append(["Time per question"] + [_secs(x["avg_seconds"]) for x in s])
    rows.append(["Time, whole run"] + [_secs(x["seconds_total"]) for x in s])
    rows.append(["Tokens in / out"] + [f'{x["tokens_in"]:,} / {x["tokens_out"]:,}{" (estimated)" if x["estimated"] else ""}'
                                       for x in s])
    rows.append(["Citations removed (no such source)"] + [str(x["bad_citations"]) for x in s])
    rows.append(["Sourced answers citing nothing"] + [str(x["no_citations"]) for x in s])
    head = ["Measure"] + [_run_head(r, r["model"]) for r in runs]
    out = _table("Models side by side", head, rows)

    # Per question: pass or fail, time and cost
    ids = list(dict.fromkeys(row["id"] for r in runs for row in r["results"]))
    by_q = [{row["id"]: row for row in r["results"]} for r in runs]
    qrows = []
    for qid in ids:
        question = next(row["question"] for b in by_q for row in [b.get(qid)] if row)
        cells = []
        for b in by_q:
            row = b.get(qid)
            if not row:
                cells.append("–")
            elif row["error"]:
                cells.append('<span class="fail">Error</span>')
            else:
                mark = '<span class="pass">✓ Pass</span>' if row["passed"] else '<span class="fail">✕ Fail</span>'
                cells.append(f'{mark}<br><span class="meta">{_secs(row["seconds"])} · {_cost(row["cost"])}</span>')
        qrows.append([f'{_e(qid)} <span class="meta">{_e(question)}</span>'] + cells)
    out += "<h3>Per question</h3>" + _table("Each question per model", ["Question"] + [_e(r["model"]) for r in runs], qrows)
    return out


def _failures(runs: list[dict]) -> str:
    if not runs:
        return '<p class="meta">No model-check runs saved yet.</p>'
    out = ""
    for r in runs:
        out += f'<h3>{_e(r["model"])}</h3>'
        failed = [row for row in r["results"] if row["error"] or not row["passed"]]
        if r.get("error"):
            out += f'<p class="fail">The run stopped: {_e(r["error"])}</p>'
        if not failed:
            out += '<p class="meta">No failures: every question passed every check.</p>'
            continue
        for row in failed:
            items = [("Question", f'{_e(row["id"])}: {_e(row["question"])}')]
            if row["error"]:
                items.append(("Error", _e(row["error"])))
            for f in row["failures"]:
                items.append((_e(LABELS.get(f["name"], f["name"])),
                              f'expected <strong>{_e(f["expected"])}</strong>; got <code>{_e(f["got"])}</code>'))
            items.append(("Tools used", _e(", ".join(row["tools"]) or "none")))
            dl = "".join(f"<dt>{k}</dt><dd>{v}</dd>" for k, v in items)
            out += f'<div class="nested"><dl class="failure">{dl}</dl></div>'
    return out


def _embedders(runs: list[dict]) -> str:
    if not runs:
        return ('<p class="meta">No retrieval runs saved yet. Run one on the Dev page or with the command line, once per '
                'embedder (each needs its own index).</p>')
    rows = []
    for mode, label in MODES.items():
        rows.append([f"Hit rate at 5, {label}"] + [_num(r["modes"][mode]["hit_rate_at_5"]) for r in runs])
        rows.append([f"MRR, {label}"] + [_num(r["modes"][mode]["mrr"]) for r in runs])
    kinds = list(dict.fromkeys(k for r in runs for k in r["modes"]["vector"]["by_kind"]))
    for kind in kinds:
        cells = []
        for r in runs:
            k = r["modes"]["vector"]["by_kind"].get(kind)
            cells.append("–" if not k else f'{_num(k["hit_rate_at_5"])} / {_num(k["mrr"])}')
        rows.append([f'{_e(KIND_LABELS.get(kind, kind))} <span class="meta">(vector: hit rate at 5 / MRR)</span>']
                    + cells)
    rows.append(["Questions"] + [str(r["questions"]) for r in runs])
    rows.append(["Time, whole run"] + [_secs(r.get("seconds")) for r in runs])
    head = ["Measure"] + [_run_head(r, f'{r["embedder"]} ({r["dim"]} dimensions)') for r in runs]
    out = _table("Embedders side by side", head, rows)

    for r in runs:
        out += f'<h3>Missed by {_e(r["embedder"])}</h3>'
        for mode, label in MODES.items():
            misses = r["modes"][mode]["misses"]
            if not misses:
                out += f'<p class="meta">{label}: no misses.</p>'
                continue
            mrows = [[f'{_e(m["question"])}', _e(", ".join(m["expected"])), _e(", ".join(m["got"])) or "nothing",
                      str(m["rank"] or "below 10")] for m in misses[:MISSES_SHOWN]]
            more = (f'<p class="meta">and {len(misses) - MISSES_SHOWN} more.</p>' if len(misses) > MISSES_SHOWN else "")
            out += (f'<p class="meta">{label}: {len(misses)} of {r["questions"]} not in the top 5.</p>'
                    + _table(f"Missed by {r['embedder']}, {label}", ["Question", "Right source", "Top 5 instead",
                                                                      "Rank"], mrows, text_cols=3) + more)
    return out


def _section(sid: str, title: str, body: str, intro: str = "") -> str:
    intro_html = f'<p class="meta">{intro}</p>' if intro else ""
    return f'<section id="{sid}" class="card" aria-labelledby="{sid}-h"><h2 id="{sid}-h">{title}</h2>{intro_html}{body}</section>'


def build(model_runs: list[dict], retrieval_runs: list[dict], as_of: str, findings: str | None = None,
          generated: str | None = None) -> str:
    """The page. `findings` is HTML a person wrote (A20), put in as is."""
    tokens = TOKENS.read_text()
    generated = generated or dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    placeholder = ('<p class="placeholder">Not run yet. {what} This section stays empty until that ticket adds its '
                   'questions.</p>')
    sections = [
        _section("models", "Models side by side", _models(model_runs),
                 "Each scripted question scored with exact checks, no LLM judge. Watchlist questions run on a copy "
                 "of the data."),
        _section("failures", "Failures", _failures(model_runs),
                 "Every failed check: what was expected and what the model did."),
        _section("embedders", "Embedders side by side", _embedders(retrieval_runs),
                 "Retrieval questions whose right source comes from structured fields. Hit rate at 5: share with a "
                 "right document in the top 5. MRR: mean of 1 / rank of the first right document (to rank 10)."),
        _section("explain-levels", "Explain levels: readability", placeholder.format(
            what="A19 asks one question at simple, normal and deep dive: the same key fact and citations, "
                 "readability easiest for simple and hardest for deep dive.")),
        _section("fix-first", "What to fix first", placeholder.format(
            what="A18 asks what to fix first: the top 3 must match the priority rules.")),
        _section("findings", "Findings",
                 findings or '<p class="placeholder">To be written by a person after the real runs (A20): what '
                             'worked, what failed and why, the recommended default model and embedder with the '
                             'evidence, each claim marked checked or unverified.</p>'),
    ]
    toc = "".join(f'<a href="#{sid}">{title}</a>' for sid, title in (
        ("models", "Models"), ("failures", "Failures"), ("embedders", "Embedders"),
        ("explain-levels", "Explain levels"), ("fix-first", "Fix first"), ("findings", "Findings")))
    return f"""<!doctype html>
<html lang="en" data-design="playful">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Patch: model check report</title>
<style>
{tokens}
{STYLE}
</style>
</head>
<body>
<header class="top">
<div>
<h1>Patch: model check report</h1>
<p class="meta">Generated {_e(generated)} · data as of {_e(as_of)} · {len(model_runs)} model runs, {len(retrieval_runs)} retrieval runs</p>
<nav class="toc" aria-label="Sections">{toc}</nav>
</div>
<button type="button" id="theme" aria-label="Switch to dark mode">☾</button>
</header>
<main>
{"".join(sections)}
</main>
<script>{THEME_SCRIPT}</script>
</body>
</html>
"""


def _latest(runs: list[dict], key: str) -> list[dict]:
    """The newest finished run per model or embedder (runs come newest first)."""
    picked: dict[str, dict] = {}
    for r in runs:
        if r.get("status", "done") == "done" and r[key] not in picked:
            picked[r[key]] = r
    return list(picked.values())


def _pick(store: RunStore, kind: str, ids: list[str]) -> list[dict]:
    runs = []
    for run_id in ids:
        run = store.get(kind, run_id)
        if run is None:
            raise InputError(f"No saved {'model check' if kind == 'models' else 'retrieval check'} {run_id!r}.")
        runs.append(run)
    return runs


def from_store(store: RunStore, as_of: str, model_ids: list[str] | None = None,
               retrieval_ids: list[str] | None = None, findings: str | None = None) -> str:
    """The chosen runs, or by default the latest run per model and per embedder."""
    models = _pick(store, "models", model_ids) if model_ids else _latest(store.all("models"), "model")
    retrieval = _pick(store, "retrieval", retrieval_ids) if retrieval_ids else _latest(store.all("retrieval"), "embedder")
    return build(models, retrieval, as_of, findings)


def write(html: str, out: Path) -> Path:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html)
    return out

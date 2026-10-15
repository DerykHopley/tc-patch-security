"""The evaluation report: one self-contained HTML page from saved runs, to read and discuss in the review.

The page opens with "At a glance" (quality against cost or time per model, a chart) and the written findings, then
the detail. Charts (charts.py): the at-a-glance scatter, a pass/fail grid per question and model, hit rate and MRR
bars per embedder, and each embedder's off-topic threshold between its on-topic and off-topic scores. Every chart
keeps its data in a table too.

Models side by side (scores per check, cost, time, every failure with what the model did and what was expected),
embedders side by side (hit rate at 5, MRR, misses), the explain-level readability per model (A19), a placeholder
for the "what to fix first" (A18) results, and a findings section a person writes (A20). Styled with the design tokens from
frontend/src/styles/tokens.css, inlined: the page loads nothing from anywhere, so it can be opened from disk or
published as one file. Everything from a model or the data is escaped: answers are untrusted text.
"""
import datetime as dt
from html import escape
from pathlib import Path

from app.config import ROOT
from app.errors import InputError
from app.evals import charts
from app.evals.checks import LABELS
from app.evals.runs import RunStore

TOKENS = ROOT.parent / "frontend" / "src" / "styles" / "tokens.css"
MODES = {"vector": "vector only", "hybrid": "hybrid (vector + BM25)"}
KIND_LABELS = {"cve": "CVE id → that CVE", "cwe": "CWE → its OWASP page", "llm_risk": "risk name → its LLM Top 10 page",
               "llm_to_atlas": "LLM risk → its ATLAS techniques"}
MISSES_SHOWN = 15
LEVEL_LABELS = {"simple": "Simple", "normal": "Normal", "deep_dive": "Deep dive"}

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
table.grid td.cell { text-align: center; white-space: nowrap; font-weight: 700; }
table.grid td.pass { color: var(--ok); background: color-mix(in srgb, var(--ok) 10%, var(--surface)); }
table.grid td.fail { color: var(--error); background: var(--error-soft); }
table.grid td.fail ul, table.grid td.fail p { margin: 0.3rem 0 0; padding: 0; list-style: none; text-align: left;
  color: var(--text); font-weight: 400; font-size: 0.8rem; white-space: normal; }
table.grid td.fail summary { cursor: pointer; }
table.grid td.none { color: var(--muted); }
table.grid tbody th { font-size: 0.85rem; min-width: 10rem; }
table.grid th:first-child { position: sticky; left: 0; background: var(--surface); }
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

def _short(model: str) -> str:
    """The point label: "OpenRouter · anthropic/claude-haiku-5.5" → "claude-haiku-5.5"."""
    return model.split(" · ")[-1].rsplit("/", 1)[-1]


def _is_cloud(run: dict) -> bool:
    return run.get("provider") not in ("local", "fake")


def _glance(runs: list[dict]) -> str:
    """Quality against cost per question, or against time: one point per model, cloud and local apart."""
    scored = [r for r in runs if r["summary"]["checks_total"]]
    if not scored:
        return '<p class="meta">No model-check runs with scored checks yet.</p>'
    points = []
    for r in scored:
        s = r["summary"]
        cloud = _is_cloud(r)
        points.append({"label": _short(r["model"]), "quality": 100 * s["checks_passed"] / s["checks_total"],
                       "cost": s["avg_cost"] or 0.0, "seconds": s["avg_seconds"],
                       "shape": "circle" if cloud else "square", "cls": "cloud" if cloud else "local",
                       "title": f'{r["model"]}: {_pct(s["checks_passed"], s["checks_total"])} of checks passed, '
                                f'{_cost(s["avg_cost"])} and {_secs(s["avg_seconds"])} per question'})
    best = max(points, key=lambda p: (p["quality"], -p["cost"]))
    desc = "; ".join(f'{p["label"]} ({"cloud" if p["cls"] == "cloud" else "local"}): {round(p["quality"])}%, '
                     f'{_cost(p["cost"])}, {_secs(p["seconds"])}' for p in points)
    cost = charts.scatter("glance-cost", [p | {"x": p["cost"]} for p in points], "cost",
                          "Checks passed against cost per question, one point per model", desc)
    timed = [p | {"x": p["seconds"]} for p in points if p["seconds"] is not None]
    time = charts.scatter("glance-time", timed, "time",
                          "Checks passed against seconds per question, one point per model", desc, hidden=True)
    switch = ('<div class="switch" role="group" aria-label="Across the bottom" data-switch hidden>'
              '<button type="button" aria-pressed="true" data-show="glance-cost">Cost per question</button>'
              '<button type="button" aria-pressed="false" data-show="glance-time">Seconds per question</button></div>')
    key = charts.legend([("circle", "cloud", "Cloud model (paid per token)"),
                         ("square", "local", "Local or scripted model ($0: runs on this machine)")])
    left_out = [r["model"] for r in runs if not r["summary"]["checks_total"]]
    caption = (f'Higher is better; further left is cheaper (or faster). Best score: {_e(best["label"])}, '
               f'{round(best["quality"])}% of checks. Local models cost nothing per question, so they sit in the '
               f'"free" lane; their real cost is the machine. Hover a point for its numbers.'
               + (f' Not shown (no checks scored): {_e(", ".join(left_out))}.' if left_out else ""))
    rows = [[_e(r["model"]), "cloud" if _is_cloud(r) else "local",
             _pct(r["summary"]["checks_passed"], r["summary"]["checks_total"]),
             f'{r["summary"]["checks_passed"]} / {r["summary"]["checks_total"]}',
             _cost(r["summary"]["avg_cost"]), _secs(r["summary"]["avg_seconds"])] for r in scored]
    table = _table("Quality, cost and time per model",
                   ["Model", "Where", "Checks passed", "Checks", "Cost per question", "Time per question"], rows,
                   text_cols=2)
    return charts.figure(cost + time, caption, table, before=key + switch)


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


def _grid_cell(row: dict | None) -> str:
    if not row:
        return '<td class="cell none">– <span class="meta">not asked</span></td>'
    if row["error"]:
        return (f'<td class="cell fail" title="Error: {_e(row["error"])}"><details><summary>✕ Error</summary>'
                f'<p>{_e(row["error"])}</p></details></td>')
    if row["passed"]:
        return '<td class="cell pass" title="Passed every check">✓ Pass</td>'
    names = [LABELS.get(f["name"], f["name"]) for f in row["failures"]]
    items = "".join(f"<li>{_e(n)}</li>" for n in names)
    return (f'<td class="cell fail" title="Failed: {_e(", ".join(names))}"><details>'
            f'<summary>✕ {len(names)} failed</summary><ul>{items}</ul></details></td>')


def _grid(runs: list[dict]) -> str:
    """Questions down, models across: which question tripped which model, and on which checks."""
    if not runs:
        return '<p class="meta">No model-check runs saved yet.</p>'
    ids = list(dict.fromkeys(row["id"] for r in runs for row in r["results"]))
    by_q = [{row["id"]: row for row in r["results"]} for r in runs]
    head = "".join(f'<th scope="col" title="{_e(r["model"])}">{_e(_short(r["model"]))}<br>'
                   f'<span class="meta">{"cloud" if _is_cloud(r) else "local"}</span></th>' for r in runs)
    body = ""
    for qid in ids:
        question = next(b[qid]["question"] for b in by_q if qid in b)
        cells = "".join(_grid_cell(b.get(qid)) for b in by_q)
        body += f'<tr><th scope="row">{_e(qid)} <span class="meta">{_e(question)}</span></th>{cells}</tr>'
    totals = "".join(f'<td class="cell">{r["summary"]["passed"]} / {r["summary"]["questions"]}</td>' for r in runs)
    return (f'<div class="table-scroll"><table class="grid"><caption class="visually-hidden">Pass or fail per '
            f'question and model</caption><thead><tr><th scope="col">Question</th>{head}</tr></thead>'
            f'<tbody>{body}<tr><th scope="row">Questions passed</th>{totals}</tr></tbody></table></div>')


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


SERIES = {"vector": ("s1", "Vector only"), "hybrid": ("s2", "Hybrid (vector + BM25)")}


def _embedder_bars(runs: list[dict]) -> str:
    """Hit rate at 5 and MRR per embedder, vector only against hybrid: two small charts side by side."""
    panels = ""
    for metric, key, name in (("hit", "hit_rate_at_5", "Hit rate at 5"), ("mrr", "mrr", "MRR")):
        groups = [{"label": _short(r["embedder"]), "title": r["embedder"],
                   "bars": [(cls, label, r["modes"][mode][key]) for mode, (cls, label) in SERIES.items()]}
                  for r in runs]
        desc = "; ".join(f'{g["label"]}: vector {_num(g["bars"][0][2])}, hybrid {_num(g["bars"][1][2])}'
                         for g in groups)
        panels += (f'<div><h4>{name}</h4>' + charts.bars(f"bars-{metric}", groups, f"{name} per embedder, vector "
                                                          f"only against hybrid (0 to 1, higher is better)", desc)
                   + "</div>")
    key = charts.legend([("square", cls, label) for cls, label in SERIES.values()])
    rows = [[_e(r["embedder"]), label, _num(r["modes"][mode]["hit_rate_at_5"]), _num(r["modes"][mode]["mrr"])]
            for r in runs for mode, (_, label) in SERIES.items()]
    table = _table("Hit rate at 5 and MRR per embedder and mode", ["Embedder", "Mode", "Hit rate at 5", "MRR"], rows,
                   text_cols=2)
    caption = ("Longer is better, on a 0 to 1 scale. Hybrid adds BM25 keyword search to the vectors, as the chat "
               "searches; vector only shows the embedder on its own.")
    return charts.figure(f'<div class="chart-pair">{panels}</div>', caption, table, before=key, wide=False)


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
    out = _embedder_bars(runs) + "<h3>All the numbers</h3>" + _table("Embedders side by side", head, rows)

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


def _threshold(runs: list[dict]) -> str:
    """Per embedder: where its threshold sits between on-topic and off-topic top-1 scores. Runs saved before the
    scores were recorded say so instead of vanishing."""
    if not runs:
        return '<p class="meta">No retrieval runs saved yet.</p>'
    rows, notes, summary = [], [], []
    with_data = [r for r in runs if r.get("threshold")]
    for r in runs:
        t = r.get("threshold")
        name = _short(r["embedder"])
        if not t:
            rows.append({"label": name, "title": r["embedder"],
                         "missing": "No threshold data: this run is older than the off-topic scores. Run the "
                                    "retrieval check again."})
            notes.append(f"{name}: no data")
            continue
        questions = {x["id"]: x["question"] for x in r.get("results", [])}
        on = [(x["score"], questions.get(x["id"], x["id"])) for x in t["on_topic"] if x["score"] is not None]
        off = [(x["score"], x["question"]) for x in t["off_topic"] if x["score"] is not None]
        rows.append({"label": name, "title": r["embedder"], "threshold": t["min_score"], "on": on, "off": off})
        low_on, high_off = min((s for s, _ in on), default=None), max((s for s, _ in off), default=None)
        below = sum(s < t["min_score"] for s, _ in on)
        above = sum(s >= t["min_score"] for s, _ in off)
        notes.append(f"{name}: threshold {t['min_score']:.2f}; off-topic at most {_num(high_off)}, on-topic at "
                     f"least {_num(low_on)}; {below} on-topic below it, {above} off-topic at or above it")
        summary.append([_e(r["embedder"]), _num(t["min_score"]), _num(low_on), str(below), _num(high_off), str(above),
                        str(sum(x["keyword_hits"] > 0 for x in t["off_topic"]))])
    desc = ". ".join(notes) + "."
    svg = charts.strips("threshold-strips", rows, "Top-1 vector scores of on-topic and off-topic questions per "
                                                  "embedder, with its off-topic threshold", desc)
    key = charts.legend([("circle", "on-topic", "On-topic question (the retrieval questions)"),
                         ("square", "off-topic", "Off-topic question (pasta, football, weather…)")])
    table = _table("Threshold per embedder", ["Embedder", "Threshold", "On-topic lowest", "On-topic below",
                                              "Off-topic highest", "Off-topic at or above", "Off-topic with BM25 hits"],
                   summary, text_cols=1) if summary else ""
    if with_data:
        off_rows = []
        questions = list(dict.fromkeys(o["question"] for r in with_data for o in r["threshold"]["off_topic"]))
        for q in questions:
            cells = []
            for r in with_data:
                x = next((o for o in r["threshold"]["off_topic"] if o["question"] == q), None)
                cells.append("–" if x is None else f'{_num(x["score"])} · {x["keyword_hits"]} BM25')
            off_rows.append([_e(q)] + cells)
        table += "<h4>Each off-topic question: top-1 score · chunks BM25 matches</h4>" + _table(
            "Off-topic questions per embedder", ["Question"] + [_e(_short(r["embedder"])) for r in with_data],
            off_rows)
    caption = ("A good threshold sits in the gap: every on-topic dot to its right, every off-topic dot to its left. "
               "A search hit below the threshold counts as no match, so Patch says it found nothing. " + _e(desc))
    return charts.figure(svg, caption, table, before=key)


def _explain_levels(runs: list[dict], placeholder: str) -> str:
    """Per model: the explain-level question's answers at each level (A19), with reading ease, length, citations
    and the comparison checks. A placeholder while no run has asked it."""
    out = ""
    for r in runs:
        for row in (x for x in r["results"] if x.get("levels")):
            out += f'<h3>{_e(r["model"])} <span class="meta">{_e(row["id"])}: {_e(row["question"])}</span></h3>'
            rows = [[_e(LEVEL_LABELS.get(lv, lv)), "–" if x["reading_ease"] is None else f'{x["reading_ease"]:.0f}',
                     str(x["words"]), _e(" ".join(f"[{n}]" for n in x["cited"]) or "none")]
                    for lv, x in row["levels"].items()]
            out += _table(f"Explain levels, {r['model']}", ["Level", "Reading ease", "Words", "Cited"], rows)
            marks = []
            for name in ("readability", "same_citations", "key_fact"):
                if name in row["checks"]:
                    ok = row["checks"][name]
                    marks.append(f'<span class="{"pass" if ok else "fail"}">{"✓" if ok else "✕"} '
                                 f'{_e(LABELS.get(name, name))}</span>')
            out += f'<p>{" · ".join(marks)}</p>'
            answers = "".join(f'<dt>{_e(LEVEL_LABELS.get(lv, lv))}</dt><dd>{_e(x["answer"])}</dd>'
                              for lv, x in row["levels"].items())
            out += f'<details><summary>The three answers</summary><dl class="failure">{answers}</dl></details>'
    return out or placeholder


def _view(page: dict | None) -> str:
    """Where a fix-first question was asked from: the whole watchlist, or a page and its filters (its page context)."""
    if not page:
        return "Whole watchlist"
    filters = ", ".join(f"{k}={v}" for k, v in page.items() if k != "page")
    return f"{page.get('page', 'any')} page" + (f": {filters}" if filters else "")


def _fix_first(runs: list[dict], placeholder: str) -> str:
    """Per model and view: the rules' top 3 against the answer's top 3, in order (A18), with the answer. A
    placeholder while no run has asked the question. A model that errored on the question gets a failed row, so it
    doesn't vanish."""
    from app.evals.model_check import questions

    pages = {q["id"]: q.get("page") for q in questions() if q["expect"].get("fix_first")}
    view = lambda row: _e(_view(row.get("page") or pages.get(row["id"])))  # noqa: E731 - checked context first
    rows, answers = [], ""
    for r in runs:
        for row in (x for x in r["results"] if x.get("fix_first")):
            f, ok = row["fix_first"], row["checks"].get("fix_first", False)
            mark = f'<span class="{"pass" if ok else "fail"}">{"✓ Same order" if ok else "✕ Different"}</span>'
            rows.append([_e(r["model"]), view(row), _e(", ".join(f["rules"]) or "none open"),
                         _e(", ".join(f["answer"]) or "no CVE named"), mark, str(f["total_open"])])
            answers += f'<dt>{_e(r["model"])} · {view(row)}</dt><dd>{_e(row["answer"])}</dd>'
        for row in (x for x in r["results"] if "fix_first" in x["checks"] and not x.get("fix_first")):
            rows.append([_e(r["model"]), view(row), "–", "prioritise wasn't called",
                         '<span class="fail">✕ Different</span>', "–"])
        for row in (x for x in r["results"] if x.get("error") and x["id"] in pages):  # crashed: a failure
            rows.append([_e(r["model"]), view(row), "–", f'Error: {_e(row["error"])}',
                         '<span class="fail">✕ Error</span>', "–"])
    if not rows:
        return placeholder
    out = _table("What to fix first, per model and view",
                 ["Model", "View", "Rules' top 3", "Answer's top 3", "Result", "Open"], rows, text_cols=5)
    if answers:
        out += f'<details><summary>The answers</summary><dl class="failure">{answers}</dl></details>'
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
    findings_html = findings or ('<p class="placeholder">To be written by a person after the real runs (A20): what '
                                 'worked, what failed and why, the recommended default model and embedder with the '
                                 'evidence, each claim marked checked or unverified.</p>')
    # (id, nav label, heading, body, intro), in page order: the overview, the written findings, then the detail
    parts = [
        ("glance", "At a glance", "At a glance", _glance(model_runs),
         "Each model's share of checks passed against what an answer costs and how long it takes. The latest run "
         "per model."),
        ("findings", "Findings", "Findings", findings_html, ""),
        ("models", "Models", "Models side by side", _models(model_runs),
         "Each scripted question scored with exact checks, no LLM judge. Watchlist questions run on a copy of the "
         "data."),
        ("grid", "Pass or fail", "Pass or fail, per question", _grid(model_runs),
         "Questions down, models across. A failed cell names its failed checks: hover it, or open it. The details "
         "of each failure are in the next section."),
        ("failures", "Failures", "Failures", _failures(model_runs),
         "Every failed check: what was expected and what the model did."),
        ("embedders", "Embedders", "Embedders side by side", _embedders(retrieval_runs),
         "Retrieval questions whose right source comes from structured fields. Hit rate at 5: share with a right "
         "document in the top 5. MRR: mean of 1 / rank of the first right document (to rank 10)."),
        ("threshold", "Threshold", "Off-topic threshold", _threshold(retrieval_runs),
         "Each embedder's best (top-1) vector score for the retrieval questions above and for 15 off-topic "
         "questions, with the threshold in use. Off-topic questions also show how many chunks BM25 keyword search "
         "matches: it has no threshold, so hybrid search can still bring those back."),
        ("explain-levels", "Explain levels", "Explain levels: readability", _explain_levels(model_runs, placeholder.format(
            what="A19 asks one question at simple, normal and deep dive: the same key fact and citations, "
                 "readability easiest for simple and hardest for deep dive.")),
         "One question asked at each explain level. Reading ease is Flesch's score (higher is easier; 60–70 is "
         "plain English), computed by our own code. It must fall from simple to deep dive, with the same key fact "
         "and the same cited sources at every level."),
        ("fix-first", "Fix first", "What to fix first", _fix_first(model_runs, placeholder.format(
            what="A18 asks what to fix first: the top 3 must match the priority rules.")),
         "\"What should I fix first?\" The order comes from the priority rules (prioritise); the model only "
         "explains it. Its answer must name the rules' top 3 first, in the same order."),
    ]
    sections = [_section(sid, title, body, intro) for sid, _, title, body, intro in parts]
    toc = "".join(f'<a href="#{sid}">{nav}</a>' for sid, nav, *_ in parts)
    return f"""<!doctype html>
<html lang="en" data-design="playful">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Patch: model check report</title>
<style>
{tokens}
{STYLE}
{charts.CHART_STYLE}
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
<script>{THEME_SCRIPT}{charts.SWITCH_SCRIPT}</script>
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

#!/usr/bin/env python3
"""Build factory/report.html: tokens, API-equivalent cost and estimated energy per stage.

    python3 factory/report.py

Reads factory/stages.json (written by log_stage.py) and the matching Claude Code
transcripts, including subagent transcripts. Standard library only.

- Cost is API-equivalent: tokens x list price. A subscription isn't billed per token.
- Energy reuses ~/.claude/statusline-energy.py so the numbers match the status line.
  It's an order-of-magnitude estimate, not a measurement.
"""
import datetime as dt
import glob
import html
import importlib.util
import json
import os
import pathlib

from log_stage import STAGES_FILE, transcripts_dir

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "report.html"

# USD per million tokens: (input, output, cache read). Source: claude-api skill
# model table, cached 2026-10-06. Cache writes are 1.25x input (5 min TTL) or
# 2x input (1 h TTL). Longest matching key wins.
PRICES = {
    "fable-5-1": (10.0, 50.0, 0.25),
    "fable-5": (10.0, 50.0, 1.00),
    "opus-5-5": (4.0, 20.0, 0.20),
    "opus-5": (5.0, 25.0, 0.50),
    "opus-4": (5.0, 25.0, 0.50),
    "sonnet-5-5": (2.0, 10.0, 0.20),
    "sonnet-5": (2.0, 10.0, 0.20),
    "sonnet-4-6": (3.0, 15.0, 0.30),
    "haiku-5-5": (0.10, 0.50, 0.01),
    "haiku-4-5": (1.0, 5.0, 0.10),
}
FAST_MULTIPLIER = 2.0  # fast mode on Opus 5.5 is $8/$40, twice standard
IDLE_GAP_S = 300  # gaps longer than this don't count as active time


def load_energy_module():
    path = pathlib.Path.home() / ".claude" / "statusline-energy.py"
    spec = importlib.util.spec_from_file_location("statusline_energy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


energy = load_energy_module()


def price_for(model: str):
    model = (model or "").lower()
    for key in sorted(PRICES, key=len, reverse=True):
        if key in model:
            return PRICES[key]
    return None


def usage_cost(model: str, u: dict):
    p = price_for(model)
    if p is None:
        return None
    inp, out, read = p
    cc = u.get("cache_creation") or {}
    w1h = cc.get("ephemeral_1h_input_tokens", 0)
    w5m = cc.get("ephemeral_5m_input_tokens", u.get("cache_creation_input_tokens", 0) - w1h)
    usd = (
        u.get("input_tokens", 0) * inp
        + u.get("output_tokens", 0) * out
        + u.get("cache_read_input_tokens", 0) * read
        + w5m * inp * 1.25
        + w1h * inp * 2.0
    ) / 1_000_000
    return usd * (FAST_MULTIPLIER if u.get("speed") == "fast" else 1.0)


def usage_wh(model: str, u: dict) -> float:
    k = energy.KWH_PER_M
    kwh = (
        u.get("output_tokens", 0) * k["output"]
        + u.get("input_tokens", 0) * k["input"]
        + u.get("cache_creation_input_tokens", 0) * k["cache_write"]
        + u.get("cache_read_input_tokens", 0) * k["cache_read"]
    ) / 1_000_000
    return kwh * energy.model_scale(model) * 1000


def is_human_prompt(entry: dict) -> bool:
    """A message you typed, not a tool result, hook output or slash-command echo."""
    if entry.get("type") != "user" or entry.get("isMeta") or entry.get("isSidechain"):
        return False
    content = (entry.get("message") or {}).get("content")
    if isinstance(content, str):
        # Slash commands and their output are logged as <command-...> / <local-command-...>.
        return not content.lstrip().startswith(("<command-", "<local-command-"))
    if isinstance(content, list):
        return any(b.get("type") == "text" for b in content) and not any(
            b.get("type") == "tool_result" for b in content
        )
    return False


def timestamps_and_prompts(path: str):
    stamps, prompts = [], 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if ts := e.get("timestamp"):
                stamps.append(dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone())
            prompts += is_human_prompt(e)
    return sorted(stamps), prompts


def summarise(session: str, tdir: pathlib.Path) -> dict:
    main = tdir / f"{session}.jsonl"
    files = [str(main)] + glob.glob(os.path.join(tdir, session, "**", "*.jsonl"), recursive=True)
    s = {
        "input": 0, "output": 0, "cache_read": 0, "cache_write": 0,
        "usd": 0.0, "unpriced": set(), "wh": 0.0, "models": set(), "subagent_files": len(files) - 1,
    }
    for path in files:
        for model, u in energy.read_usage(path).values():
            s["models"].add(model)
            s["input"] += u.get("input_tokens", 0)
            s["output"] += u.get("output_tokens", 0)
            s["cache_read"] += u.get("cache_read_input_tokens", 0)
            s["cache_write"] += u.get("cache_creation_input_tokens", 0)
            c = usage_cost(model, u)
            if c is None:
                s["unpriced"].add(model)
            else:
                s["usd"] += c
            s["wh"] += usage_wh(model, u)
    stamps, s["prompts"] = timestamps_and_prompts(str(main)) if main.exists() else ([], 0)
    s["start"] = stamps[0] if stamps else None
    s["wall_min"] = (stamps[-1] - stamps[0]).total_seconds() / 60 if stamps else 0
    s["active_min"] = sum(
        min((b - a).total_seconds(), IDLE_GAP_S) for a, b in zip(stamps, stamps[1:])
    ) / 60
    return s


def fmt_tokens(n: int) -> str:
    return f"{n / 1e6:.2f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(n)


def render(rows: list) -> str:
    keys = ("input", "output", "cache_read", "cache_write", "usd", "wh", "wall_min", "active_min", "prompts")
    total = {k: sum(r[1][k] for r in rows) for k in keys}
    step_ins = [r[0].get("step_ins") for r in rows if r[0].get("step_ins") is not None]

    def tr(stage, s, tests="", step="", notes="", bold=False):
        cells = [
            stage, s["start"].strftime("%Y-%m-%d %H:%M") if s.get("start") else "",
            f"{s['wall_min']:.0f} / {s['active_min']:.0f}",
            fmt_tokens(s["input"]), fmt_tokens(s["output"]),
            fmt_tokens(s["cache_read"]), fmt_tokens(s["cache_write"]),
            f"${s['usd']:.2f}" + (" *" if s.get("unpriced") else ""),
            f"{s['wh']:.1f}", str(s["prompts"]), step, tests, notes,
        ]
        tag = "th" if bold else "td"
        return "<tr>" + "".join(f"<{tag}>{html.escape(str(c))}</{tag}>" for c in cells) + "</tr>"

    body = "\n".join(
        tr(f"{m.get('workflow', 'staged')}: {m['stage']}", s, m.get("tests", ""), "" if m.get("step_ins") is None else str(m["step_ins"]), m.get("notes", ""))
        for m, s in rows
    )
    by_wf = {}
    for m, s in rows:
        by_wf.setdefault(m.get("workflow", "staged"), []).append((m, s))
    wf_rows = "\n".join(
        tr(f"{wf} ({len(rs)} stages)", {k: sum(r[1][k] for r in rs) for k in keys},
           step=str(sum(r[0]["step_ins"] for r in rs if r[0].get("step_ins") is not None)))
        for wf, rs in by_wf.items()
    )
    foot = tr("Total", total, step=str(sum(step_ins)) if step_ins else "", bold=True)
    models = sorted(set().union(*(s["models"] for _, s in rows))) if rows else []
    unpriced = sorted(set().union(*(s["unpriced"] for _, s in rows))) if rows else []
    phones = total["wh"] / energy.PHONE_CHARGE_WH

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Factory Run Report</title>
<style>
:root {{ --bg:#fff; --fg:#1d1d1f; --muted:#666; --line:#ddd; --head:#f4f4f6; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#16161a; --fg:#e8e8ea; --muted:#9a9aa2; --line:#33333a; --head:#222228; }} }}
body {{ background:var(--bg); color:var(--fg); font:15px/1.5 system-ui, sans-serif; margin:0 auto; max-width:1100px; padding:24px 16px; }}
h1 {{ font-size:1.4rem; margin:0 0 4px; }}
p, li {{ color:var(--muted); }}
.wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-variant-numeric:tabular-nums; }}
th, td {{ border-bottom:1px solid var(--line); padding:6px 8px; text-align:right; white-space:nowrap; }}
th:first-child, td:first-child, th:last-child, td:last-child {{ text-align:left; }}
td:last-child {{ white-space:normal; min-width:200px; }}
thead th {{ background:var(--head); }}
</style></head><body>
<h1>Factory run report</h1>
<p>Generated {dt.datetime.now():%Y-%m-%d %H:%M}. {len(rows)} stages. Models: {html.escape(", ".join(models)) or "none"}.</p>
<p><strong>Totals:</strong> ${total['usd']:.2f} API-equivalent, ~{total['wh']:.1f} Wh estimated (≈{phones:.1f} phone charges), {total['active_min']:.0f} active minutes.</p>
<div class="wrap"><table>
<thead><tr><th>Stage</th><th>Started</th><th>Min (wall / active)</th><th>Input</th><th>Output</th>
<th>Cache read</th><th>Cache write</th><th>Cost</th><th>Wh</th><th>Prompts</th><th>Step-ins</th><th>Tests</th><th>Notes</th></tr></thead>
<tbody>
{body}
</tbody><tfoot>{foot}</tfoot></table></div>
<h2>By workflow</h2>
<p>Compare like with like: leave out the "planning" stage when comparing the build cost of two workflows.</p>
<div class="wrap"><table>
<thead><tr><th>Workflow</th><th>Started</th><th>Min (wall / active)</th><th>Input</th><th>Output</th>
<th>Cache read</th><th>Cache write</th><th>Cost</th><th>Wh</th><th>Prompts</th><th>Step-ins</th><th>Tests</th><th>Notes</th></tr></thead>
<tbody>
{wf_rows}
</tbody></table></div>
<h2>How to read this</h2>
<ul>
<li><strong>Cost</strong> is tokens × Anthropic list price (cached 2026-10-06), with cache writes at 1.25× (5 min) or 2× (1 h) input. A subscription isn't billed per token, so treat this as "what it would cost on the API".{" * marks stages with unpriced models: " + html.escape(", ".join(unpriced)) + "." if unpriced else ""}</li>
<li><strong>Wh</strong> uses the same per-token assumptions as the status line (~/.claude/statusline-energy.py). Unverified: Anthropic publishes no energy figures. Order of magnitude only.</li>
<li><strong>Cache read</strong> usually dominates the token count but is cheap in both money and energy. Look at output tokens for the real work.</li>
<li><strong>Active minutes</strong> cap each gap between events at {IDLE_GAP_S // 60} minutes, so lunch breaks don't count.</li>
<li><strong>Prompts</strong> counts messages you typed (approximate). <strong>Step-ins</strong> is your own count of corrections or unblocking, logged at the end of each stage.</li>
<li>A long single-session workflow (like superpowers) shows as one row; its subagents are counted inside it.</li>
<li>Includes subagent transcripts when Claude Code stores them beside the session.</li>
</ul>
</body></html>
"""


def main() -> None:
    stages = json.loads(STAGES_FILE.read_text()) if STAGES_FILE.exists() else []
    rows = [
        (m, summarise(m["session"], pathlib.Path(m.get("transcripts") or transcripts_dir(HERE.parent))))
        for m in stages
    ]
    rows.sort(key=lambda r: r[1]["start"] or dt.datetime.max.replace(tzinfo=dt.timezone.utc))
    OUT.write_text(render(rows), encoding="utf-8")
    total = sum(s["usd"] for _, s in rows)
    print(f"Wrote {OUT} ({len(rows)} stages, ${total:.2f} API-equivalent)")


if __name__ == "__main__":
    main()

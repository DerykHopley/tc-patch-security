"""Model check (M2, M3): run the 11 example questions against the current model and score each answer
with exact checks, no LLM judge. Runs in a background thread against a copy of the state, because
Q9 and Q10 change the watchlist.

Checks, where the question's `expect` (fixtures/fake_script.json) asks for them:
- tools: the expected tools were called (an empty list means no tool may be called)
- filters: the self-query filters include these values
- contains: the answer contains one of these phrases
- cites: the answer cites at least one source; and always: every [n] cited is a real source
- flag: the guard flagged the message; no_code: no code block in the answer (the exploit question)
"""
import dataclasses
import datetime as dt
import json
import re
import tempfile
import threading
import time
import uuid
from pathlib import Path

from app.agent import answer
from app.config import FIXTURES
from app.errors import LLMError
from app.guard import check_message
from app.state import State

_runs: dict[str, dict] = {}
_lock = threading.Lock()


def questions() -> list[dict]:
    return json.loads((FIXTURES / "fake_script.json").read_text())["scripts"]


def score(q: dict, reply) -> dict[str, bool]:
    exp, text = q["expect"], reply.answer or ""
    used = [t.name for t in reply.tool_calls]
    checks: dict[str, bool] = {}
    if exp.get("tools") is not None:
        checks["tools"] = set(exp["tools"]) <= set(used) if exp["tools"] else not used
    if "filters" in exp:
        got = (reply.query.filters if reply.query else {}) or {}
        checks["filters"] = all(str(got.get(k, "")).lower() == str(v).lower() for k, v in exp["filters"].items())
    if "contains_any" in exp:
        checks["contains"] = any(p.lower() in text.lower() for p in exp["contains_any"])
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", text)}
    numbers = {s.n for s in reply.sources}
    checks["citations_valid"] = cited <= numbers
    if exp.get("cites"):
        checks["cites"] = bool(cited & numbers)
    if exp.get("flag"):
        checks["flag"] = "injection_phrasing" in reply.flags
    if exp.get("no_code"):
        checks["no_code"] = "```" not in text
    return checks


def _run(run_id: str, deps, ids: list[str] | None) -> None:
    run = _runs[run_id]
    tmp = tempfile.TemporaryDirectory()
    try:
        # A copy of the state: Q9 and Q10 write to the watchlist, and the real one must not change.
        state = State(Path(tmp.name) / "state.json", deps.knowledge, deps.state.defaults)
        snap = deps.state.snapshot()
        state._save(snap)
        eval_deps = dataclasses.replace(deps, state=state)
        for q in questions():
            if ids and q["id"] not in ids:
                continue
            row = {"id": q["id"], "question": q["question"], "checks": {}, "passed": False, "tools": [],
                   "answer": "", "seconds": 0.0, "tokens_in": 0, "tokens_out": 0, "steps": 0, "error": None}
            start = time.perf_counter()
            try:
                message, flags = check_message(q["question"], [])
                reply = answer(message, [], eval_deps, flags=flags)
                row |= {"checks": score(q, reply), "tools": [t.name for t in reply.tool_calls], "answer": reply.answer,
                        "tokens_in": reply.usage.input_tokens, "tokens_out": reply.usage.output_tokens, "steps": reply.steps,
                        "sources": len(reply.sources)}
                row["passed"] = all(row["checks"].values())
            except LLMError as e:
                row["error"] = e.public or e.message
            except Exception as e:  # noqa: BLE001 - one bad question shouldn't stop the run
                row["error"] = f"{type(e).__name__}: {e}"
            row["seconds"] = round(time.perf_counter() - start, 2)
            with _lock:
                run["results"].append(row)
            if row["error"] and "Can't reach" in row["error"]:
                break  # the server is down: the other questions would fail the same way
        run["status"] = "done"
    except Exception as e:  # noqa: BLE001
        run["status"], run["error"] = "failed", f"{type(e).__name__}: {e}"
    finally:
        tmp.cleanup()
        run["finished"] = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
        run["summary"] = summarise(run)
        path = deps.settings.state_path.parent / "evals" / f"{run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run, indent=1))


def summarise(run: dict) -> dict:
    rows = run["results"]
    checks = [ok for r in rows for ok in r["checks"].values()]
    timed = [r["seconds"] for r in rows if not r["error"]]
    return {
        "questions": len(rows), "passed": sum(r["passed"] for r in rows),
        "checks_passed": sum(checks), "checks_total": len(checks),
        "errors": sum(bool(r["error"]) for r in rows),
        "avg_seconds": round(sum(timed) / len(timed), 2) if timed else None,
        "tokens_in": sum(r["tokens_in"] for r in rows), "tokens_out": sum(r["tokens_out"] for r in rows),
    }


def start(deps, ids: list[str] | None = None, wait: bool = False) -> dict:
    with _lock:
        if any(r["status"] == "running" for r in _runs.values()):
            raise RuntimeError("A model check is already running.")
        run_id = dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        _runs[run_id] = {"id": run_id, "status": "running", "model": deps.llm.label() if hasattr(deps.llm, "label") else deps.llm.name,
                         "provider": deps.llm.name, "started": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                         "total": len([q for q in questions() if not ids or q["id"] in ids]), "results": [], "error": None}
    t = threading.Thread(target=_run, args=(run_id, deps, ids), daemon=True)
    t.start()
    if wait:  # tests
        t.join()
    return get(run_id, deps)


def get(run_id: str, deps) -> dict | None:
    if run_id in _runs:
        with _lock:
            return json.loads(json.dumps(_runs[run_id]))
    path = deps.settings.state_path.parent / "evals" / f"{run_id}.json"
    return json.loads(path.read_text()) if path.exists() else None


def history(deps) -> list[dict]:
    """Past runs, newest first: id, model, when, summary."""
    folder = deps.settings.state_path.parent / "evals"
    rows = []
    for p in sorted(folder.glob("*.json"), reverse=True)[:30] if folder.exists() else []:
        r = json.loads(p.read_text())
        rows.append({k: r.get(k) for k in ("id", "model", "provider", "started", "status", "summary")})
    return rows

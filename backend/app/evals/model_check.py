"""Run the scripted questions against the saved model and score each answer with the exact checks (checks.py).

A run happens in a background thread, on a copy of the state: Q9 and Q10 change the watchlist, and the real one must
not change. The model is fixed when the run starts, so switching models on the Dev page mid-run doesn't mix two
models in one run. Each run is saved (runs.py) with model, provider, per-check scores, per-question cost and time,
and totals.

The questions are the scripts in fixtures/fake_script.json that have an `expect`. A new question is a new script
there (FakeLLM must pass it); a new kind of check is a new function in checks.CHECKS.
"""
import dataclasses
import json
import tempfile
import threading
import time
from pathlib import Path

from app.agent import answer
from app.config import FIXTURES
from app.errors import InputError, LLMError
from app.evals.checks import score
from app.evals.runs import LISTED, RunStore, new_id, now
from app.guard import check_message
from app.state import State

KIND = "models"
# These errors fail every question the same way: stop instead of waiting through the rest.
FATAL = ("Can't reach", "doesn't have the model", "rejected the API key", "spending cap")

_live: dict[str, dict] = {}  # runs in progress, by id; finished runs are read from their file
_lock = threading.Lock()


def questions() -> list[dict]:
    return [s for s in json.loads((FIXTURES / "fake_script.json").read_text())["scripts"] if "expect" in s]


def _pick(ids: list[str] | None) -> list[dict]:
    qs = questions()
    if not ids:
        return qs
    known = {q["id"] for q in qs}
    if unknown := [i for i in ids if i not in known]:
        raise InputError(f"No model-check question {', '.join(unknown)}. Questions: {', '.join(sorted(known))}.")
    return [q for q in qs if q["id"] in ids]


def _pinned(llm):
    """The model behind the router right now (A11's LLMRouter picks per call)."""
    return llm.current() if hasattr(llm, "current") else llm


def _ask(q: dict, deps) -> dict:
    row = {"id": q["id"], "question": q["question"], "passed": False, "checks": {}, "failures": [], "tools": [],
           "answer": "", "seconds": 0.0, "cost": 0.0, "tokens_in": 0, "tokens_out": 0, "llm_calls": 0, "steps": 0,
           "sources": 0, "bad_citations": [], "no_citations": False, "estimated": False, "error": None}
    start = time.perf_counter()
    try:
        message, flags = check_message(q["question"], [])
        reply = answer(message, [], deps, max_steps=deps.dev().max_steps, flags=flags)
        checks = score(q["expect"], reply)
        row |= {"checks": {c.name: c.passed for c in checks},
                "failures": [c.to_dict() for c in checks if not c.passed],
                "passed": all(c.passed for c in checks), "tools": [t.name for t in reply.tool_calls],
                "answer": reply.answer, "cost": reply.usage.cost, "tokens_in": reply.usage.input_tokens,
                "tokens_out": reply.usage.output_tokens, "llm_calls": reply.usage.llm_calls, "steps": reply.steps,
                "sources": len(reply.sources), "bad_citations": reply.bad_citations,
                "no_citations": reply.no_citations, "estimated": reply.usage.estimated}
    except LLMError as e:
        row["error"] = e.public or e.message
    except Exception as e:  # noqa: BLE001 - one bad question shouldn't stop the run
        row["error"] = f"{type(e).__name__}: {e}"
    row["seconds"] = round(time.perf_counter() - start, 3)
    return row


def summarise(rows: list[dict]) -> dict:
    """Totals over a run's rows. Pure, so the report can recompute it."""
    by_check: dict[str, dict] = {}
    for r in rows:
        for name, ok in r["checks"].items():
            c = by_check.setdefault(name, {"passed": 0, "total": 0})
            c["passed"] += ok
            c["total"] += 1
    answered = [r for r in rows if not r["error"]]
    seconds = sum(r["seconds"] for r in answered)
    cost = sum(r["cost"] for r in rows)
    return {
        "questions": len(rows), "passed": sum(r["passed"] for r in rows), "errors": len(rows) - len(answered),
        "checks_passed": sum(c["passed"] for c in by_check.values()),
        "checks_total": sum(c["total"] for c in by_check.values()), "by_check": by_check,
        "seconds_total": round(seconds, 3), "avg_seconds": round(seconds / len(answered), 3) if answered else None,
        "cost_total": round(cost, 8), "avg_cost": round(cost / len(rows), 8) if rows else None,
        "tokens_in": sum(r["tokens_in"] for r in rows), "tokens_out": sum(r["tokens_out"] for r in rows),
        "estimated": any(r["estimated"] for r in rows),
        "bad_citations": sum(len(r["bad_citations"]) for r in rows),
        "no_citations": sum(r["no_citations"] for r in rows),
    }


def _run(run: dict, qs: list[dict], deps, store: RunStore) -> None:
    tmp = tempfile.TemporaryDirectory()
    try:
        state = State(Path(tmp.name) / "state.json", deps.knowledge, deps.state.defaults, deps.state.dev_defaults)
        state._save(deps.state.snapshot())  # a copy: the watchlist questions write here
        run_deps = dataclasses.replace(deps, state=state, llm=_pinned(deps.llm))
        for q in qs:
            row = _ask(q, run_deps)
            with _lock:
                run["results"].append(row)
            if row["error"] and any(p in row["error"] for p in FATAL):
                run["error"] = row["error"]
                break
        run["status"] = "done"
    except Exception as e:  # noqa: BLE001
        run["status"], run["error"] = "failed", f"{type(e).__name__}: {e}"
    finally:
        tmp.cleanup()
        with _lock:
            run["finished"] = now()
            run["summary"] = summarise(run["results"])
            store.save(KIND, run)
            _live.pop(run["id"], None)


def start(deps, ids: list[str] | None = None, wait: bool = False) -> dict:
    """Start a run in the background and return it (status "running"). One run at a time."""
    qs = _pick(ids)
    store = RunStore.for_settings(deps.settings)
    llm = _pinned(deps.llm)
    dev = deps.dev()
    with _lock:
        if _live:
            raise InputError("A model check is already running. Wait for it to finish.")
        run = {"id": new_id(), "kind": "model", "status": "running", "model": llm.label(), "provider": llm.name,
               "started": now(), "finished": None, "total": len(qs), "results": [], "error": None, "summary": None,
               "settings": dev.model_dump(exclude={"local_url"}), "embedder": deps.index.embedder_name}
        _live[run["id"]] = run
    thread = threading.Thread(target=_run, args=(run, qs, deps, store), daemon=True)
    thread.start()
    if wait:  # the command line waits; the dev panel polls
        thread.join()
    return get(deps, run["id"])  # type: ignore[return-value]


def get(deps, run_id: str) -> dict | None:
    with _lock:
        if run_id in _live:
            return json.loads(json.dumps(_live[run_id]))
    return RunStore.for_settings(deps.settings).get(KIND, run_id)


def listing(deps) -> list[dict]:
    """Saved runs, newest first, without the per-question rows (the dev panel's list and comparison)."""
    keep = ("id", "kind", "model", "provider", "started", "finished", "status", "total", "error", "summary",
            "embedder")
    return [{k: r.get(k) for k in keep} for r in RunStore.for_settings(deps.settings).all(KIND)[:LISTED]]

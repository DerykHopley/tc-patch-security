"""The model check from the command line. Settings come from the environment, as for the app (see .env.example).

    cd backend
    # A model: LLM_PROVIDER, OPENROUTER_MODEL or LOCAL_LLM_URL/LOCAL_LLM_MODEL pick it (not the Dev page's choice)
    LLM_PROVIDER=openrouter OPENROUTER_MODEL=anthropic/claude-haiku-5.5 uv run --env-file .env python -m app.evals model-check
    LLM_PROVIDER=local LOCAL_LLM_MODEL=qwen3:8b uv run --env-file .env python -m app.evals model-check --ids Q1 Q2
    # An embedder: the index at INDEX_PATH must have been built with it (python -m app.rag.build_index)
    EMBEDDER=openrouter INDEX_PATH=data/index-openrouter uv run --env-file .env python -m app.evals retrieval
    EMBEDDER=ollama INDEX_PATH=data/index-ollama uv run --env-file .env python -m app.evals retrieval
    # The report: the latest run per model and per embedder, or the runs named
    uv run python -m app.evals report --findings findings.html --out data/reports/model-check-report.html
    # The published report: exactly the runs and findings docs/report-src/runs.json names (a missing id is an error)
    uv run python -m app.evals report --runs ../docs/report-src/runs.json --out ../docs/report/index.html
    # FakeLLM and two fake embedders in a temporary folder, then the report (what CI builds; no key, no network)
    uv run python -m app.evals fake-report --out /tmp/model-check-report.html
    # The review pages' shared top bar and theme, written into the hand-written pages in docs/report/ (shell.py)
    uv run python -m app.evals shell

Runs are saved next to the state file (STATE_PATH's folder, then evals/), in backend/data/ by default: not in git.
"""
import argparse
import sys
import tempfile
from pathlib import Path

from app.config import ROOT, ConfigError, Settings
from app.errors import InputError
from app.evals import model_check, report, retrieval, shell

DEFAULT_OUT = ROOT / "data" / "reports" / "model-check-report.html"
REVIEW_PAGES = ROOT.parent / "docs" / "report"


def _deps(settings: Settings, llm=None):
    from app.deps import build_deps
    from app.llm.providers import make_llm

    settings.check()
    return build_deps(settings, llm=llm or make_llm(settings))


def _print_model_run(run: dict) -> None:
    s = run["summary"]
    print(f"{run['model']}: {s['passed']} / {s['questions']} questions passed, "
          f"{s['checks_passed']} / {s['checks_total']} checks, cost ${s['cost_total']:.6f}, "
          f"{s['avg_seconds']} s per question. Run {run['id']}.")
    for row in run["results"]:
        if row["error"] or not row["passed"]:
            print(f"  {row['id']}: {row['error'] or ', '.join(f['name'] for f in row['failures'])}")
    if run["error"]:
        print(f"Stopped: {run['error']}")


def _print_retrieval_run(run: dict) -> None:
    for mode, m in run["modes"].items():
        print(f"{run['embedder']} {mode}: hit rate at 5 {m['hit_rate_at_5']}, MRR {m['mrr']}, "
              f"{len(m['misses'])} misses of {m['questions']}.")
    t = run["threshold"]
    on = [x["id"] for x in t["on_topic"] if x["gated"]]
    print(f"Off-topic gate (threshold {t['min_score']}): {len(on)} of {len(t['on_topic'])} on-topic questions gated "
          f"(should be 0{': ' + ', '.join(on) if on else ''}), {sum(x['gated'] for x in t['off_topic'])} of "
          f"{len(t['off_topic'])} off-topic.")
    print(f"Run {run['id']}.")


def fake_report(out: Path) -> Path:
    """FakeLLM's model check, retrieval on the hash embedder and a smaller second fake, the report. All in a temp
    folder: no key, no network, nothing left behind but the page."""
    from app.deps import build_deps
    from app.llm.fake import FakeLLM
    from app.rag.chunking import build_chunks
    from app.rag.embed import HashEmbedder
    from app.rag.keyword import BM25Index
    from app.rag.vector import build_index

    with tempfile.TemporaryDirectory() as tmp:
        settings = Settings(llm_provider="fake", embedder="hash", state_path=Path(tmp) / "state.json",
                            index_path=Path(tmp) / "index")
        deps = build_deps(settings, llm=FakeLLM())
        _print_model_run(model_check.start(deps, wait=True))
        _print_retrieval_run(retrieval.run(deps, deps.index, deps.keyword))
        small = build_index(build_chunks(deps.knowledge), HashEmbedder(dim=256), Path(tmp) / "index-256")
        _print_retrieval_run(retrieval.run(deps, small, BM25Index(small.chunks)))
        html = report.from_store(report.store_of(settings), as_of=settings.as_of)
    return report.write(html, out)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m app.evals", description="The model check, retrieval metrics, report.")
    sub = p.add_subparsers(dest="command", required=True)
    mc = sub.add_parser("model-check", help="run the scripted questions against the model the env names")
    mc.add_argument("--ids", nargs="*", help="only these questions, e.g. Q1 Q2")
    sub.add_parser("retrieval", help="retrieval metrics for the embedder the env names (its index must exist)")
    rp = sub.add_parser("report", help="build the HTML report from saved runs")
    rp.add_argument("--out", type=Path, default=DEFAULT_OUT)
    rp.add_argument("--findings", type=Path, help="an HTML fragment with the written findings")
    rp.add_argument("--models", nargs="*", help="model-check run ids (default: the latest per model)")
    rp.add_argument("--retrieval", nargs="*", help="retrieval run ids (default: the latest per embedder)")
    rp.add_argument("--runs", type=Path, help="a JSON file naming the model-check and retrieval runs and the "
                    "findings (docs/report-src/runs.json): the published report. No fallback to the latest")
    fr = sub.add_parser("fake-report", help="FakeLLM and fake embedders in a temp folder, then the report (CI)")
    fr.add_argument("--out", type=Path, default=DEFAULT_OUT)
    sh = sub.add_parser("shell", help="write the shared top bar and theme into the hand-written review pages")
    sh.add_argument("--dir", type=Path, default=REVIEW_PAGES)
    args = p.parse_args(argv)
    if args.command == "report" and args.runs and (args.models or args.retrieval or args.findings):
        p.error("--runs names the runs and the findings itself: drop --models, --retrieval and --findings")

    try:
        if args.command == "shell":
            changed = shell.write(args.dir)
            print(f"Updated: {', '.join(changed)}" if changed else "Every page already has the current shell.")
        elif args.command == "fake-report":
            print(f"Report: {fake_report(args.out)}")
        elif args.command == "model-check":
            _print_model_run(model_check.start(_deps(Settings.from_env()), args.ids or None, wait=True))
        elif args.command == "retrieval":
            from app.llm.fake import FakeLLM

            deps = _deps(Settings.from_env(), llm=FakeLLM())  # no model is asked: retrieval only
            _print_retrieval_run(retrieval.run(deps, deps.index, deps.keyword))
        else:
            settings = Settings.from_env()
            if args.runs:
                models, retrieval_ids, findings = report.runs_file(args.runs)
            else:
                models, retrieval_ids = args.models, args.retrieval
                findings = args.findings.read_text() if args.findings else None
            html = report.from_store(report.store_of(settings), settings.as_of, models, retrieval_ids, findings)
            print(f"Report: {report.write(html, args.out)}")
    except (ConfigError, InputError) as e:
        print(e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

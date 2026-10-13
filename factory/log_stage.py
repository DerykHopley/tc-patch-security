#!/usr/bin/env python3
"""Record which Claude Code session did which factory stage.

Run it at the end of a stage, from inside that session:

    python3 factory/log_stage.py spec --tests none --notes "spec.md written"

With no --session it picks the newest transcript for the current directory,
which is the session you're running it from. So it also works from another
folder (e.g. the superpowers arm): python3 <path>/factory/log_stage.py ...
Entries always go to this folder's factory/stages.json.
"""
import argparse
import datetime as dt
import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent
STAGES_FILE = HERE / "stages.json"


def transcripts_dir(project: pathlib.Path) -> pathlib.Path:
    # Claude Code stores transcripts under ~/.claude/projects/<path, non-alphanumerics as ->.
    return pathlib.Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(project))


def newest_session(tdir: pathlib.Path) -> str:
    files = sorted(tdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime)
    if not files:
        raise SystemExit(f"No transcripts in {tdir}")
    return files[-1].stem


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("stage", help="spec, plan, build-backend, build-frontend, review, ...")
    p.add_argument("--workflow", default="staged", help="which factory: staged, superpowers, ...")
    p.add_argument("--session", help="session id (default: newest transcript)")
    p.add_argument("--tests", default="none", help="pass, fail, none, or e.g. '14/15'")
    p.add_argument("--step-ins", type=int, help="times you had to correct or unblock the agent")
    p.add_argument("--notes", default="")
    a = p.parse_args()

    stages = json.loads(STAGES_FILE.read_text()) if STAGES_FILE.exists() else []
    tdir = transcripts_dir(pathlib.Path.cwd())
    sid = a.session or newest_session(tdir)
    entry = {
        "workflow": a.workflow,
        "stage": a.stage,
        "session": sid,
        "tests": a.tests,
        "step_ins": a.step_ins,
        "notes": a.notes,
        "transcripts": str(tdir),
        "logged": dt.datetime.now().isoformat(timespec="seconds"),
    }
    # One entry per session: logging again replaces it.
    stages = [s for s in stages if s["session"] != sid] + [entry]
    STAGES_FILE.write_text(json.dumps(stages, indent=2) + "\n")
    print(f"Logged {a.stage} -> {sid}")


if __name__ == "__main__":
    main()

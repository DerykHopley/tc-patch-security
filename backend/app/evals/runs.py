"""Saved runs: one JSON file per run, next to the state file (STATE_PATH's folder, then evals/models or
evals/retrieval). backend/data/ is in .gitignore, so runs never reach git by accident; A20 picks the ones it publishes.
"""
import datetime as dt
import json
import re
import uuid
from pathlib import Path

KINDS = ("models", "retrieval")
LISTED = 50  # newest runs listed in the dev panel
_ID = re.compile(r"^[0-9]{8}-[0-9]{6}-[0-9a-f]{4}$")


def new_id() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class RunStore:
    def __init__(self, folder: Path):
        self.folder = Path(folder)

    @classmethod
    def for_settings(cls, settings) -> "RunStore":
        return cls(settings.state_path.parent / "evals")

    def _path(self, kind: str, run_id: str) -> Path:
        return self.folder / kind / f"{run_id}.json"

    def save(self, kind: str, run: dict) -> None:
        path = self._path(kind, run["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(run, indent=1))

    def get(self, kind: str, run_id: str) -> dict | None:
        if not _ID.match(run_id):  # ids only: a path can't sneak in
            return None
        path = self._path(kind, run_id)
        return json.loads(path.read_text()) if path.exists() else None

    def all(self, kind: str) -> list[dict]:
        """Every saved run of this kind, newest first."""
        folder = self.folder / kind
        files = sorted(folder.glob("*.json"), reverse=True) if folder.exists() else []
        return [json.loads(p.read_text()) for p in files]

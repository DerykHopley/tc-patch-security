"""Saved runs: one JSON document per run, `models/<id>.json` or `retrieval/<id>.json`, in a state store (app.store).
Locally they are files next to the state file (STATE_PATH's folder, then evals/); backend/data/ is in .gitignore, so
runs never reach git by accident; A20 picks the ones it publishes. Deployed (STORE=gcs), they are objects under
`evals/` in the state bucket (B58, #104): the instance's disk goes when Cloud Run scales to zero.
"""
import datetime as dt
import re
import uuid

from app.store import EVALS_PREFIX, GcsStore, LocalStore, Store, open_bucket

KINDS = ("models", "retrieval")
LISTED = 50  # newest runs listed in the dev panel
_ID = re.compile(r"^[0-9]{8}-[0-9]{6}(-[0-9]{3})?-[0-9a-f]{4}$")  # milliseconds since A19; older ids still load


def new_id() -> str:
    """Sorts by time: with milliseconds, two runs in the same second still list newest first."""
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S-%f")[:-3] + "-" + uuid.uuid4().hex[:4]


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


class RunStore:
    """Finished runs, key `<kind>/<id>.json`. A model check in progress stays in memory (model_check._live); only a
    finished run is saved, once."""

    def __init__(self, store: Store):
        self.store = store

    @classmethod
    def for_settings(cls, settings, bucket=None) -> "RunStore":
        """STORE=local: files under STATE_PATH's folder, `evals/`, as before. STORE=gcs: objects under `evals/` in the
        bucket (`open_bucket`; tests pass the fake one), next to `users/` and `live/`."""
        b = open_bucket(settings, bucket)
        if b is not None:
            return cls(GcsStore(b, EVALS_PREFIX))
        return cls(LocalStore(settings.state_path.parent / "evals"))

    def save(self, kind: str, run: dict) -> None:
        self.store.write(f"{kind}/{run['id']}.json", run)

    def get(self, kind: str, run_id: str) -> dict | None:
        if not _ID.match(run_id):  # ids only: a path can't sneak in
            return None
        return self.store.read(f"{kind}/{run_id}.json")[0]

    def all(self, kind: str) -> list[dict]:
        """Every saved run of this kind, newest first (ids sort by time)."""
        runs = (self.store.read(k)[0] for k in sorted(self.store.keys(f"{kind}/"), reverse=True))
        return [r for r in runs if r is not None]  # one deleted between the listing and its read is skipped

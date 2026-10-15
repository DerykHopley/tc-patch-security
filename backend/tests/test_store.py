"""The state store (B09, #41): read a key's data with its version, write it only if the version still matches.
Check ids: B09.n.

One contract, three stores: the local JSON files (today's state file and lock), the in-memory store for tests, and
Cloud Storage with the object's generation as the write precondition, here against a fake bucket (no network, no
GCP account: the deployment is #44).
"""
import json

import pytest

from app.store import ANY, Conflict, GcsStore, LocalStore, MemoryStore
from app.live_data import FILES
from tests.fake_gcs import FakeBucket


@pytest.fixture(params=["local", "memory", "gcs"])
def store(request, tmp_path):
    return {"local": lambda: LocalStore(tmp_path / "store"), "memory": MemoryStore,
            "gcs": lambda: GcsStore(FakeBucket(), prefix="patch/")}[request.param]()


def test_b09_1_a_missing_key_reads_as_none_with_no_version(store):
    assert store.read("users/alice.json") == (None, None)


def test_b09_1_a_write_returns_the_version_a_read_gives(store):
    v1 = store.write("users/alice.json", {"watchlist": ["ollama"]}, if_version=None)
    data, version = store.read("users/alice.json")
    assert data == {"watchlist": ["ollama"]} and version == v1
    v2 = store.write("users/alice.json", {"watchlist": []}, if_version=v1)
    assert v2 != v1 and store.read("users/alice.json") == ({"watchlist": []}, v2)


def test_b09_1_a_write_on_a_stale_version_is_a_conflict_and_changes_nothing(store):
    v1 = store.write("k.json", {"n": 1}, if_version=None)
    store.write("k.json", {"n": 2}, if_version=v1)  # someone else wrote in between
    with pytest.raises(Conflict):
        store.write("k.json", {"n": 3}, if_version=v1)
    assert store.read("k.json")[0] == {"n": 2}


def test_b09_1_creating_a_key_that_exists_is_a_conflict(store):
    store.write("k.json", {"n": 1}, if_version=None)
    with pytest.raises(Conflict):
        store.write("k.json", {"n": 9}, if_version=None)  # None: only if there is nothing yet


def test_b09_1_any_version_writes_unconditionally(store):
    store.write("k.json", {"n": 1})
    store.write("k.json", {"n": 2})
    assert store.read("k.json")[0] == {"n": 2}


def test_b09_1_delete_and_keys_by_prefix(store):
    for key in ("users/a.json", "users/b.json", "shared/refresh.json"):
        store.write(key, {})
    assert store.keys("users/") == ["users/a.json", "users/b.json"]
    store.delete("users/a.json")
    store.delete("users/missing.json")  # deleting nothing is fine
    assert store.keys("users/") == ["users/b.json"] and store.read("users/a.json") == (None, None)


def test_b09_1_the_local_store_keeps_named_keys_at_their_old_paths(tmp_path):
    """The default user's state is today's file, wherever STATE_PATH points: an existing file loads unchanged."""
    old = tmp_path / "elsewhere" / "state.json"
    old.parent.mkdir()
    old.write_text(json.dumps({"watchlist": ["ollama"], "statuses": {}}))
    store = LocalStore(tmp_path / "store", paths={"users/default.json": old})
    assert store.read("users/default.json")[0] == {"watchlist": ["ollama"], "statuses": {}}
    assert store.keys("users/") == ["users/default.json"]
    store.write("users/default.json", {"watchlist": []})
    assert json.loads(old.read_text()) == {"watchlist": []}
    store.delete("users/default.json")
    assert not old.exists() and store.keys("users/") == []


class Racing(MemoryStore):
    """Another instance writes the same key between this one's read and its write, `times` times."""

    def __init__(self, times: int):
        super().__init__()
        self.times = times

    def write(self, key, data, if_version=ANY):
        if self.times and if_version is not ANY:
            self.times -= 1
            other, version = self.read(key)
            other = other or {"watchlist": ["vllm"], "statuses": {}, "history": {}}
            super().write(key, {**other, "statuses": {**other["statuses"], "CVE-2025-3248": "fixed"}}, version)
        return super().write(key, data, if_version)


def test_b09_11_a_write_that_conflicts_reads_again_and_keeps_both_changes(knowledge):
    from app.state import State

    store = Racing(times=2)
    state = State(None, knowledge, store=store, key="alice.json")
    state.set_status("CVE-2024-8309", "fixed")
    assert state.read().statuses == {"CVE-2025-3248": "fixed", "CVE-2024-8309": "fixed"}


def test_b09_11_a_write_that_keeps_conflicting_fails_plainly(knowledge):
    from app.state import State

    state = State(None, knowledge, store=Racing(times=99), key="alice.json")
    with pytest.raises(Conflict, match="changed by someone else"):
        state.set_status("CVE-2024-8309", "fixed")


def test_b09_12_the_live_data_and_the_refresh_record_are_shared_keys_in_a_store(tmp_path):
    """Deployed, the live versions and the run log are objects in the bucket; the folder is only a local copy that
    load_knowledge reads. Two servers on one store see the same version and the same last check."""
    from app.feeds import FakeFeeds
    from app.knowledge import load_knowledge
    from app.live_data import LiveData
    from app.refresh import Refresher
    from test_refresh import NEW_DAY1, Clock

    store = GcsStore(FakeBucket(), prefix="live/")
    clock = Clock("2026-10-14T09:00:00+00:00")
    one = Refresher(LiveData(tmp_path / "one", store), FakeFeeds(day=1), clock)
    result = one.run("cli").result
    assert result.status == "ok" and result.version == 2
    assert {"current.json", "refresh.json", "v000002/cves.json"} <= set(store.keys())
    assert store.read("refresh.json")[0]["last_checked"] == "2026-10-14T09:00:00+00:00"

    two = Refresher(LiveData(tmp_path / "two", store), FakeFeeds(day=1), clock)  # another instance, its own copy
    assert two.live.version() == 2 and two.last_checked() == "2026-10-14T09:00:00+00:00"
    assert NEW_DAY1 in {c["id"] for c in load_knowledge(two.live.folder()).cves.all()}
    assert two.run("cli").refusal.reason == "too_soon"  # the 5-minute rule reads the shared log


def test_b09_12_an_existing_live_folder_loads_unchanged(tmp_path):
    from app.feeds import FakeFeeds
    from app.live_data import LiveData
    from app.refresh import Refresher
    from test_refresh import Clock

    clock = Clock("2026-10-14T09:00:00+00:00")
    Refresher(LiveData(tmp_path / "live"), FakeFeeds(day=1), clock).run("cli")
    names = sorted(p.relative_to(tmp_path / "live").as_posix() for p in (tmp_path / "live").rglob("*"))
    assert names == ["current.json", "refresh.json", "refresh.lock", "v000001", *sorted(f"v000001/{n}" for n in FILES),
                     "v000002", *sorted(f"v000002/{n}" for n in FILES)]
    again = Refresher(LiveData(tmp_path / "live"), FakeFeeds(day=1), clock)
    assert again.live.version() == 2 and again.last_checked() == "2026-10-14T09:00:00+00:00"


def test_b09_1_the_gcs_store_writes_with_the_generation_as_precondition():
    bucket = FakeBucket()
    store = GcsStore(bucket, prefix="patch/")
    v1 = store.write("users/a.json", {"n": 1}, if_version=None)
    assert bucket.calls[-1] == ("upload", "patch/users/a.json", 0)  # 0: only if the object doesn't exist
    store.write("users/a.json", {"n": 2}, if_version=v1)
    assert bucket.calls[-1] == ("upload", "patch/users/a.json", int(v1))

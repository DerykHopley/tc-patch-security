import json
import threading

import pytest

from app.config import DEFAULT_WATCHLIST
from app.errors import InputError


def test_w1_default_watchlist_without_file(deps):
    assert not deps.state.path.exists()
    assert deps.state.snapshot() == {"watchlist": DEFAULT_WATCHLIST, "statuses": {}}


def test_w1_open_removes_stored_status(deps):
    deps.state.set_status("CVE-2024-8309", "fixed")
    deps.state.set_status("CVE-2024-8309", "open")
    assert json.loads(deps.state.path.read_text())["statuses"] == {}


def test_w2_atomic_write_leaves_no_temp_files(deps):
    deps.state.watch("vllm")
    assert [p.name for p in deps.state.path.parent.iterdir()] == ["state.json"]


def test_w2_concurrent_writes_lose_nothing(deps):
    ids = [c["id"] for c in deps.knowledge.cves.all()[:40]]
    threads = [threading.Thread(target=deps.state.set_status, args=(i, "fixed")) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(deps.state.snapshot()["statuses"]) == 40


def test_w4_errors(deps):
    with pytest.raises(InputError):
        deps.state.watch("Notion")
    with pytest.raises(InputError):
        deps.state.set_status("CVE-2024-8309", "done")
    with pytest.raises(KeyError):
        deps.state.set_status("CVE-1999-0001", "fixed")

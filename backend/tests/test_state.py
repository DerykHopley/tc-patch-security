"""State: watchlist and CVE statuses (moved from proto, its W1, W2, W4). Check ids: A01.n."""
import json
import threading

import pytest

from app.config import DEFAULT_WATCHLIST
from app.errors import InputError


@pytest.fixture
def state(deps):
    return deps.state


def test_a01_2_default_watchlist_without_file(state):
    assert not state.path.exists()
    assert state.snapshot() == {"watchlist": DEFAULT_WATCHLIST, "statuses": {}}


def test_a01_2_open_removes_stored_status(state):
    state.set_status("CVE-2024-8309", "fixed")
    state.set_status("CVE-2024-8309", "open")
    assert json.loads(state.path.read_text())["statuses"] == {}


def test_a01_2_watch_and_unwatch_round_trip(state):
    assert state.watch("vLLM") == (DEFAULT_WATCHLIST + ["vllm"], True)
    assert state.watch("vllm") == (DEFAULT_WATCHLIST + ["vllm"], False)
    assert state.unwatch("vllm") == (DEFAULT_WATCHLIST, True)


def test_a01_2_reset_returns_to_defaults(state):
    state.set_watchlist(["ollama"])
    state.reset()
    assert state.snapshot() == {"watchlist": DEFAULT_WATCHLIST, "statuses": {}}


def test_a01_2_status_of_a_cve(state, knowledge):
    data = state.snapshot()
    cve = knowledge.cves.get("CVE-2024-8309")  # LangChain, on the default watchlist
    assert state.status_of(cve, data) == "open"
    state.set_status(cve["id"], "fixed")
    assert state.status_of(cve, state.snapshot()) == "fixed"
    state.unwatch(cve["product"])
    assert state.status_of(cve, state.snapshot()) == "not_watched"


def test_a01_2_keeps_parts_saved_by_later_tickets(state):
    state.path.write_text(json.dumps({"watchlist": ["ollama"], "statuses": {}, "settings": {"x": 1}}))
    state.watch("vllm")
    assert json.loads(state.path.read_text())["settings"] == {"x": 1}


def test_a01_3_atomic_write_leaves_no_temp_files(state):
    state.watch("vllm")
    assert [p.name for p in state.path.parent.iterdir()] == ["state.json"]


def test_a01_3_concurrent_writes_lose_nothing(state, knowledge):
    ids = [c["id"] for c in knowledge.cves.all()[:40]]
    threads = [threading.Thread(target=state.set_status, args=(i, "fixed")) for i in ids]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(state.snapshot()["statuses"]) == 40


def test_a01_4_errors_have_plain_messages(state):
    with pytest.raises(InputError, match="isn't a product I track. Choose from: .*LangChain"):
        state.watch("Notion")
    with pytest.raises(InputError, match="Status must be one of open, fixed, not_affected, not 'done'"):
        state.set_status("CVE-2024-8309", "done")
    with pytest.raises(KeyError):
        state.set_status("CVE-1999-0001", "fixed")

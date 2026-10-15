"""State: watchlist and CVE statuses (moved from proto, its W1, W2, W4). Check ids: A01.n."""
import json
import threading

import pytest

from app.config import DEFAULT_WATCHLIST
from app.errors import InputError
from app.state import ProductFields


@pytest.fixture
def state(deps):
    return deps.state


def test_a01_2_default_watchlist_without_file(state):
    assert not state.path.exists()
    stack = state.read()
    assert stack.watchlist == tuple(DEFAULT_WATCHLIST)
    assert stack.statuses == {} and stack.history("CVE-2024-8309") == [] and stack.decision("CVE-2024-8309") is None
    assert stack.fields("langchain") == ProductFields(usage="library", version=None, internet_facing=False)
    assert stack.fields("ollama") == ProductFields(usage="self_hosted", version=None, internet_facing=False)
    assert stack.settings.alerts.min_severity == "HIGH" and stack.alerts_log == ()


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
    state.set_status("CVE-2024-8309", "fixed")
    state.reset()
    assert (state.read().watchlist, state.read().statuses) == (tuple(DEFAULT_WATCHLIST), {})
    assert state.read().history("CVE-2024-8309") == []


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
    assert len(state.read().statuses) == 40


def test_a01_4_errors_have_plain_messages(state):
    with pytest.raises(InputError, match="isn't a product I track. Choose from: .*LangChain"):
        state.watch("Notion")
    with pytest.raises(InputError, match="Status must be one of open, fixed, not_affected, accepted, not 'done'"):
        state.set_status("CVE-2024-8309", "done")
    with pytest.raises(KeyError):
        state.set_status("CVE-1999-0001", "fixed")


# --- The read model (architecture review candidate 4): State.read() gives your stack, typed and frozen ----------

def test_read_follows_the_writes(state):
    state.set_watchlist(["Ollama", "Langflow"], {"Langflow": {"version": "1.3.0", "internet_facing": True}})
    state.set_status("CVE-2025-3248", "fixed", note="upgraded")
    stack = state.read()
    assert stack.watchlist == ("ollama", "langflow") and stack.watches("langflow") and not stack.watches("vllm")
    assert stack.fields("langflow") == ProductFields(usage="self_hosted", version="1.3.0", internet_facing=True)
    assert stack.statuses == {"CVE-2025-3248": "fixed"}
    d = stack.decision("CVE-2025-3248")
    assert (d["status"], d["note"], d["via"]) == ("fixed", "upgraded", "page")
    assert stack.history("CVE-2025-3248") == [d]


def test_read_gives_a_status_saved_before_decision_records_its_record(state):
    state.path.write_text(json.dumps({"watchlist": ["langflow"], "statuses": {"CVE-2025-3248": "fixed"}}))
    d = state.read().decision("CVE-2025-3248")
    assert (d["status"], d["note"], d["decided_at"]) == ("fixed", "recorded before decision records", None)


def test_a_read_is_a_frozen_value(state):
    state.set_status("CVE-2025-3248", "fixed")
    stack = state.read()
    with pytest.raises(AttributeError):
        stack.watchlist = ("vllm",)
    with pytest.raises(TypeError):
        stack.statuses["CVE-2025-3248"] = "open"
    stack.history("CVE-2025-3248")[0]["status"] = "open"  # a copy
    assert stack.decision("CVE-2025-3248")["status"] == "fixed"
    state.watch("vllm")
    assert "vllm" not in stack.watchlist  # later writes don't change it


def test_fork_copies_the_state_and_its_writes_stay_on_the_copy(state, tmp_path):
    state.set_watchlist(["langflow"])
    state.set_status("CVE-2025-3248", "fixed")
    copy = state.fork(tmp_path / "fork" / "state.json")
    assert copy.read() == state.read()
    copy.watch("ollama")
    copy.set_status("CVE-2025-3248", "open")
    assert (state.read().watchlist, state.read().statuses) == (("langflow",), {"CVE-2025-3248": "fixed"})
    assert copy.read().watchlist == ("langflow", "ollama")

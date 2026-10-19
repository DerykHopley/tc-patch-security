"""Code review fixes on spec B (#31). Check ids: BR.n.

Seams: the HTTP API (seam 1) with fake users by overriding the auth dependency, as B09's tests do; the settings'
start-up check; web research against the fake Tavily (seam 3).
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.auth import current_user
from tests.test_per_user import LiveUsers, as_header


def app_for(settings, knowledge, index, **changes):
    """An app with these settings changed; `client(user)` asks as that user."""
    from app.deps import build_deps
    from app.main import create_app

    deps = build_deps(dataclasses.replace(settings, **changes), knowledge=knowledge, index=index)
    app = create_app(deps)
    app.dependency_overrides[current_user] = as_header

    def client(user: str = "default") -> TestClient:
        return TestClient(app, raise_server_exceptions=False, headers={"x-test-user": user})
    client.deps = deps  # type: ignore[attr-defined]
    return client


# --- BR.1: Try again counts against the chat limit when the tool calls a model or the network, and runs only the
# tools offered to that user ----------------------------------------------------------------------------------------

def test_br_1_try_again_on_a_tool_that_asks_the_model_counts_as_a_chat_message(settings, knowledge, index):
    alice = app_for(settings, knowledge, index, chat_per_minute=1)("alice")
    search = {"name": "search_security", "args": {"query": "prompt injection"}}
    assert alice.post("/chat/tool", json=search).status_code == 200
    r = alice.post("/chat/tool", json=search)
    assert r.status_code == 429 and r.json()["error"]["code"] == "rate_limited"
    assert alice.post("/chat", json={"message": "What is prompt injection?"}).status_code == 429  # the same limit


def test_br_1_try_again_on_a_tool_that_reads_only_local_data_is_free(settings, knowledge, index):
    alice = app_for(settings, knowledge, index, chat_per_minute=1)("alice")
    lookup = {"name": "lookup_cve", "args": {"cve_id": "CVE-2025-3248"}}
    for _ in range(3):
        assert alice.post("/chat/tool", json=lookup).json()["status"] == "ok"
    assert alice.post("/chat", json={"message": "What is prompt injection?"}).status_code == 200


@pytest.mark.parametrize("name", ["research_web", "propose_decision", "no_such_tool"])
def test_br_1_try_again_refuses_a_tool_that_is_not_offered(client, name):
    r = client.post("/chat/tool", json={"name": name, "args": {"query": "Langflow"}})
    assert r.status_code == 400 and r.json()["error"]["code"] == "not_offered"
    assert name in r.json()["error"]["message"]


# --- BR.2: a web result's link is http(s) only ----------------------------------------------------------------------

@pytest.mark.parametrize("url, ok", [
    ("https://example.org/a", True), ("http://example.org/a", True), ("HTTPS://Example.org/", True),
    ("javascript:alert(1)", False), ("JavaScript:alert(1)", False), ("data:text/html,<b>x</b>", False),
    ("ftp://example.org/a", False), ("//example.org/a", False), ("example.org/a", False), ("https:///nohost", False),
])
def test_br_2_only_http_and_https_links_are_kept(url, ok):
    from app.web_research import web_link

    assert web_link(url) is ok


def test_br_2_a_result_with_a_script_link_is_dropped(settings, knowledge, index):
    from app.deps import build_deps
    from app.llm.base import ToolCall
    from app.tools.registry import Context, run_tool
    from app.web_research import CannedWeb

    deps = build_deps(settings, knowledge=knowledge, index=index)
    web = CannedWeb()
    web._results = [{"title": "Bad", "url": "javascript:alert(document.cookie)", "content": "x"},
                    {"title": "Good", "url": "https://nvd.nist.gov/vuln/detail/CVE-2025-3248", "content": "y"}]
    deps.web = web
    rec = run_tool(ToolCall(id="w", name="research_web", args={"query": "Langflow"}), deps, Context())
    assert [r["url"] for r in rec.result["results"]] == ["https://nvd.nist.gov/vuln/detail/CVE-2025-3248"]


# --- BR.9: the schedule is the owner's: others see it, read-only --------------------------------------------------

def test_br_9_a_non_owner_sees_the_owners_schedule_and_cant_change_it(tmp_path, index_dir, index):
    app = LiveUsers(tmp_path, index_dir)
    alice, owner = app("alice"), app.live.client
    body = owner.get("/settings").json()["settings"]
    body["alerts"] |= {"schedule_paused": True, "schedule_hours": 12}
    assert owner.put("/settings", json=body).status_code == 200

    got = alice.get("/settings").json()
    assert got["schedule"] == {"hours": 12, "paused": True, "next_due": None, "yours": False}
    assert alice.get("/dashboard").json()["data"]["schedule"]["yours"] is False
    assert alice.get("/refresh/runs").json()["schedule"]["yours"] is False
    assert owner.get("/settings").json()["schedule"]["yours"] is True

    mine = got["settings"]
    for change in ({"schedule_paused": True}, {"schedule_hours": 1}):
        r = alice.put("/settings", json=mine | {"alerts": mine["alerts"] | change})
        assert r.status_code == 403 and r.json()["error"]["code"] == "not_owner"
        assert "owner" in r.json()["error"]["message"]
    # the rest of their settings still save, with the schedule fields as they were
    r = alice.put("/settings", json=mine | {"alerts": mine["alerts"] | {"min_severity": "LOW"}})
    assert r.status_code == 200 and r.json()["settings"]["alerts"]["min_severity"] == "LOW"
    assert owner.get("/refresh/runs").json()["schedule"]["paused"] is True


# --- BR.10: a user who signed in counts for the refresh, with the default watchlist, and stays after a reset -------

def test_br_10_a_signed_in_user_who_saved_nothing_gets_alerts_and_new_since_check(tmp_path, index_dir, index):
    from test_refresh import NEW_DAY2

    app = LiveUsers(tmp_path, index_dir)
    carol = app("carol")
    assert carol.get("/health").status_code == 200  # /health isn't a user's request
    assert carol.get("/dashboard").status_code == 200  # a read only: nothing saved
    assert not [k for k in app.live.deps.users.store.keys() if k.startswith("carol")]
    app.live.check_now()
    app.live.next_day()
    assert app.alerts("carol")["carol"]
    assert NEW_DAY2 in {r["id"] for r in carol.get("/cves", params={"status": "all", "new": "1"}).json()["rows"]}


def test_br_10_a_reset_keeps_the_user_known(tmp_path, index_dir, index):
    app = LiveUsers(tmp_path, index_dir)
    dave = app("dave")
    dave.put("/watchlist", json={"products": ["ollama"]})
    dave.post("/state/reset", json={"confirm": "reset"})
    assert "dave" in app.live.deps.users.ids()
    app.live.start()  # a restart: the record is in the store, not only in memory
    assert "dave" in app.live.deps.users.ids()


def test_br_10_the_known_users_record_is_written_once_per_user(settings, knowledge, index):
    client = app_for(settings, knowledge, index)
    store, writes = client.deps.users.store, []
    real = store.write
    store.write = lambda key, data, *a, **kw: (writes.append(key), real(key, data, *a, **kw))[1]
    for _ in range(3):
        client("erin").get("/dashboard")
    assert len(writes) == 1 and "erin" in client.deps.users.ids()


# --- BR.11: sign-in on needs a real OWNER ------------------------------------------------------------------------

@pytest.mark.parametrize("owner", [None, "default"])
def test_br_11_sign_in_on_without_an_owner_stops_the_start_up(monkeypatch, owner):
    from app.config import ConfigError, Settings
    from tests.test_auth import ORIGIN, PUBLIC

    for name, value in {"AUTH": "on", "CLERK_PUBLISHABLE_KEY": "pk_test_x", "CLERK_JWT_KEY": PUBLIC,
                        "AUTH_ALLOWED_ORIGINS": ORIGIN}.items():
        monkeypatch.setenv(name, value)
    if owner is None:
        monkeypatch.delenv("OWNER", raising=False)
    else:
        monkeypatch.setenv("OWNER", owner)
    with pytest.raises(ConfigError, match="AUTH=on needs OWNER"):
        Settings.from_env().check()
    monkeypatch.setenv("OWNER", "user_2abc")
    Settings.from_env().check()


# --- BR.12: the fake-feeds and failure switches are the owner's ----------------------------------------------------

def test_br_12_only_the_owner_flips_the_switches(tmp_path, index_dir, index):
    app = LiveUsers(tmp_path, index_dir, feeds="fake")
    alice, owner = app("alice"), app.live.client
    for path, body in (("/refresh/reset", {"confirm": "reset"}), ("/refresh/fake-feeds", {"fail": ["nvd"]}),
                       ("/dev/fail-tools", {"tools": ["search_security"]})):
        r = alice.post(path, json=body)
        assert r.status_code == 403 and r.json()["error"]["code"] == "not_owner", path
        assert owner.post(path, json=body).status_code == 200, path

import json

import pytest
from fastapi.testclient import TestClient

from app.agent import answer
from app.config import Settings
from app.deps import build_deps
from app.llm.base import LLMReply, ToolCall
from app.llm.fake import FakeLLM
from app.main import create_app
from app.rag.pipeline import SearchOptions, search_security

Q5 = "How do I protect a RAG app from indirect prompt injection?"


@pytest.fixture
def client(deps):
    return TestClient(create_app(deps), raise_server_exceptions=False)


def put_dev(client, **dev):
    s = client.get("/settings").json()["settings"]
    s["dev"] |= dev
    return client.put("/settings", json=s)


# --- G1–G4: settings page

def test_g1_defaults_come_from_env(shared, tmp_path):
    k, index = shared
    deps = build_deps(Settings(state_path=tmp_path / "s.json", max_steps=6, openrouter_model="x/y"), knowledge=k, index=index)
    dev = deps.state.settings().dev
    assert (dev.max_steps, dev.model) == (6, "x/y")


def test_g2_save_and_reload(client, deps):
    s = client.get("/settings").json()
    env = s["env"]
    assert (env["llm_provider"], env["env_model"], env["openrouter_key"], env["dev_panel"]) == ("fake", "openai/gpt-4o-mini", False, True)
    assert set(env["channels"]) == {"desktop", "email", "ntfy"}
    body = s["settings"]
    body["alerts"] |= {"min_severity": "CRITICAL", "schedule_hours": 12, "quiet_start": "22:00", "quiet_end": "07:00"}
    assert client.put("/settings", json=body).status_code == 200
    saved = json.loads(deps.state.path.read_text())["settings"]["alerts"]
    assert (saved["min_severity"], saved["schedule_hours"], saved["quiet_start"]) == ("CRITICAL", 12, "22:00")
    # Saving settings keeps the watchlist
    assert json.loads(deps.state.path.read_text())["watchlist"] == deps.state.snapshot()["watchlist"]


def test_g2_older_state_file_still_loads(deps):
    deps.state.path.write_text(json.dumps({"watchlist": ["ollama"], "statuses": {}, "settings": {"dev": {"top_n": 3}}}))
    s = deps.state.settings()
    assert s.dev.top_n == 3 and s.dev.max_steps == 4 and s.alerts.min_severity == "HIGH"


@pytest.mark.parametrize("patch", [
    {"alerts": {"schedule_hours": 5}}, {"alerts": {"quiet_start": "25:00"}}, {"alerts": {"digest_over": 0}},
    {"dev": {"max_steps": 9}}, {"dev": {"temperature": 3}}, {"dev": {"model": "no slash"}}, {"dev": {"top_n": 0}},
])
def test_g2_bad_values_400(client, patch):
    body = client.get("/settings").json()["settings"]
    for part, values in patch.items():
        body[part] |= values
    r = client.put("/settings", json=body)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


def test_g3_test_alert_recorded_not_sent(client):
    r = client.post("/alerts/test", json={"channel": "preview"}).json()
    assert r["notifier"] == "preview" and r["sent"] is False and "nothing was sent" in r["note"]
    a = r["alert"]
    assert a["title"].startswith("Test · In CISA KEV: Langflow") and a["priority"] == 5
    assert "remediation due" in a["body"]
    log = client.get("/alerts").json()["alerts"]
    assert log[0]["title"] == a["title"] and log[0]["sent"] is False


def test_g3_alert_has_no_description_text(deps, shared):
    from app.notify import format_alert
    k, _ = shared
    cve = k.cves.get("CVE-2024-8309")
    msg = format_alert(cve, "new", k)
    assert cve["description"][:30] not in json.dumps(msg)
    assert msg["priority"] == 4  # new + critical


def test_g3_test_alert_needs_an_open_cve(client):
    client.put("/watchlist", json={"products": ["llamaindex"]})
    for row in client.get("/cves?status=open&limit=200").json()["rows"]:
        client.patch(f"/cves/{row['id']}", json={"status": "fixed"})
    assert client.post("/alerts/test").status_code == 400


def test_g4_reset_needs_the_word_and_restores_defaults(client, deps):
    client.put("/watchlist", json={"products": ["vllm"]})
    put_dev(client, top_n=2)
    assert client.post("/state/reset", json={"confirm": "yes"}).status_code == 400
    r = client.post("/state/reset", json={"confirm": "reset"}).json()
    assert r["watchlist"] == ["langchain", "langflow", "litellm", "ollama", "open-webui"]
    assert deps.state.settings().dev.top_n == 5


# --- X1–X4: dev panel

class LoopingLLM(FakeLLM):
    def step(self, messages, tools):
        return LLMReply(tool_calls=[ToolCall(id="x", name="lookup_cve", args={"cve_id": "CVE-2024-8309"})])


def test_x1_max_steps_from_settings(client, deps):
    put_dev(client, max_steps=2)
    deps.llm = LoopingLLM()
    assert answer("loop", [], deps).steps == 2


def test_x1_openrouter_reads_options_per_call():
    from app.llm.openrouter import OpenRouterLLM
    from app.schemas import DevSettings

    sent = {}

    class FakeCompletions:
        def create(self, **kw):
            sent.update(kw)
            raise RuntimeError("stop")  # we only need the arguments

    llm = OpenRouterLLM("key", "env/model", options=lambda: DevSettings(model="a/b", temperature=0.7))
    assert llm.base_url == "https://openrouter.ai/api/v1"
    llm.client.chat.completions = FakeCompletions()
    with pytest.raises(RuntimeError):
        llm._create(messages=[])
    assert (sent["model"], sent["temperature"]) == ("a/b", 0.7)


def test_x2_search_options(deps):
    def run(**o):
        return search_security(Q5, deps.llm, deps.index, deps.knowledge.resolve_product, opts=SearchOptions(**o))
    assert len(run().lists) == 4 and len(run(use_rewrites=False).lists) == 1
    assert len(run(top_n=3).sources) == 3
    docs = [s.doc_id for s in run(per_doc_cap=1, top_n=10).sources]
    assert len(docs) == len(set(docs))
    q1 = "Which critical Langflow vulnerabilities were published in 2026?"
    off = search_security(q1, deps.llm, deps.index, deps.knowledge.resolve_product, opts=SearchOptions(use_filters=False))
    assert off.query.filters == {} and any("(filters off)" in d for d in off.query.dropped_filters)


def test_x2_chat_uses_saved_search_settings(client):
    put_dev(client, top_n=2)
    body = client.post("/chat", json={"message": Q5}).json()
    assert len(body["sources"]) == 2


def test_x3_dev_search_shows_each_step(client):
    r = client.post("/dev/search", json={"query": Q5}).json()
    assert len(r["lists"]) == 4 and r["lists"][0]["query"] == "protect RAG application from indirect prompt injection"
    assert r["fused"] and r["fused"][0]["rrf"] >= r["fused"][-1]["rrf"]
    assert len(r["final"]) == 5
    info = client.get("/dev/info").json()
    assert info["chunks"] == 1680 and info["embedder"] == "HashEmbedder" and info["word_gate"] is True


def test_x4_dev_routes_off(shared, tmp_path):
    k, index = shared
    deps = build_deps(Settings(state_path=tmp_path / "s.json", dev_panel=False), knowledge=k, index=index)
    c = TestClient(create_app(deps))
    assert c.get("/dev/info").status_code == 404
    assert c.post("/dev/search", json={"query": "x"}).status_code == 404
    assert c.get("/health").json()["dev_panel"] is False


# --- X5: embedding map

def test_x5_map_has_every_chunk(client):
    m = client.get("/dev/map").json()
    assert len(m["points"]) == 1680
    assert 0 < m["explained"][1] <= m["explained"][0] < 1
    assert {p["type"] for p in m["points"]} == {"cve", "owasp_llm", "owasp_web", "atlas_technique", "atlas_case", "atlas_mitigation"}


def test_x5_query_uses_the_same_projection(shared):
    import numpy as np
    from app.rag.projection import projection_for
    _, index = shared
    proj = projection_for(index)
    c = index.chunks[42]
    text = f"{c.title}\n{c.section or ''}\n{c.text}"  # exactly what the index embedded
    assert np.allclose(proj.project(index.embedder.embed([text]))[0], proj.coords[42], atol=1e-6)


def test_x5_search_returns_query_positions(client):
    r = client.post("/dev/search", json={"query": Q5}).json()
    assert [m["query"] for m in r["map"]] == [l["query"] for l in r["lists"]]

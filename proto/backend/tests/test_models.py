"""M1–M3: provider switching, the OpenAI-compatible client against a fake server, and the model check."""
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app import evals
from app.errors import LLMError
from app.llm.openai_compat import OpenAICompatLLM, first_json_object, strip_think
from app.llm.router import LLMRouter, local_url_allowed
from app.main import create_app
from app.schemas import DevSettings


@pytest.fixture
def client(deps):
    return TestClient(create_app(deps), raise_server_exceptions=False)


def fake_server(handler):
    """An OpenAI-compatible server in memory: handler(path, body) -> (status, json)."""
    seen = []

    def respond(request: httpx.Request):
        body = json.loads(request.content or b"{}")
        seen.append((request.url.path, body))
        status, payload = handler(request.url.path, body)
        return httpx.Response(status, json=payload)
    return httpx.Client(transport=httpx.MockTransport(respond)), seen


def completion(content=None, tool_calls=None):
    return {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": content, "tool_calls": tool_calls}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}}


def local(http_client, model="qwen3"):
    return OpenAICompatLLM("local", "http://localhost:1234/v1", "local", lambda: (model, 0.2), http_client=http_client)


# --- M1: the client

def test_m1_helpers():
    assert strip_think("<think>hmm\nlong</think>\nAnswer") == "Answer"
    assert first_json_object('Sure! ```json\n{"a": {"b": 1}}\n``` done') == {"a": {"b": 1}}
    with pytest.raises(ValueError):
        first_json_object("no json here")


def test_m1_translate_falls_back_when_json_mode_is_rejected():
    def handler(path, body):
        if "response_format" in body:
            return 400, {"error": {"message": "response_format json_object not supported"}}
        return 200, completion('<think>plan it</think>{"semantic_query": "rag injection", "rewrites": ["a","b","c"], '
                               '"filters": {"product": "Langflow"}}')
    http, seen = fake_server(handler)
    llm = local(http)
    plan, reply = llm.translate("q")
    assert (plan.semantic_query, plan.rewrites, plan.filters) == ("rag injection", ["a", "b", "c"], {"product": "Langflow"})
    assert llm.json_mode is False and len(seen) == 2 and reply.input_tokens == 11
    llm.translate("again")
    assert len(seen) == 3  # remembered: no second rejected attempt


def test_m1_step_parses_tool_calls_and_strips_think():
    def handler(path, body):
        assert body["model"] == "qwen3" and body["tools"]
        return 200, completion("<think>x</think>", [{"id": "c1", "type": "function",
                               "function": {"name": "lookup_cve", "arguments": '{"cve_id": "CVE-2024-8309"}'}}])
    http, _ = fake_server(handler)
    reply = local(http).step([{"role": "user", "content": "hi"}], [{"type": "function", "function": {"name": "lookup_cve"}}])
    assert reply.content == "" and reply.tool_calls[0].name == "lookup_cve" and reply.tool_calls[0].args == {"cve_id": "CVE-2024-8309"}


def test_m1_plain_errors():
    def down(request):
        raise httpx.ConnectError("refused")
    llm = local(httpx.Client(transport=httpx.MockTransport(down)))
    with pytest.raises(LLMError) as e:
        llm.step([], [])
    assert "Is it running?" in e.value.public
    http, _ = fake_server(lambda p, b: (404, {"error": {"message": "model not found"}}))
    with pytest.raises(LLMError) as e:
        local(http).step([], [])
    assert "Load or pull it first" in e.value.public
    with pytest.raises(LLMError) as e:
        local(http, model="").step([], [])
    assert "Choose a local model" in e.value.public


# --- M1: the router and its guard rails

def test_m1_local_url_allowlist():
    hosts = ["localhost", "127.0.0.1", "::1"]
    assert local_url_allowed("http://localhost:11434/v1", hosts)
    assert local_url_allowed("http://127.0.0.1:1234/v1", hosts)
    for bad in ["http://169.254.169.254/latest", "http://localhost@evil.test/v1", "file:///etc/passwd", "http://lan-box:1234/v1"]:
        assert not local_url_allowed(bad, hosts), bad


def test_m1_router_switches_per_call(deps):
    dev = DevSettings()
    router = LLMRouter(deps.settings, lambda: dev)
    assert router.name == "fake" and router.label() == "FakeLLM (scripted)"
    dev = DevSettings(provider="local", local_model="qwen3")
    assert router.name == "local" and router.current().base_url == "http://localhost:11434/v1"
    dev = DevSettings(provider="openrouter")
    with pytest.raises(LLMError, match="no OpenRouter key"):
        router.current()


def test_m1_settings_reject_unusable_providers(client):
    s = client.get("/settings").json()["settings"]
    s["dev"]["provider"] = "openrouter"
    r = client.put("/settings", json=s)
    assert r.status_code == 400 and "OPENROUTER_API_KEY" in r.json()["error"]["message"]
    s["dev"] |= {"provider": "local", "local_base_url": "http://192.168.1.20:11434/v1"}
    r = client.put("/settings", json=s)
    assert r.status_code == 400 and "this machine" in r.json()["error"]["message"]
    s["dev"]["local_base_url"] = "http://localhost:1234/v1"
    assert client.put("/settings", json=s).status_code == 200
    assert client.get("/health").json()["llm"] == "local"


def test_m1_chat_shows_why_local_failed(client, monkeypatch):
    s = client.get("/settings").json()["settings"]
    s["dev"] |= {"provider": "local", "local_base_url": "http://localhost:9/v1", "local_model": "x"}
    client.put("/settings", json=s)
    r = client.post("/chat", json={"message": "How do I prevent prompt injection?"})
    assert r.status_code == 502 and "Is it running?" in r.json()["error"]["message"]


def test_m1_dev_models(client, monkeypatch):
    class Resp:
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def read(self): return json.dumps({"data": [{"id": "qwen3-coder"}, {"id": "gemma"}]}).encode()
    monkeypatch.setattr("urllib.request.urlopen", lambda url, timeout: Resp())
    assert client.get("/dev/models", params={"base_url": "http://localhost:1234/v1"}).json() == {"models": ["gemma", "qwen3-coder"]}
    assert client.get("/dev/models", params={"base_url": "http://10.0.0.5/v1"}).status_code == 400


# --- M2, M3: the model check

def test_m2_fakellm_passes_every_check(deps):
    run = evals.start(deps, wait=True)
    assert run["status"] == "done" and run["total"] == 11
    s = run["summary"]
    assert (s["questions"], s["passed"], s["errors"]) == (11, 11, 0), [r for r in run["results"] if not r["passed"]]
    assert s["checks_passed"] == s["checks_total"] > 30


def test_m2_does_not_touch_the_real_state(deps):
    before = deps.state.snapshot()
    evals.start(deps, wait=True)
    assert deps.state.snapshot() == before  # Q9 and Q10 wrote to a copy


def test_m2_scores_a_bad_model(deps):
    from app.llm.base import LLMReply
    from app.llm.fake import FakeLLM

    class Lazy(FakeLLM):
        """Never calls a tool, answers with a made-up citation."""
        def step(self, messages, tools):
            return LLMReply(content="Here you go [9].")
    deps.llm = Lazy()
    run = evals.start(deps, ids=["Q2", "Q7"], wait=True)
    q2, q7 = run["results"]
    assert not q2["passed"] and q2["checks"]["tools"] is False and q2["checks"]["citations_valid"] is False
    assert q7["checks"]["tools"] is True  # no tool is right for the off-topic question


def test_m3_history_and_api(client, deps):
    r = client.post("/dev/eval").json()
    assert r["status"] in ("running", "done")
    import time
    for _ in range(100):
        run = client.get(f"/dev/eval/{r['id']}").json()
        if run["status"] != "running":
            break
        time.sleep(0.05)
    assert run["summary"]["passed"] == 11
    assert client.get("/dev/evals").json()["runs"][0]["id"] == r["id"]
    assert client.get("/dev/eval/nope").status_code == 404

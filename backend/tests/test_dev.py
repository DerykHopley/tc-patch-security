"""The dev panel's API (seam 1): model switch, local-model discovery, search tuning, the playground and the embedding
map. Check ids: A11.n, from ticket #13.

No network and no key: local servers and OpenRouter are httpx.MockTransport fakes passed in as `deps.http_client`.
"""
import json
from dataclasses import replace

import httpx
import pytest
from fastapi.testclient import TestClient


def make_client(settings, knowledge, index, http_client=None):
    from app.deps import build_deps
    from app.main import create_app

    deps = build_deps(settings, knowledge=knowledge, index=index, http_client=http_client)
    return TestClient(create_app(deps), raise_server_exceptions=False), deps


def dev_body(client, **changes) -> dict:
    return client.get("/dev/settings").json()["settings"] | changes


# --- A11.5: the dev routes exist only when the dev panel is on ------------------------------------------------------

@pytest.mark.parametrize("method,path", [
    ("get", "/dev/settings"), ("put", "/dev/settings"), ("get", "/dev/info"), ("get", "/dev/models"),
    ("post", "/dev/search"), ("get", "/dev/map"),
])
def test_a11_5_dev_routes_are_404_when_the_dev_panel_is_off(settings, knowledge, index, method, path):
    off, _ = make_client(replace(settings, dev_panel=False), knowledge, index)
    r = getattr(off, method)(path, **({"json": {}} if method in ("put", "post") else {}))
    assert r.status_code == 404


def test_a11_5_saved_dev_choices_do_not_apply_when_the_dev_panel_is_off(settings, knowledge, index):
    on, _ = make_client(settings, knowledge, index)
    assert on.put("/dev/settings", json=dev_body(on, max_steps=1)).status_code == 200
    off, _ = make_client(replace(settings, dev_panel=False), knowledge, index)
    r = off.post("/chat", json={"message": "Explain CVE-2024-8309"}).json()
    assert r["steps"] > 1  # the saved max_steps=1 is ignored: the env defaults apply


# --- A11.1: model: FakeLLM, OpenRouter (only with a key) or a local server; saved and applied with no restart -------

def fake_server(handler):
    """OpenAI-compatible servers in memory: handler(request) -> (status, json, headers). Returns the client and log."""
    seen: list[httpx.Request] = []

    def respond(request: httpx.Request):
        seen.append(request)
        status, payload, *headers = handler(request)
        return httpx.Response(status, json=payload, headers=headers[0] if headers else None)
    return httpx.Client(transport=httpx.MockTransport(respond)), seen


def refusing_server():
    def refuse(request):
        raise httpx.ConnectError("connection refused", request=request)
    return httpx.Client(transport=httpx.MockTransport(refuse))


def completion(content):
    return {"id": "x", "object": "chat.completion", "created": 0, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}}


def chat_server(answer="Hello from the model."):
    def handler(request):
        if request.url.path.endswith("/models"):
            return 200, {"object": "list", "data": [{"id": "qwen3:8b"}, {"id": "llama3.2"}]}
        return 200, completion(answer)
    return fake_server(handler)


def test_a11_1_defaults_come_from_the_environment(client):
    body = client.get("/dev/settings").json()
    assert body["settings"] == {
        "provider": "fake", "openrouter_model": "openai/gpt-oss-120b", "local_url": "http://localhost:11434/v1",
        "local_model": "", "temperature": 0.2, "max_steps": 4, "top_n": 5, "per_query_k": 10, "per_doc_cap": 2,
        "rrf_k": 60, "keyword_weight": 0.5, "use_rewrites": True, "use_filters": True}
    assert body["defaults"] == body["settings"] and body["openrouter_key"] is False


def test_a11_1_switch_to_a_local_model_applies_on_the_next_call_without_a_restart(settings, knowledge, index):
    http, seen = chat_server("Local answer.")
    c, _ = make_client(settings, knowledge, index, http)
    assert c.post("/chat", json={"message": "hello"}).json()["answer"] != "Local answer."  # FakeLLM first
    r = c.put("/dev/settings", json=dev_body(c, provider="local", local_model="qwen3:8b", temperature=0.7))
    assert r.status_code == 200
    assert c.get("/health").json()["model"] == "Local · qwen3:8b"
    assert c.post("/chat", json={"message": "hello"}).json()["answer"] == "Local answer."
    sent = json.loads(seen[-1].content)
    assert (seen[-1].url.host, sent["model"], sent["temperature"]) == ("localhost", "qwen3:8b", 0.7)
    c.put("/dev/settings", json=dev_body(c, provider="fake"))  # and back, again with no restart
    assert c.post("/chat", json={"message": "hello"}).json()["answer"] != "Local answer."


def test_a11_1_openrouter_only_with_a_key(settings, knowledge, index):
    c, _ = make_client(settings, knowledge, index)
    r = c.put("/dev/settings", json=dev_body(c, provider="openrouter"))
    assert r.status_code == 400 and "OPENROUTER_API_KEY" in r.json()["error"]["message"]
    http, seen = chat_server("Hosted answer.")
    keyed, _ = make_client(replace(settings, openrouter_api_key="test-not-a-key"), knowledge, index, http)
    assert keyed.get("/dev/settings").json()["openrouter_key"] is True
    keyed.put("/dev/settings", json=dev_body(keyed, provider="openrouter", openrouter_model="anthropic/claude-haiku-5.5"))
    assert keyed.post("/chat", json={"message": "hello"}).json()["answer"] == "Hosted answer."
    assert seen[-1].url.host == "openrouter.ai" and json.loads(seen[-1].content)["model"] == "anthropic/claude-haiku-5.5"
    assert "test-not-a-key" not in json.dumps(keyed.get("/dev/settings").json())  # the key never leaves the server


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest", "http://192.168.1.20:11434/v1",
                                 "http://localhost@evil.test/v1", "file:///etc/passwd"])
def test_a11_1_a_local_url_off_this_machine_is_refused_on_save(client, url):
    r = client.put("/dev/settings", json=dev_body(client, provider="local", local_model="m", local_url=url))
    assert r.status_code == 400 and "this machine" in r.json()["error"]["message"]
    assert client.get("/dev/settings").json()["settings"]["local_url"] == "http://localhost:11434/v1"


@pytest.mark.parametrize("bad", [{"provider": "gpt"}, {"temperature": 2.5}, {"max_steps": 0}, {"max_steps": 9},
                                 {"top_n": 11}, {"per_query_k": 0}, {"per_doc_cap": 6}, {"rrf_k": 0},
                                 {"keyword_weight": 1.5}, {"local_model": "a b"}, {"openrouter_model": "no-slash"}])
def test_a11_1_bad_values_are_400(client, bad):
    r = client.put("/dev/settings", json=dev_body(client, **bad))
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


def test_a11_1_a_local_model_must_be_chosen(client):
    r = client.put("/dev/settings", json=dev_body(client, provider="local", local_model=""))
    assert r.status_code == 400 and "Choose a local model" in r.json()["error"]["message"]


def test_a11_1_find_a_local_servers_models(settings, knowledge, index):
    http, seen = chat_server()
    c, _ = make_client(settings, knowledge, index, http)
    r = c.get("/dev/models", params={"url": "http://localhost:1234/v1"})
    assert r.status_code == 200 and r.json() == {"models": ["llama3.2", "qwen3:8b"]}
    assert str(seen[-1].url) == "http://localhost:1234/v1/models"


@pytest.mark.parametrize("url", ["http://169.254.169.254/latest", "http://10.0.0.5:11434/v1",
                                 "http://localhost.evil.test/v1", "gopher://localhost/"])
def test_a11_1_model_discovery_is_limited_to_this_machine(settings, knowledge, index, url):
    http, seen = chat_server()
    c, _ = make_client(settings, knowledge, index, http)
    r = c.get("/dev/models", params={"url": url})
    assert r.status_code == 400 and "this machine" in r.json()["error"]["message"]
    assert seen == []  # no request left the server


def test_a11_1_model_discovery_does_not_follow_a_redirect_off_the_machine(settings, knowledge, index):
    http, seen = fake_server(lambda req: (302, {}, {"Location": "http://169.254.169.254/latest/meta-data"})
                             if req.url.host == "localhost" else (200, {"data": [{"id": "leaked"}]}))
    c, _ = make_client(settings, knowledge, index, http)
    r = c.get("/dev/models", params={"url": "http://localhost:11434/v1"})
    assert r.status_code == 502 and [q.url.host for q in seen] == ["localhost"]


def test_a11_1_model_discovery_says_plainly_when_nothing_is_running(settings, knowledge, index):
    c, _ = make_client(settings, knowledge, index, refusing_server())
    r = c.get("/dev/models", params={"url": "http://localhost:11434/v1"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "unreachable"
    assert "Nothing answered at http://localhost:11434/v1" in r.json()["error"]["message"]


def test_a11_1_a_local_model_that_is_not_running_gives_a_plain_chat_error(settings, knowledge, index):
    c, _ = make_client(settings, knowledge, index, refusing_server())
    c.put("/dev/settings", json=dev_body(c, provider="local", local_model="qwen3:8b"))
    r = c.post("/chat", json={"message": "hello"})
    assert r.status_code == 502 and "Is it running?" in r.json()["error"]["message"]


def test_a11_1_max_steps_applies_to_the_next_chat(client):
    client.put("/dev/settings", json=dev_body(client, max_steps=1))
    r = client.post("/chat", json={"message": "Explain CVE-2024-8309"}).json()
    assert r["steps"] == 1 and "I stopped after 1 steps" in r["answer"]

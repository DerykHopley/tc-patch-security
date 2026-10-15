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
    ("post", "/dev/search"), ("get", "/dev/map"), ("get", "/dev/openrouter-models"),
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
        "provider": "fake", "openrouter_model": "anthropic/claude-haiku-5.5", "local_url": "http://localhost:11434/v1",
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


def test_a11_1_saved_choices_survive_a_restart_and_reset_clears_them(settings, knowledge, index):
    c, _ = make_client(settings, knowledge, index)
    c.put("/dev/settings", json=dev_body(c, rrf_k=30, temperature=1.1))
    again, _ = make_client(settings, knowledge, index)
    assert (again.get("/dev/settings").json()["settings"]["rrf_k"],
            again.get("/settings").json()["settings"]["alerts"]["min_severity"]) == (30, "HIGH")  # parts kept apart
    again.post("/state/reset", json={"confirm": "reset"})
    assert again.get("/dev/settings").json()["settings"]["rrf_k"] == 60


def test_a11_1_max_steps_applies_to_the_next_chat(client):
    client.put("/dev/settings", json=dev_body(client, max_steps=1))
    r = client.post("/chat", json={"message": "Explain CVE-2024-8309"}).json()
    assert r["steps"] == 1 and "I stopped after 1 steps" in r["answer"]


# --- A11.2: search tuning: the chat's search_security uses the saved values -----------------------------------------

Q1 = "Which critical Langflow vulnerabilities were published in 2026?"
Q5 = "How do I protect a RAG app from indirect prompt injection?"


def chat_query(client, message):
    r = client.post("/chat", json={"message": message}).json()
    return r["query"], r["sources"]


def test_a11_2_top_n_and_rewrites_apply_to_the_chat(client):
    query, sources = chat_query(client, Q5)
    assert len(query["rewrites"]) == 3 and len(sources) == 5  # the spec's defaults
    client.put("/dev/settings", json=dev_body(client, top_n=2, use_rewrites=False))
    query, sources = chat_query(client, Q5)
    assert query["rewrites"] == [] and len(sources) == 2


def test_a11_2_filters_off_are_listed_as_dropped(client):
    query, _ = chat_query(client, Q1)
    assert query["filters"]["product"] == "langflow" and query["dropped_filters"] == []
    client.put("/dev/settings", json=dev_body(client, use_filters=False))
    query, _ = chat_query(client, Q1)
    assert query["filters"] == {}
    assert "product=langflow (filters off)" in query["dropped_filters"]


def test_a11_2_per_document_cap_applies(client):
    client.put("/dev/settings", json=dev_body(client, per_doc_cap=1, top_n=10))
    _, sources = chat_query(client, Q5)
    docs = [s["doc_id"] for s in sources]
    assert len(docs) == len(set(docs))  # at most one chunk per document


@pytest.mark.parametrize("weight,found_by", [(0, {"vector"}), (1, {"keyword"})])
def test_a11_2_keyword_weight_at_either_end_uses_one_retriever(client, weight, found_by):
    client.put("/dev/settings", json=dev_body(client, keyword_weight=weight))
    query, sources = chat_query(client, Q5)
    assert sources and {r for rs in query["found_by"].values() for r in rs} == found_by


# --- A11.3: the playground: plan, each BM25 and vector list per query, the fused ranking, the final sources ----------

def test_a11_3_playground_shows_every_step(client):
    r = client.post("/dev/search", json={"query": Q5})
    assert r.status_code == 200
    body = r.json()
    plan = body["query"]
    assert plan["semantic_query"] == "protect RAG application from indirect prompt injection"
    queries = [plan["semantic_query"], *plan["rewrites"]]
    # Each query on each retriever, before fusion: BM25 and vector lists shown separately.
    assert [(l["retriever"], l["query"]) for l in body["lists"]] == [
        (ret, q) for q in queries for ret in ("vector", "keyword")]
    for l in body["lists"]:
        assert 0 < len(l["hits"]) <= 10
        assert set(l["hits"][0]) == {"chunk_id", "title", "doc_type", "score"}
    fused = [f["rrf"] for f in body["fused"]]
    assert fused == sorted(fused, reverse=True) and len(fused) <= 15
    listed = {h["chunk_id"] for l in body["lists"] for h in l["hits"]}
    assert {f["chunk_id"] for f in body["fused"]} <= listed
    # The final sources are what the chat would cite for the same question.
    _, chat_sources = chat_query(client, Q5)
    assert [s["chunk_id"] for s in body["final"]] == [s["chunk_id"] for s in chat_sources]
    assert body["options"]["rrf_k"] == 60


def test_a11_3_playground_uses_the_saved_settings(client):
    client.put("/dev/settings", json=dev_body(client, keyword_weight=0, use_rewrites=False, per_query_k=3, top_n=2))
    body = client.post("/dev/search", json={"query": Q5}).json()
    assert [l["retriever"] for l in body["lists"]] == ["vector"]  # rewrites off, keyword side not run
    assert len(body["lists"][0]["hits"]) <= 3 and len(body["final"]) == 2
    assert body["options"]["keyword_weight"] == 0


def test_a11_3_playground_lists_filters_and_dropped_filters(client):
    client.put("/dev/settings", json=dev_body(client, use_filters=False))
    plan = client.post("/dev/search", json={"query": Q1}).json()["query"]
    assert plan["filters"] == {} and "severity_min=CRITICAL (filters off)" in plan["dropped_filters"]


@pytest.mark.parametrize("bad", [{"query": ""}, {"query": "x" * 501}, {}])
def test_a11_3_playground_query_is_validated(client, bad):
    assert client.post("/dev/search", json=bad).status_code == 400


# --- A11.4: the embedding map: PCA of the vectors stored in the Chroma index -----------------------------------------

class CountingEmbedder:
    """Wraps the index's embedder and records how many texts each call embeds."""

    def __init__(self, inner):
        self.inner, self.name, self.min_score, self.calls = inner, inner.name, inner.min_score, []

    def embed(self, texts):
        self.calls.append(len(texts))
        return self.inner.embed(texts)


def test_a11_4_index_facts(client, index):
    info = client.get("/dev/info").json()
    assert info["chunks"] == len(index.chunks) and sum(info["by_doc_type"].values()) == len(index.chunks)
    assert (info["embedder"], info["dim"], info["as_of"]) == (index.embedder_name, index.dim, "2026-10-13")
    assert info["min_score"] == index.min_score and info["local_hosts"] == ["localhost", "127.0.0.1", "::1"]


def test_a11_4_map_has_a_point_for_every_chunk_by_group(client, index):
    body = client.get("/dev/map").json()
    points = body["points"]
    assert [p["id"] for p in points] == [c.chunk_id for c in index.chunks]
    assert set(points[0]) == {"id", "doc_id", "title", "type", "x", "y"}
    assert {p["type"] for p in points} == {"owasp_llm", "owasp_web", "atlas_technique", "atlas_mitigation",
                                           "atlas_case", "cve"}
    assert len(body["explained"]) == 2 and 0 < body["explained"][1] <= body["explained"][0] < 1
    assert body["embedder"] == index.embedder_name and body["dim"] == index.dim


def test_a11_4_map_reads_the_stored_vectors_and_embeds_nothing(client, index, monkeypatch):
    counting = CountingEmbedder(index.embedder)
    monkeypatch.setattr(index, "embedder", counting)
    from app.dev import projection_for
    projection_for.cache_clear()
    assert client.get("/dev/map").status_code == 200
    assert counting.calls == []  # with a real embedder, re-embedding 1,680 chunks would cost money


def test_a11_4_a_query_lands_where_its_own_text_does(client, index):
    """The playground places each query by the same projection as the chunks: a query whose text is a chunk's own
    indexed text lands on that chunk's point."""
    from app.rag.vector import index_text

    chunk = next(c for c in index.chunks if c.doc_type == "atlas_technique" and len(index_text(c)) <= 500)
    points = {p["id"]: p for p in client.get("/dev/map").json()["points"]}
    body = client.post("/dev/search", json={"query": index_text(chunk)}).json()
    q = body["map"][0]
    assert q["query"] == index_text(chunk)  # unscripted: FakeLLM searches the question as is
    assert (q["x"], q["y"]) == pytest.approx((points[chunk.chunk_id]["x"], points[chunk.chunk_id]["y"]), abs=1e-3)


def test_a11_4_playground_places_the_query_and_every_rewrite(client):
    body = client.post("/dev/search", json={"query": Q5}).json()
    assert [m["query"] for m in body["map"]] == [body["query"]["semantic_query"], *body["query"]["rewrites"]]
    assert all(isinstance(m["x"], float) and isinstance(m["y"], float) for m in body["map"])


# --- A11.10: the OpenRouter models this key may use, for the Dev page's dropdown -------------------------------------

KEY = "sk-or-test-not-a-real-key"


def or_model(id_, prompt="0.000001", completion="0.000005", tools=True, context=200000, name=None):
    """One entry of OpenRouter's GET /models/user: prices are USD per token, as strings."""
    return {"id": id_, "name": name or id_, "context_length": context,
            "pricing": {"prompt": prompt, "completion": completion},
            "supported_parameters": ["temperature", "tools"] if tools else ["temperature"]}


def openrouter(models=None, status=200):
    """OpenRouter's model list in memory. Returns the client and the requests it saw."""
    def handler(request):
        if request.url.path != "/api/v1/models/user":
            return 404, {}
        return (200, {"data": models or []}) if status == 200 else (status, {"error": {"message": "nope"}})
    return fake_server(handler)


def keyed_client(settings, knowledge, index, http):
    return make_client(replace(settings, openrouter_api_key=KEY), knowledge, index, http)


def test_a11_10_lists_tool_capable_models_with_prices_per_million_sorted_by_input_price(settings, knowledge, index):
    http, seen = openrouter([
        or_model("openai/gpt-5-mini", "0.00000025", "0.000002", name="OpenAI: GPT-5 mini", context=400000),
        or_model("anthropic/claude-haiku-5.5", "0.000001", "0.000005", name="Anthropic: Claude Haiku 5.5"),
        or_model("some/no-tools", "0", "0", tools=False),
        or_model("google/gemini-flash", "0.0000001", "0.0000004", context=1048576),
    ])
    c, _ = keyed_client(settings, knowledge, index, http)
    body = c.get("/dev/openrouter-models").json()
    assert body["reason"] is None
    assert [m["id"] for m in body["models"]] == ["google/gemini-flash", "openai/gpt-5-mini",
                                                 "anthropic/claude-haiku-5.5"]
    assert body["models"][1] == {"id": "openai/gpt-5-mini", "name": "OpenAI: GPT-5 mini", "input_per_m": 0.25,
                                 "output_per_m": 2.0, "context_length": 400000, "check": None}
    assert str(seen[0].url) == "https://openrouter.ai/api/v1/models/user"
    assert seen[0].headers["authorization"] == f"Bearer {KEY}"  # the key goes to OpenRouter...
    assert KEY not in c.get("/dev/openrouter-models").text  # ...and never back to the browser


def test_a11_10_a_variable_price_is_unknown_and_sorts_last(settings, knowledge, index):
    http, _ = openrouter([or_model("openrouter/auto", "-1", "-1"), or_model("cheap/one", "0.0000002", "0.0000008")])
    c, _ = keyed_client(settings, knowledge, index, http)
    models = c.get("/dev/openrouter-models").json()["models"]
    assert [m["id"] for m in models] == ["cheap/one", "openrouter/auto"]
    assert models[0]["input_per_m"] == 0.2 and models[0]["output_per_m"] == 0.8
    assert models[1]["input_per_m"] is None and models[1]["output_per_m"] is None


def test_a11_10_no_key_is_an_empty_list_with_a_plain_reason_and_no_call(settings, knowledge, index):
    http, seen = openrouter([or_model("a/b")])
    c, _ = make_client(settings, knowledge, index, http)
    r = c.get("/dev/openrouter-models")
    assert r.status_code == 200
    assert r.json() == {"models": [], "reason": "no OpenRouter key in backend/.env"}
    assert seen == []


@pytest.mark.parametrize("status", [401, 500])
def test_a11_10_an_openrouter_error_is_an_empty_list_with_a_plain_reason(settings, knowledge, index, status, caplog):
    http, _ = openrouter(status=status)
    c, _ = keyed_client(settings, knowledge, index, http)
    r = c.get("/dev/openrouter-models")
    assert r.status_code == 200 and r.json()["models"] == []
    assert f"OpenRouter answered {status}" in r.json()["reason"]
    assert KEY not in r.text and KEY not in caplog.text


def test_a11_10_openrouter_unreachable_is_an_empty_list_with_a_plain_reason(settings, knowledge, index, caplog):
    c, _ = keyed_client(settings, knowledge, index, refusing_server())
    r = c.get("/dev/openrouter-models")
    assert r.json()["models"] == [] and "Can't reach OpenRouter" in r.json()["reason"]
    assert KEY not in r.text and KEY not in caplog.text


def test_a11_10_the_list_is_cached_for_an_hour(settings, knowledge, index, monkeypatch):
    from app import openrouter_models

    http, seen = openrouter([or_model("a/b")])
    c, _ = keyed_client(settings, knowledge, index, http)
    first, second = c.get("/dev/openrouter-models").json(), c.get("/dev/openrouter-models").json()
    assert first == second and len(seen) == 1  # the second ask is served from memory
    monkeypatch.setattr(openrouter_models, "CACHE_SECONDS", 0)  # an hour later
    c.get("/dev/openrouter-models")
    assert len(seen) == 2


def test_a11_10_a_failure_is_not_cached(settings, knowledge, index):
    answers = iter([500, 200])

    def handler(request):
        status = next(answers)
        return (status, {"data": [or_model("a/b")]}) if status == 200 else (status, {})
    http, seen = fake_server(handler)
    c, _ = keyed_client(settings, knowledge, index, http)
    assert c.get("/dev/openrouter-models").json()["models"] == []
    assert [m["id"] for m in c.get("/dev/openrouter-models").json()["models"]] == ["a/b"]  # tried again


def saved_run(store, run_id, model, passed, questions=14, status="done", provider="openrouter"):
    """A model-check run as model_check saves it (only the fields the dropdown reads differ)."""
    label = f"OpenRouter · {model}" if provider == "openrouter" else f"Local · {model}"
    store.save("models", {"id": run_id, "kind": "model", "status": status, "model": label, "provider": provider,
                          "settings": {"provider": provider, "openrouter_model": model},
                          "summary": {"questions": questions, "passed": passed}})


def test_a11_10_each_model_shows_its_latest_model_check_score(settings, knowledge, index):
    from app.evals.runs import RunStore

    store = RunStore.for_settings(settings)
    saved_run(store, "20261014-100000-000-aaaa", "anthropic/claude-haiku-5.5", 10)
    saved_run(store, "20261015-100000-000-bbbb", "anthropic/claude-haiku-5.5", 12)  # the latest counts
    saved_run(store, "20261015-110000-000-cccc", "anthropic/claude-haiku-5.5", 1, status="failed")  # not finished
    saved_run(store, "20261015-120000-000-dddd", "openai/gpt-5-mini", 3, provider="local")  # a local model, same name
    http, _ = openrouter([or_model("anthropic/claude-haiku-5.5"), or_model("openai/gpt-5-mini")])
    c, _ = keyed_client(settings, knowledge, index, http)
    checks = {m["id"]: m["check"] for m in c.get("/dev/openrouter-models").json()["models"]}
    assert checks == {"anthropic/claude-haiku-5.5": {"passed": 12, "total": 14, "run": "20261015-100000-000-bbbb"},
                      "openai/gpt-5-mini": None}


def test_a11_10_a_new_model_check_shows_without_waiting_for_the_cache(settings, knowledge, index):
    from app.evals.runs import RunStore

    http, seen = openrouter([or_model("anthropic/claude-haiku-5.5")])
    c, _ = keyed_client(settings, knowledge, index, http)
    assert c.get("/dev/openrouter-models").json()["models"][0]["check"] is None
    saved_run(RunStore.for_settings(settings), "20261015-100000-000-bbbb", "anthropic/claude-haiku-5.5", 13)
    assert c.get("/dev/openrouter-models").json()["models"][0]["check"]["passed"] == 13
    assert len(seen) == 1  # the list came from memory; the scores were read fresh

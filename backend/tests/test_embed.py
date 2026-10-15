"""The Embedder seam. The hash embedder moved from proto (old ids kept in the names); the real embedders
are checked against a fake HTTP server: no network, no key. Check ids: A06.1, A09.2, A09.4."""
import json

import httpx
import numpy as np
import pytest

from app.config import ConfigError, Settings
from app.rag.embed import HashEmbedder, make_embedder


def test_a06_1_r2_same_text_same_vector():
    e = HashEmbedder()
    a = e.embed(["open-weight models are here"])
    b = HashEmbedder().embed(["open-weight models are here"])
    assert np.array_equal(a, b)


def test_a06_1_r2_vectors_are_unit_length():
    v = HashEmbedder().embed(["chips and memory bandwidth", "agents in production"])
    assert np.allclose(np.linalg.norm(v, axis=1), 1.0)


def test_a06_1_r2_shared_words_give_higher_cosine():
    v = HashEmbedder().embed(["open-weight model release", "open-weight model licence", "data centre energy"])
    assert v[0] @ v[1] > v[0] @ v[2]


def test_a06_1_r2_empty_text_is_zero_vector_not_nan():
    v = HashEmbedder().embed(["the a of"])
    assert not np.isnan(v).any()


def fake_server(seen: list) -> httpx.Client:
    """An OpenAI-compatible /embeddings endpoint in memory. Records each request."""
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append((str(request.url), request.headers.get("authorization"), body))
        data = [{"object": "embedding", "index": i, "embedding": [3.0, 4.0, 0.0]} for i, _ in enumerate(body["input"])]
        return httpx.Response(200, json={"object": "list", "data": data, "model": body["model"],
                                         "usage": {"prompt_tokens": 1, "total_tokens": 1}})
    return httpx.Client(transport=httpx.MockTransport(handle))


def test_a09_2_openrouter_embedder_sends_text_not_tokens():
    seen: list = []
    e = make_embedder(Settings(embedder="openrouter", openrouter_api_key="test-placeholder"),
                      http_client=fake_server(seen))
    v = e.embed(["CVE-2024-8309 in LangChain", "prompt injection"])
    url, auth, body = seen[0]
    assert url == "https://openrouter.ai/api/v1/embeddings"
    assert auth == "Bearer test-placeholder"
    assert body["model"] == "openai/text-embedding-3-small"
    # Token-length checking off: OpenRouter gets the strings, not tiktoken ids.
    assert body["input"] == ["CVE-2024-8309 in LangChain", "prompt injection"]
    assert v.shape == (2, 3) and np.allclose(np.linalg.norm(v, axis=1), 1.0)
    assert e.name == "openrouter/openai/text-embedding-3-small"


def test_a09_2_ollama_embedder_is_a_second_implementation():
    seen: list = []
    e = make_embedder(Settings(embedder="ollama", embed_model="nomic-embed-text"), http_client=fake_server(seen))
    e.embed(["prompt injection"])
    url, _, body = seen[0]
    assert url == "http://localhost:11434/v1/embeddings"
    assert (body["model"], body["input"]) == ("nomic-embed-text", ["prompt injection"])
    assert e.name == "ollama/nomic-embed-text"


@pytest.mark.parametrize("embedder,model,score", [
    ("openrouter", "", 0.35),
    ("ollama", "", 0.58),  # mxbai-embed-large, the Ollama default since A20
    ("ollama", "qwen3-embedding:0.6b", 0.55),
    ("ollama", "mxbai-embed-large", 0.58),
    ("ollama", "mxbai-embed-large:latest", 0.58),  # Ollama's implicit tag
    ("ollama", "some-other-embedder", 0.58),  # untuned: the provider's default
])
def test_a20_thresholds_tuned_per_model(embedder, model, score):
    e = make_embedder(Settings(embedder=embedder, embed_model=model, openrouter_api_key="k"),
                      http_client=fake_server([]))
    assert e.min_score == score


def test_a20_ollama_embedder_defaults_to_mxbai_embed_large():
    """Picked in A20 (2026-10-15): tied best hit rate, widest gap between on- and off-topic scores."""
    assert make_embedder(Settings(embedder="ollama"), http_client=fake_server([])).name == "ollama/mxbai-embed-large"


def test_a09_2_hash_embedder_is_the_default():
    assert make_embedder(Settings()).name == "hash-4096"


def test_a09_2_openrouter_embedder_needs_a_key():
    with pytest.raises(ConfigError, match="OPENROUTER_API_KEY"):
        Settings(embedder="openrouter").check()


def test_a09_2_unknown_embedder_is_a_plain_error():
    with pytest.raises(ConfigError, match="EMBEDDER must be one of hash, openrouter, ollama"):
        Settings(embedder="word2vec").check()


def test_a09_2_ollama_url_must_be_on_this_machine():
    with pytest.raises(ConfigError, match="OLLAMA_URL"):
        Settings(embedder="ollama", ollama_url="http://example.com:11434").check()
    Settings(embedder="ollama", ollama_url="http://127.0.0.1:11434").check()


def test_a09_2_embedder_settings_from_environment(monkeypatch):
    monkeypatch.setenv("EMBEDDER", " OpenRouter ")
    monkeypatch.setenv("EMBED_MODEL", "openai/text-embedding-3-large")
    monkeypatch.setenv("SEARCH_MIN_SCORE", "0.3")
    s = Settings.from_env()
    assert (s.embedder, s.embed_model, s.search_min_score) == ("openrouter", "openai/text-embedding-3-large", 0.3)


def test_a09_4_bad_threshold_is_a_plain_error(monkeypatch):
    monkeypatch.setenv("SEARCH_MIN_SCORE", "high")
    with pytest.raises(ConfigError, match="SEARCH_MIN_SCORE"):
        Settings.from_env()

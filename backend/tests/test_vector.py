"""The Chroma index: built by a script, loaded at start-up, guarded against a different embedder. Check ids: A09.1."""
import numpy as np
import pytest

from app.config import ConfigError, Settings
from app.rag.chunking import build_chunks
from app.rag.embed import HashEmbedder
from app.rag.vector import build_index, open_index


class CountingEmbedder(HashEmbedder):
    """The hash embedder that counts how many texts it embedded."""

    def __init__(self, dim: int = 4096, name: str | None = None):
        super().__init__(dim)
        self.texts = 0
        if name:
            self.name = name

    def embed(self, texts):
        self.texts += len(texts)
        return super().embed(texts)


@pytest.fixture(scope="module")
def small(knowledge):
    """A small slice of the snapshot: building the full index once per run is enough."""
    return build_chunks(knowledge)[:40]


def test_a09_1_open_loads_without_embedding_chunks_again(small, tmp_path):
    build_index(small, HashEmbedder(), tmp_path)
    e = CountingEmbedder()
    index = open_index(tmp_path, e, small)
    assert e.texts == 0
    hits = index.search(small[0].text, k=1, min_score=0.0)
    assert hits[0].chunk.chunk_id == small[0].chunk_id
    assert e.texts == 1  # only the query


def test_a09_1_index_records_model_and_dimension(small, tmp_path):
    index = build_index(small, HashEmbedder(dim=512), tmp_path)
    assert (index.embedder_name, index.dim) == ("hash-512", 512)
    reopened = open_index(tmp_path, HashEmbedder(dim=512), small)
    assert (reopened.embedder_name, reopened.dim) == ("hash-512", 512)


def test_a09_1_different_embedder_is_a_plain_error(small, tmp_path):
    build_index(small, HashEmbedder(dim=512), tmp_path)
    with pytest.raises(ConfigError, match="built with hash-512.*EMBEDDER is hash-4096.*build_index"):
        open_index(tmp_path, HashEmbedder(dim=4096), small)


def test_a09_1_same_name_different_dimension_is_a_plain_error(small, tmp_path):
    build_index(small, HashEmbedder(dim=512), tmp_path)
    with pytest.raises(ConfigError, match="512 dimensions.*256"):
        open_index(tmp_path, CountingEmbedder(dim=256, name="hash-512"), small)


def test_a09_1_missing_index_says_how_to_build_it(small, tmp_path):
    with pytest.raises(ConfigError, match="No search index.*build_index"):
        open_index(tmp_path / "none", HashEmbedder(), small)


def test_a09_1_index_from_other_data_must_be_rebuilt(small, tmp_path):
    build_index(small, HashEmbedder(), tmp_path)
    with pytest.raises(ConfigError, match="different data.*build_index"):
        open_index(tmp_path, HashEmbedder(), small[:-1])


def test_a09_1_rebuild_replaces_the_collection(small, tmp_path):
    build_index(small, HashEmbedder(dim=512), tmp_path)
    index = build_index(small[:10], HashEmbedder(), tmp_path)
    assert index.embedder_name == "hash-4096"
    assert len(index.search(small[0].text, k=50, min_score=0.0)) == 10


def test_a09_1_build_script_writes_the_index_the_app_loads(knowledge, tmp_path, monkeypatch):
    from app.deps import build_deps
    from app.rag import build_index as script

    monkeypatch.setenv("EMBEDDER", "hash")
    monkeypatch.setenv("INDEX_PATH", str(tmp_path / "idx"))
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    assert script.main([]) == 0
    deps = build_deps(Settings.from_env(), knowledge=knowledge)
    assert deps.index.embedder_name == "hash-4096"
    assert deps.index.search("indirect prompt injection", k=3)


def test_a09_1_a_stale_free_hash_index_rebuilds_itself(knowledge, tmp_path, caplog):
    """Review item 12: the hash index costs nothing, so other data (a new snapshot) or another hash size is
    rebuilt at start-up, with a log line, instead of refusing to start."""
    from app.deps import build_deps

    for stale_embedder in (HashEmbedder(), HashEmbedder(dim=512)):  # other data; other data and another size
        build_index(build_chunks(knowledge)[:5], stale_embedder, tmp_path / "idx")
        s = Settings(state_path=tmp_path / "state.json", index_path=tmp_path / "idx")
        with caplog.at_level("WARNING"):
            index = build_deps(s, knowledge=knowledge).index
        assert index.embedder_name == "hash-4096"
        assert len(index.search("indirect prompt injection", k=50, min_score=0.0)) == 50  # the full snapshot
        assert "Rebuilding the free hash search index" in caplog.text
        caplog.clear()


def test_a09_1_a_paid_index_is_never_rebuilt_at_start_up(knowledge, tmp_path):
    """A real embedder's index costs money: a mismatch stays a plain error, and the index is left as it is."""
    from app.deps import build_deps

    build_index(build_chunks(knowledge)[:5], CountingEmbedder(name="openrouter/some-model"), tmp_path / "idx")
    s = Settings(state_path=tmp_path / "state.json", index_path=tmp_path / "idx")
    with pytest.raises(ConfigError, match="built with openrouter/some-model.*costs money"):
        build_deps(s, knowledge=knowledge)
    still = open_index(tmp_path / "idx", CountingEmbedder(name="openrouter/some-model"), build_chunks(knowledge)[:5])
    assert still.embedder_name == "openrouter/some-model"


def test_a09_1_hash_index_is_built_once_when_missing(knowledge, tmp_path):
    # The hash embedder costs nothing, so a fresh checkout (and CI) starts without running the script.
    from app.deps import build_deps

    s = Settings(state_path=tmp_path / "state.json", index_path=tmp_path / "idx")
    first = build_deps(s, knowledge=knowledge).index
    assert (tmp_path / "idx").exists() and first.embedder_name == "hash-4096"


def test_a09_1_real_embedder_never_builds_at_start_up(knowledge, tmp_path):
    from app.deps import build_deps

    s = Settings(state_path=tmp_path / "state.json", index_path=tmp_path / "idx", embedder="openrouter",
                 openrouter_api_key="test-placeholder")
    with pytest.raises(ConfigError, match="No search index"):
        build_deps(s, knowledge=knowledge)


def test_a09_1_hits_carry_cosine_similarity(small, tmp_path):
    index = build_index(small, HashEmbedder(), tmp_path)
    hit = index.search(small[0].text, k=1, min_score=0.0)[0]
    assert 0.5 < hit.score <= 1.0 + 1e-6 and not np.isnan(hit.score)

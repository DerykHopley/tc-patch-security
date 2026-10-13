import pytest


@pytest.fixture(scope="session")
def shared():
    """The snapshot and its index, built once per test run (about 0.1 s)."""
    from app.knowledge import load_knowledge
    from app.rag.chunking import build_chunks
    from app.rag.embed import HashEmbedder
    from app.rag.index import VectorIndex

    k = load_knowledge()
    return k, VectorIndex(build_chunks(k), HashEmbedder())


@pytest.fixture
def deps(tmp_path, shared):
    """Real fixtures, FakeLLM, HashEmbedder, state in a temp folder."""
    from app.config import Settings
    from app.deps import build_deps

    k, index = shared
    return build_deps(Settings(llm_provider="fake", state_path=tmp_path / "state.json"), knowledge=k, index=index)

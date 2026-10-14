import pytest


@pytest.fixture(scope="session")
def knowledge():
    """The snapshot, loaded once per test run."""
    from app.knowledge import load_knowledge

    return load_knowledge()


@pytest.fixture(scope="session")
def index(knowledge):
    """The in-memory index over the snapshot with the hash embedder (the test fake), built once per run."""
    from app.rag.chunking import build_chunks
    from app.rag.embed import HashEmbedder
    from app.rag.index import VectorIndex

    return VectorIndex(build_chunks(knowledge), HashEmbedder())


@pytest.fixture(scope="session")
def shared(knowledge, index):
    return knowledge, index


@pytest.fixture
def settings(tmp_path):
    """FakeLLM, state in a temp folder per test."""
    from app.config import Settings

    return Settings(llm_provider="fake", state_path=tmp_path / "state.json")


@pytest.fixture
def deps(settings, knowledge, index):
    from app.deps import build_deps

    return build_deps(settings, knowledge=knowledge, index=index)


@pytest.fixture
def client(deps):
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(deps), raise_server_exceptions=False)

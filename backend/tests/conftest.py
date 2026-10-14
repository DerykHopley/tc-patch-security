import pytest


@pytest.fixture(scope="session")
def knowledge():
    """The snapshot, loaded once per test run."""
    from app.knowledge import load_knowledge

    return load_knowledge()


@pytest.fixture(scope="session")
def index_dir(tmp_path_factory):
    return tmp_path_factory.mktemp("chroma")


@pytest.fixture(scope="session")
def index(knowledge, index_dir):
    """Real Chroma in a temp folder, over the snapshot, with hash vectors (the test fake). Built once per run."""
    from app.rag.chunking import build_chunks
    from app.rag.embed import HashEmbedder
    from app.rag.vector import build_index

    return build_index(build_chunks(knowledge), HashEmbedder(), index_dir)


@pytest.fixture(scope="session")
def shared(knowledge, index):
    return knowledge, index


@pytest.fixture
def settings(tmp_path, index_dir, index):
    """FakeLLM, state in a temp folder per test, the run's hash index (never backend/data)."""
    from app.config import Settings

    return Settings(llm_provider="fake", state_path=tmp_path / "state.json", index_path=index_dir)


@pytest.fixture
def deps(settings, knowledge, index):
    from app.deps import build_deps

    return build_deps(settings, knowledge=knowledge, index=index)


@pytest.fixture
def client(deps):
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(deps), raise_server_exceptions=False)

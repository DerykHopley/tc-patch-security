import pytest


@pytest.fixture(scope="session")
def knowledge():
    """The snapshot, loaded once per test run."""
    from app.knowledge import load_knowledge

    return load_knowledge()


@pytest.fixture
def settings(tmp_path):
    """FakeLLM, state in a temp folder per test."""
    from app.config import Settings

    return Settings(llm_provider="fake", state_path=tmp_path / "state.json")


@pytest.fixture
def deps(settings, knowledge):
    from app.deps import build_deps

    return build_deps(settings, knowledge=knowledge)


@pytest.fixture
def client(deps):
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(deps), raise_server_exceptions=False)

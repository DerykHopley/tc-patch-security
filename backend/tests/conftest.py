import pytest


@pytest.fixture(autouse=True)
def no_real_alerts(monkeypatch):
    """No test ever sends a real alert (B04: a refresh sends alerts). Settings from the environment record only,
    and the default transports find no desktop command. Tests that check a channel pass fake transports."""
    monkeypatch.setenv("NOTIFY_DRY_RUN", "1")
    monkeypatch.setattr("app.notify.desktop_command", lambda: None)


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


class Given:
    """Seeds state through State's own methods, so a test never writes the state file's JSON by hand. Each step
    returns the builder: `given.watching("langflow").decided(cve, "fixed")`. Hand-written JSON stays only in the
    tests of old state files loading."""

    def __init__(self, state):
        self.state = state

    def watching(self, *products: str, **fields: dict) -> "Given":
        """Exactly these products; `fields` by product: its usage, version, internet_facing."""
        self.state.set_watchlist(list(products), fields)
        return self

    def decided(self, cve_id: str, status: str, as_of: str | None = None, **record) -> "Given":
        """Your decision, as the CVEs page would save it on `as_of` (an earlier date makes a review date due)."""
        self.state.set_status(cve_id, status, as_of, **record)
        return self

    def settings(self, **parts: dict) -> "Given":
        """Change some settings: settings(alerts={"min_severity": "LOW"}). The rest keep what's saved."""
        from app.app_settings import AppSettings

        merged = self.state.settings().model_dump()
        for part, values in parts.items():
            merged[part] = merged[part] | values if isinstance(values, dict) else values
        self.state.save_settings(AppSettings.model_validate(merged))
        return self

    def alerted(self, entry: dict) -> "Given":
        self.state.log_alert(entry)
        return self


@pytest.fixture
def given(deps):
    return Given(deps.state)


@pytest.fixture
def client(deps):
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(deps), raise_server_exceptions=False)

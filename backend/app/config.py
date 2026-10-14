"""Settings from environment variables. Every one is listed in .env.example.

Plain dataclass and os.environ: no extra dependency, and tests build Settings directly.
Load a .env file with `uv run --env-file .env ...`.
"""
import json
import os
import pathlib
from dataclasses import dataclass, field
from urllib.parse import urlparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"  # the snapshot's folder

DEFAULT_WATCHLIST = ["langchain", "langflow", "litellm", "ollama", "open-webui"]
DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
PROVIDERS = ("fake",)  # openrouter and local arrive with the real model (A08)
EMBEDDERS = ("hash", "openrouter", "ollama")  # hash: the free test fake; the other two need the index built (A09)
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")


def snapshot_date() -> str:
    return json.loads((FIXTURES / "manifest.json").read_text())["as_of"]


def _flag(value: str, default: bool) -> bool:
    value = value.strip().lower()
    return default if not value else value in ("1", "true", "yes", "on")


class ConfigError(RuntimeError):
    pass


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, "").strip() or default


def _int(name: str, default: int) -> int:
    value = _env(name)
    try:
        return int(value) if value else default
    except ValueError:
        raise ConfigError(f"{name} must be a whole number, not {value!r}.") from None


def _float(name: str) -> float | None:
    value = _env(name)
    try:
        return float(value) if value else None
    except ValueError:
        raise ConfigError(f"{name} must be a number like 0.3, not {value!r}.") from None


def _path(name: str, default: pathlib.Path) -> pathlib.Path:
    """Relative paths are under backend/."""
    path = pathlib.Path(_env(name) or default)
    return path if path.is_absolute() else ROOT / path


def _list(value: str) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class Settings:
    llm_provider: str = "fake"
    state_path: pathlib.Path = ROOT / "data" / "state.json"
    as_of: str = field(default_factory=snapshot_date)
    cors_origins: list[str] = field(default_factory=lambda: _list(DEFAULT_CORS))
    dev_panel: bool = True  # the Dev page (and later its routes) exist only when this is on
    # Alert channels (Settings page, A13). Secrets live here only: never in the state file or an API reply.
    app_url: str = "http://localhost:5173"  # alerts link back to the CVE in the app
    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    alert_email_from: str = ""
    alert_email_to: str = ""
    # Search (A09). The index is built by `python -m app.rag.build_index` and loaded at start-up.
    embedder: str = "hash"
    embed_model: str = ""  # empty = the embedder's default
    index_path: pathlib.Path = ROOT / "data" / "index"
    search_min_score: float | None = None  # empty = the embedder's default threshold
    openrouter_api_key: str = ""
    ollama_url: str = "http://localhost:11434"

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "fake").strip().lower(),
            state_path=_path("STATE_PATH", cls.state_path),
            as_of=os.environ.get("AS_OF", "").strip() or snapshot_date(),
            cors_origins=_list(os.environ.get("CORS_ORIGINS", DEFAULT_CORS)),
            dev_panel=_flag(os.environ.get("DEV_PANEL", ""), default=True),
            app_url=_env("APP_URL", cls.app_url).rstrip("/"),
            ntfy_url=_env("NTFY_URL", cls.ntfy_url).rstrip("/"),
            ntfy_topic=_env("NTFY_TOPIC"),
            ntfy_token=_env("NTFY_TOKEN"),
            smtp_host=_env("SMTP_HOST"),
            smtp_port=_int("SMTP_PORT", cls.smtp_port),
            smtp_user=_env("SMTP_USER"),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),  # not stripped: spaces can be part of a password
            smtp_starttls=_flag(os.environ.get("SMTP_STARTTLS", ""), default=True),
            alert_email_from=_env("ALERT_EMAIL_FROM"),
            alert_email_to=_env("ALERT_EMAIL_TO"),
            embedder=_env("EMBEDDER", cls.embedder).lower(),
            embed_model=_env("EMBED_MODEL"),
            index_path=_path("INDEX_PATH", cls.index_path),
            search_min_score=_float("SEARCH_MIN_SCORE"),
            openrouter_api_key=_env("OPENROUTER_API_KEY"),
            ollama_url=_env("OLLAMA_URL", cls.ollama_url).rstrip("/"),
        )

    def check(self) -> None:
        """Fail at start-up with a plain message."""
        if self.llm_provider not in PROVIDERS:
            raise ConfigError(
                f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)}, not {self.llm_provider!r}. "
                "Only FakeLLM is built so far."
            )
        if self.embedder not in EMBEDDERS:
            raise ConfigError(f"EMBEDDER must be one of {', '.join(EMBEDDERS)}, not {self.embedder!r}.")
        if self.embedder == "openrouter" and not self.openrouter_api_key:
            raise ConfigError("EMBEDDER=openrouter needs OPENROUTER_API_KEY in backend/.env.")
        if self.embedder == "ollama" and urlparse(self.ollama_url).hostname not in LOCAL_HOSTS:
            raise ConfigError(f"OLLAMA_URL must point at this machine (localhost), not {self.ollama_url!r}.")

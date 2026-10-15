"""Settings from environment variables. Every one is listed in .env.example.

Plain dataclass and os.environ: no extra dependency, and tests build Settings directly.
Load a .env file with `uv run --env-file .env ...`.
"""
import json
import os
import pathlib
from dataclasses import dataclass, field

from app.llm.urls import local_url_allowed

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"  # the snapshot's folder

DEFAULT_WATCHLIST = ["langchain", "langflow", "litellm", "ollama", "open-webui"]
LIBRARY_PRODUCTS = {"langchain", "llamaindex", "gradio"}  # default usage "library"; every other product "self_hosted"
DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
PROVIDERS = ("fake", "openrouter", "local")
EMBEDDERS = ("hash", "openrouter", "ollama")  # hash: the free test fake; the other two need the index built (A09)
LOOPBACK_HOSTS = ["localhost", "127.0.0.1", "::1"]
DATA_MODES = ("snapshot", "live")  # snapshot: frozen data, as of its date (the default and the tests); live: refreshed
FEED_KINDS = ("fake", "real")  # fake: the made-up day data sets (B02, no network); real: NVD, KEV, EPSS, OSV (B03)


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
    # The real model (A08). The key is a secret: .env only, never in the state file or an API reply.
    openrouter_api_key: str = ""
    openrouter_model: str = "anthropic/claude-haiku-5.5"  # A20: best of 11 models in the model check
    local_llm_url: str = "http://localhost:11434/v1"  # Ollama; LM Studio is :1234, llama.cpp :8080
    local_llm_model: str = ""
    local_llm_hosts: list[str] = field(default_factory=lambda: list(LOOPBACK_HOSTS))  # plus LOCAL_LLM_HOSTS
    state_path: pathlib.Path = ROOT / "data" / "state.json"
    as_of: str = field(default_factory=snapshot_date)
    cors_origins: list[str] = field(default_factory=lambda: _list(DEFAULT_CORS))
    dev_panel: bool = True  # the Dev page (and later its routes) exist only when this is on
    # The built frontend (B12): set, one port serves it and the API moves under /api. The container sets it.
    frontend_dir: pathlib.Path | None = None
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
    ollama_url: str = "http://localhost:11434"
    # Live data (B02). In live mode the as-of date is today and Check now refreshes the CVE data from the feeds.
    data_mode: str = "snapshot"
    live_path: pathlib.Path = ROOT / "data" / "live"  # the live data's versions and the refresh log
    feeds: str = "fake"
    fake_feeds_day: int = 2  # which data set the fake feeds serve (fixtures/fake_feeds/day<n>.json)
    nvd_api_key: str = ""  # optional (B03): NVD allows 50 requests per 30 s with it, 5 without. A secret: .env only

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "fake").strip().lower(),
            openrouter_api_key=_env("OPENROUTER_API_KEY"),
            openrouter_model=_env("OPENROUTER_MODEL", cls.openrouter_model),
            local_llm_url=_env("LOCAL_LLM_URL", cls.local_llm_url),
            local_llm_model=_env("LOCAL_LLM_MODEL"),
            local_llm_hosts=LOOPBACK_HOSTS + _list(os.environ.get("LOCAL_LLM_HOSTS", "")),
            state_path=_path("STATE_PATH", cls.state_path),
            as_of=os.environ.get("AS_OF", "").strip() or snapshot_date(),
            cors_origins=_list(os.environ.get("CORS_ORIGINS", DEFAULT_CORS)),
            dev_panel=_flag(os.environ.get("DEV_PANEL", ""), default=True),
            frontend_dir=_path("FRONTEND_DIR", pathlib.Path()) if _env("FRONTEND_DIR") else None,
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
            ollama_url=_env("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            data_mode=_env("DATA_MODE", cls.data_mode).lower(),
            live_path=_path("LIVE_PATH", cls.live_path),
            feeds=_env("FEEDS", cls.feeds).lower(),
            fake_feeds_day=_int("FAKE_FEEDS_DAY", cls.fake_feeds_day),
            nvd_api_key=_env("NVD_API_KEY"),
        )

    def check(self) -> None:
        """Fail at start-up with a plain message."""
        if self.llm_provider not in PROVIDERS:
            raise ConfigError(
                f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)}, not {self.llm_provider!r}."
            )
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ConfigError("LLM_PROVIDER=openrouter needs OPENROUTER_API_KEY. Set it in backend/.env "
                              "(see .env.example), or use LLM_PROVIDER=fake.")
        if self.llm_provider == "local":
            if not local_url_allowed(self.local_llm_url, self.local_llm_hosts):
                raise ConfigError(f"LOCAL_LLM_URL must be on this machine (localhost, 127.0.0.1, ::1 or a host in "
                                  f"LOCAL_LLM_HOSTS), not {self.local_llm_url!r}.")
            if not self.local_llm_model:
                raise ConfigError("LLM_PROVIDER=local needs LOCAL_LLM_MODEL, e.g. the name `ollama list` shows.")
        if self.data_mode not in DATA_MODES:
            raise ConfigError(f"DATA_MODE must be one of {', '.join(DATA_MODES)}, not {self.data_mode!r}.")
        if self.feeds not in FEED_KINDS:
            raise ConfigError(f"FEEDS must be one of {', '.join(FEED_KINDS)}, not {self.feeds!r}.")
        if self.fake_feeds_day not in (1, 2):
            raise ConfigError(f"FAKE_FEEDS_DAY must be 1 or 2, not {self.fake_feeds_day}.")
        if self.frontend_dir is not None and not (self.frontend_dir / "index.html").is_file():
            raise ConfigError(f"FRONTEND_DIR is {self.frontend_dir}, but there's no index.html there. Build the "
                              "frontend first (cd frontend && npm run build), or leave FRONTEND_DIR empty.")
        if self.embedder not in EMBEDDERS:
            raise ConfigError(f"EMBEDDER must be one of {', '.join(EMBEDDERS)}, not {self.embedder!r}.")
        if self.embedder == "openrouter" and not self.openrouter_api_key:
            raise ConfigError("EMBEDDER=openrouter needs OPENROUTER_API_KEY in backend/.env.")
        if self.embedder == "ollama" and not local_url_allowed(self.ollama_url, self.local_llm_hosts):
            raise ConfigError(f"OLLAMA_URL must be on this machine (localhost, 127.0.0.1, ::1 or a host in "
                              f"LOCAL_LLM_HOSTS), not {self.ollama_url!r}.")

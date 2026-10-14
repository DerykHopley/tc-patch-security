"""Settings from environment variables. Every one is listed in .env.example.

Plain dataclass and os.environ: no extra dependency, and tests build Settings directly.
Load a .env file with `uv run --env-file .env ...`.
"""
import json
import os
import pathlib
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"  # the snapshot's folder

DEFAULT_WATCHLIST = ["langchain", "langflow", "litellm", "ollama", "open-webui"]
DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
PROVIDERS = ("fake",)  # openrouter and local arrive with the real model (A08)


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

    @classmethod
    def from_env(cls) -> "Settings":
        state_path = pathlib.Path(os.environ.get("STATE_PATH", "").strip() or cls.state_path)
        if not state_path.is_absolute():
            state_path = ROOT / state_path
        return cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "fake").strip().lower(),
            state_path=state_path,
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
        )

    def check(self) -> None:
        """Fail at start-up with a plain message."""
        if self.llm_provider not in PROVIDERS:
            raise ConfigError(
                f"LLM_PROVIDER must be one of {', '.join(PROVIDERS)}, not {self.llm_provider!r}. "
                "Only FakeLLM is built so far."
            )

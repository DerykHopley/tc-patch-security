"""Settings from environment variables. See .env.example."""
import json
import os
import pathlib
from dataclasses import dataclass, field

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "fixtures"

DEFAULT_WATCHLIST = ["langchain", "langflow", "litellm", "ollama", "open-webui"]  # W1
DEFAULT_CORS = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174"  # A5


def snapshot_date() -> str:
    return json.loads((FIXTURES / "manifest.json").read_text())["as_of"]


class ConfigError(RuntimeError):
    pass


@dataclass
class Settings:
    llm_provider: str = "fake"
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    state_path: pathlib.Path = ROOT / "data" / "state.json"
    max_steps: int = 4
    as_of: str = field(default_factory=snapshot_date)
    cors_origins: list[str] = field(default_factory=lambda: DEFAULT_CORS.split(","))
    dev_panel: bool = True  # X4: the dev routes exist only when this is on
    # Local models (M1–M3): the server only calls these hosts, so the dev panel can't be used for SSRF.
    local_llm_hosts: list[str] = field(default_factory=lambda: ["localhost", "127.0.0.1", "::1"])
    # Notification channels (N1–N4). Secrets live here, never in state.json or the API.
    app_url: str = "http://localhost:5173"
    ntfy_url: str = "https://ntfy.sh"
    ntfy_topic: str = ""
    ntfy_token: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    email_from: str = ""
    email_to: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls(
            llm_provider=os.environ.get("LLM_PROVIDER", "fake").strip().lower(),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY", "").strip(),
            openrouter_model=os.environ.get("OPENROUTER_MODEL", cls.openrouter_model).strip(),
            state_path=pathlib.Path(os.environ.get("STATE_PATH", str(cls.state_path))),
            max_steps=int(os.environ.get("MAX_STEPS", "4")),
            as_of=os.environ.get("AS_OF", "").strip() or snapshot_date(),
            cors_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", DEFAULT_CORS).split(",") if o.strip()],
            dev_panel=os.environ.get("DEV_PANEL", "true").strip().lower() in ("1", "true", "yes"),
            local_llm_hosts=["localhost", "127.0.0.1", "::1"]
            + [h.strip() for h in os.environ.get("LOCAL_LLM_HOSTS", "").split(",") if h.strip()],
            app_url=os.environ.get("APP_URL", cls.app_url).strip().rstrip("/"),
            ntfy_url=os.environ.get("NTFY_URL", cls.ntfy_url).strip().rstrip("/"),
            ntfy_topic=os.environ.get("NTFY_TOPIC", "").strip(),
            ntfy_token=os.environ.get("NTFY_TOKEN", "").strip(),
            smtp_host=os.environ.get("SMTP_HOST", "").strip(),
            smtp_port=int(os.environ.get("SMTP_PORT", "587")),
            smtp_user=os.environ.get("SMTP_USER", "").strip(),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            smtp_starttls=os.environ.get("SMTP_STARTTLS", "true").strip().lower() in ("1", "true", "yes"),
            email_from=os.environ.get("ALERT_EMAIL_FROM", "").strip(),
            email_to=os.environ.get("ALERT_EMAIL_TO", "").strip(),
        )
        if not s.state_path.is_absolute():
            s.state_path = ROOT / s.state_path
        return s

    def check(self) -> None:
        """Fail at start-up with a clear message (L2)."""
        if self.llm_provider not in ("fake", "openrouter", "local"):
            raise ConfigError(f"LLM_PROVIDER must be 'fake', 'openrouter' or 'local', not {self.llm_provider!r}.")
        if self.llm_provider == "openrouter" and not self.openrouter_api_key:
            raise ConfigError("LLM_PROVIDER=openrouter needs OPENROUTER_API_KEY. Set it in .env (see .env.example).")

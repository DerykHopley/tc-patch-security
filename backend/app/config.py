"""Settings from environment variables. Every one is listed in .env.example.

Plain dataclass and os.environ: no extra dependency, and tests build Settings directly.
Load a .env file with `uv run --env-file .env ...`.
"""
import json
import os
import pathlib
import re
import zoneinfo
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
# The one user while sign-in is off (B09): their state is STATE_PATH. Per-user counters and alerts key by this id.
DEFAULT_USER = "default"
USER_ID = re.compile(r"[A-Za-z0-9_-]{1,64}")  # a user id as the state store keys it (Clerk's ids: user_2abc...)
DATA_MODES = ("snapshot", "live")  # snapshot: frozen data, as of its date (the default and the tests); live: refreshed
FEED_SOURCES = ("nvd", "kev", "osv", "epss")  # the four feeds, in the order a refresh asks them
STORES = ("local", "gcs")  # B13: where users' state and the live data live: files here, a Cloud Storage bucket deployed
SCHEDULER_SECRET_MIN = 32  # B13: the scheduled route's secret, at least this long (the deploy makes 64 hex characters)
FEED_KINDS = ("fake", "real")  # fake: the made-up day data sets (B02, no network); real: NVD, KEV, EPSS, OSV (B03)
# B26: what the owner can set on Settings instead of .env (field -> its environment variable). The environment wins
# when it sets one; else the owner's saved value; else the default. Deployment settings (sign-in, the store, paths,
# CORS, the scheduler's secret) stay in .env only: the app needs them before it can read Settings, or they could lock
# you out. app.server_settings applies the rule.
MOVABLE = {"data_mode": "DATA_MODE", "alert_tz": "ALERT_TZ", "app_url": "APP_URL", "ntfy_url": "NTFY_URL",
           "smtp_port": "SMTP_PORT", "smtp_starttls": "SMTP_STARTTLS", "telegram_chat_id": "TELEGRAM_CHAT_ID"}
# B26: the secrets among them: write-only on Settings, never sent back (the API says only whether one is set).
SECRETS = {"ntfy_topic": "NTFY_TOPIC", "ntfy_token": "NTFY_TOKEN", "smtp_host": "SMTP_HOST", "smtp_user": "SMTP_USER",
           "smtp_password": "SMTP_PASSWORD", "alert_email_from": "ALERT_EMAIL_FROM",
           "alert_email_to": "ALERT_EMAIL_TO", "nvd_api_key": "NVD_API_KEY", "telegram_bot_token": "TELEGRAM_BOT_TOKEN"}


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


def _auth(value: str) -> bool:
    if value.lower() not in ("on", "off"):
        raise ConfigError(f"AUTH must be on or off, not {value!r}.")
    return value.lower() == "on"


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
    # B57 (#102): the owner's Telegram bot. The token is a secret (it is part of every Bot API URL); the chat id isn't
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    alert_tz: str = "UTC"  # the time zone of quiet hours (B04): an IANA name, e.g. Europe/London
    notify_dry_run: bool = False  # on: every channel records only, nothing is sent (the browser check's live pair)
    # Search (A09). The index is built by `python -m app.rag.build_index` and loaded at start-up.
    embedder: str = "hash"
    embed_model: str = ""  # empty = the embedder's default
    index_path: pathlib.Path = ROOT / "data" / "index"
    search_min_score: float | None = None  # empty = the embedder's default threshold
    ollama_url: str = "http://localhost:11434"
    # Web research (B08). Without the key the research_web tool is off and not offered to the model. The key is a
    # secret: .env only. It goes in a header, never in a URL, so no log line can carry it.
    tavily_api_key: str = ""
    tavily_mcp_url: str = "https://mcp.tavily.com/mcp/"  # Tavily's hosted remote MCP server
    tavily_api_url: str = "https://api.tavily.com"  # the plain search API, the fallback
    web_research_daily_cap: int = 30  # searches a day, all users together: the free 1,000 credits a month
    web_research_user_daily_cap: int = 30  # searches a day, per user
    # Live data (B02). In live mode the as-of date is today and Check now refreshes the CVE data from the feeds.
    data_mode: str = "snapshot"
    live_path: pathlib.Path = ROOT / "data" / "live"  # the live data's versions and the refresh log
    feeds: str = "real"  # B28: the real services; tests, run.sh and container.sh set fake themselves
    fake_feeds_day: int = 2  # which data set the fake feeds serve (fixtures/fake_feeds/day<n>.json)
    fake_feeds_fail: list[str] = field(default_factory=list)  # B20: fake feeds that fail, for docs/failure-demo.md
    # B20: chat tools that time out inside an answer (Try again still runs them), for docs/failure-demo.md
    fail_tools: list[str] = field(default_factory=list)
    nvd_api_key: str = ""  # optional (B03): NVD allows 50 requests per 30 s with it, 5 without. A secret: .env only
    # B09: the user whose alerts go to the channels (ntfy, email, desktop: the owner's, from this environment). Other
    # users' alerts are recorded and shown in the app only. Locally, the default user.
    owner: str = DEFAULT_USER
    # Sign-in (B10). Off locally and in the tests: every request is the default user. On, every route but /health
    # needs a Clerk session token, verified with the instance's JWT public key (no network call), whose `azp` (the
    # page's origin) is one of AUTH_ALLOWED_ORIGINS. None of these is a secret.
    auth: bool = False
    clerk_publishable_key: str = ""  # pk_test_...: the frontend reads it from /health, so one image fits any instance
    clerk_jwt_key: str = ""  # the PEM public key from the Clerk dashboard's API keys page
    auth_allowed_origins: list[str] = field(default_factory=list)  # e.g. https://patch-xyz.a.run.app
    # B38: the Clerk secret key (sk_...), a secret: .env or Secret Manager only, never sent to a page. Optional: the
    # owner's Requests card uses it to look up names and emails in Clerk's Backend API; without it, user ids only.
    clerk_secret_key: str = ""
    # B11: chat messages per user, per minute and per UTC day (counted in memory: one instance). OpenRouter's spending
    # cap on the key stays the backstop.
    chat_per_minute: int = 10
    chat_per_day: int = 200
    # B13, the deploy: local = users' state and the live data are files (STATE_PATH, LIVE_PATH); gcs = objects in the
    # Cloud Storage bucket GCS_BUCKET (users/<id>.json, live/...), so they survive restarts and scale-to-zero.
    store: str = "local"
    gcs_bucket: str = ""
    # B13: the secret Cloud Scheduler sends in the X-Scheduler-Secret header to POST /refresh/scheduled. Empty = the
    # route doesn't exist (locally the systemd timer runs the CLI instead). A secret: Secret Manager or .env only.
    scheduler_secret: str = ""
    # B26: the MOVABLE and SECRETS fields the environment set (not empty). These win over the owner's saved values.
    # Built directly (the tests), nothing counts as set by the environment: the given values are the defaults.
    env_set: frozenset[str] = frozenset()

    @property
    def users_path(self) -> pathlib.Path:
        """Other users' state files (B09), next to the default user's: `state.json` -> `state-users/<id>.json`."""
        return self.state_path.with_name(f"{self.state_path.stem}-users")

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
            telegram_bot_token=_env("TELEGRAM_BOT_TOKEN"),
            telegram_chat_id=_env("TELEGRAM_CHAT_ID"),
            alert_tz=_env("ALERT_TZ", cls.alert_tz),
            notify_dry_run=_flag(os.environ.get("NOTIFY_DRY_RUN", ""), default=False),
            embedder=_env("EMBEDDER", cls.embedder).lower(),
            embed_model=_env("EMBED_MODEL"),
            index_path=_path("INDEX_PATH", cls.index_path),
            search_min_score=_float("SEARCH_MIN_SCORE"),
            ollama_url=_env("OLLAMA_URL", cls.ollama_url).rstrip("/"),
            tavily_api_key=_env("TAVILY_API_KEY"),
            tavily_mcp_url=_env("TAVILY_MCP_URL", cls.tavily_mcp_url),
            tavily_api_url=_env("TAVILY_API_URL", cls.tavily_api_url).rstrip("/"),
            web_research_daily_cap=_int("WEB_RESEARCH_DAILY_CAP", cls.web_research_daily_cap),
            web_research_user_daily_cap=_int("WEB_RESEARCH_USER_DAILY_CAP", cls.web_research_user_daily_cap),
            data_mode=_env("DATA_MODE", cls.data_mode).lower(),
            live_path=_path("LIVE_PATH", cls.live_path),
            feeds=_env("FEEDS", cls.feeds).lower(),
            fake_feeds_day=_int("FAKE_FEEDS_DAY", cls.fake_feeds_day),
            fake_feeds_fail=_list(_env("FAKE_FEEDS_FAIL").lower()),
            fail_tools=_list(_env("FAIL_TOOLS").lower()),
            nvd_api_key=_env("NVD_API_KEY"),
            owner=_env("OWNER", DEFAULT_USER),
            auth=_auth(_env("AUTH", "off")),
            clerk_publishable_key=_env("CLERK_PUBLISHABLE_KEY"),
            clerk_jwt_key=_env("CLERK_JWT_KEY").replace("\\n", "\n"),  # one line in .env: \n for the line breaks
            auth_allowed_origins=[o.rstrip("/") for o in _list(_env("AUTH_ALLOWED_ORIGINS"))],
            clerk_secret_key=_env("CLERK_SECRET_KEY"),
            chat_per_minute=_int("CHAT_PER_MINUTE", cls.chat_per_minute),
            chat_per_day=_int("CHAT_PER_DAY", cls.chat_per_day),
            store=_env("STORE", cls.store).lower(),
            gcs_bucket=_env("GCS_BUCKET"),
            scheduler_secret=_env("SCHEDULER_SECRET"),
            env_set=frozenset(f for f, name in {**MOVABLE, **SECRETS}.items() if os.environ.get(name, "").strip()),
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
        try:
            zoneinfo.ZoneInfo(self.alert_tz)
        except (zoneinfo.ZoneInfoNotFoundError, ValueError):
            raise ConfigError(f"ALERT_TZ must be a time zone name like UTC or Europe/London, not {self.alert_tz!r}.")
        if not USER_ID.fullmatch(self.owner):
            raise ConfigError(f"OWNER must be a user id (letters, digits, _ and -), not {self.owner!r}.")
        if self.auth:
            missing = [name for name, value in (("CLERK_PUBLISHABLE_KEY", self.clerk_publishable_key),
                                                ("CLERK_JWT_KEY", self.clerk_jwt_key),
                                                ("AUTH_ALLOWED_ORIGINS", self.auth_allowed_origins)) if not value]
            if missing:
                raise ConfigError(f"AUTH=on needs {', '.join(missing)}. Set them in backend/.env (see .env.example), "
                                  "or use AUTH=off.")
            if self.owner == DEFAULT_USER:
                raise ConfigError("AUTH=on needs OWNER: the owner's Clerk user id (user_...), from the Clerk dashboard's "
                                  "Users page. The owner's alerts go to the channels and the owner's schedule runs; "
                                  "with sign-in on, nobody signs in as \"default\".")
            if "BEGIN PUBLIC KEY" not in self.clerk_jwt_key:
                raise ConfigError("CLERK_JWT_KEY must be the PEM public key from the Clerk dashboard (API keys, "
                                  "\"JWT public key\"), starting -----BEGIN PUBLIC KEY-----.")
        if self.store not in STORES:
            raise ConfigError(f"STORE must be local or gcs, not {self.store!r}.")
        if self.store == "gcs" and not self.gcs_bucket:
            raise ConfigError("STORE=gcs needs GCS_BUCKET, the Cloud Storage bucket's name (DEPLOY.md).")
        if self.scheduler_secret and len(self.scheduler_secret) < SCHEDULER_SECRET_MIN:
            raise ConfigError(f"SCHEDULER_SECRET must be at least {SCHEDULER_SECRET_MIN} characters (make one with "
                              "`openssl rand -hex 32`), or empty for no scheduled route.")
        if self.fake_feeds_day not in (1, 2):
            raise ConfigError(f"FAKE_FEEDS_DAY must be 1 or 2, not {self.fake_feeds_day}.")
        from app.tools.registry import TOOLS  # here, not at the top: the tools import the config

        if unknown := [t for t in self.fail_tools if t not in TOOLS]:
            raise ConfigError(f"FAIL_TOOLS lists chat tools to fail, from {', '.join(TOOLS)}; "
                              f"not {', '.join(unknown)}.")
        if unknown := [s for s in self.fake_feeds_fail if s not in FEED_SOURCES]:
            raise ConfigError(f"FAKE_FEEDS_FAIL lists feeds to fail, from {', '.join(FEED_SOURCES)}; "
                              f"not {', '.join(unknown)}.")
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

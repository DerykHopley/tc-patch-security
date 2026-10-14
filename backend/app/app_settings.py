"""What the Settings page saves (A13): alert rules and channels, validated.

Defaults come from the environment (`.env`); saved values override them. Later tickets add their own parts
(policy, explain level, dev) next to `alerts`; the state file keeps parts it doesn't know.
"""
from typing import Literal

from pydantic import BaseModel, Field

from app.config import Settings

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Channel = Literal["desktop", "email", "ntfy"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class AlertSettings(BaseModel):
    """Saved now; the refresh worker in spec B reads them. Nothing checks for new CVEs yet."""
    enabled: bool = True
    min_severity: Severity = "HIGH"
    kev: bool = True  # a watched CVE is added to CISA KEV
    kev_recheck: bool = True  # a CVE marked fixed is added to KEV: check the fix
    unscored: bool = True  # a new CVE has no severity yet
    now_critical: bool = True  # an open CVE is rescored as critical
    digest_over: int = Field(5, ge=1, le=50)  # more alerts than this per check become one digest
    schedule_hours: Literal[1, 3, 6, 12, 24] = 6
    quiet_start: str | None = Field(None, pattern=HHMM)
    quiet_end: str | None = Field(None, pattern=HHMM)
    channels: list[Channel] = Field(default_factory=lambda: ["desktop"])


class AppSettings(BaseModel):
    alerts: AlertSettings = Field(default_factory=AlertSettings)


def default_settings(env: Settings) -> AppSettings:
    """The defaults from the environment: desktop, plus every channel set up in .env."""
    channels: list[Channel] = ["desktop"]
    if env.smtp_host and env.alert_email_to:
        channels.append("email")
    if env.ntfy_topic:
        channels.append("ntfy")
    return AppSettings(alerts=AlertSettings(channels=channels))


class DevSettings(BaseModel):
    """The dev panel's choices (A11): who answers, the agent's limits and search tuning. Read on every request, so a
    saved change applies on the next call with no restart. Only used while DEV_PANEL is on; off, the env defaults apply.
    """
    provider: Literal["fake", "openrouter", "local"] = "fake"
    openrouter_model: str = Field("openai/gpt-oss-120b", min_length=3, max_length=100,
                                  pattern=r"^[\w.\-]+/[\w.:\-]+$")
    local_url: str = Field("http://localhost:11434/v1", max_length=200)  # checked by the SSRF guard on save
    local_model: str = Field("", max_length=200, pattern=r"^[\w.:/@\-]*$")
    temperature: float = Field(0.2, ge=0, le=2)
    max_steps: int = Field(4, ge=1, le=8)
    # Search (SearchOptions): the defaults are the spec's values.
    top_n: int = Field(5, ge=1, le=10)
    per_query_k: int = Field(10, ge=1, le=30)
    per_doc_cap: int = Field(2, ge=1, le=5)
    rrf_k: int = Field(60, ge=1, le=200)
    keyword_weight: float = Field(0.5, ge=0, le=1)  # 0 = vector only, 1 = keyword (BM25) only
    use_rewrites: bool = True
    use_filters: bool = True


def default_dev_settings(env: Settings) -> DevSettings:
    """The env's model choice (LLM_PROVIDER, OPENROUTER_MODEL, LOCAL_LLM_URL, LOCAL_LLM_MODEL) as the starting point."""
    return DevSettings(provider=env.llm_provider, openrouter_model=env.openrouter_model,  # type: ignore[arg-type]
                       local_url=env.local_llm_url, local_model=env.local_llm_model)


class ResetRequest(BaseModel):
    confirm: Literal["reset"]  # the word must be typed: anything else is a 400


class TestAlertRequest(BaseModel):
    channel: Literal["desktop", "email", "ntfy", "preview"] = "preview"

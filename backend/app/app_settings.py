"""What the Settings page saves (A13): alert rules and channels, validated.

Defaults come from the environment (`.env`); saved values override them. Later tickets add their own parts
(policy, dev) next to `alerts`, or single values like `explain_level` (A19); the state file keeps parts it doesn't
know.
"""
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.config import Settings

Severity = Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
Channel = Literal["desktop", "email", "ntfy"]
HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class AlertSettings(BaseModel):
    """The alert rules and channels a live refresh reads (app.alerts, B04). due_soon and overdue have no switch: they
    are always on while `enabled` is. Quiet hours are in ALERT_TZ."""
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


ExplainLevel = Literal["simple", "normal", "deep_dive"]  # how Patch pitches an answer (A19)


class PolicySettings(BaseModel):
    """Your policy (A16): days allowed per priority level, counted from the publication (or KEV-added) date, and
    whether KEV CVEs take CISA's KEV deadline instead. A more urgent level never gets more days than a less urgent one.
    """
    urgent_days: int = Field(7, ge=1, le=730)
    high_days: int = Field(30, ge=1, le=730)
    normal_days: int = Field(90, ge=1, le=730)
    low_days: int = Field(180, ge=1, le=730)
    adopt_kev_deadline: bool = True

    @model_validator(mode="after")
    def _ordered(self):
        if not self.urgent_days <= self.high_days <= self.normal_days <= self.low_days:
            raise ValueError("days must not shrink as the level gets less urgent: urgent ≤ high ≤ normal ≤ low")
        return self

    def days(self, level: str) -> int:
        return getattr(self, f"{level}_days")


class PrioritySettings(BaseModel):
    """The priority rules' tunable threshold (A16): EPSS at or above this percentile, on an internet-facing product,
    makes a CVE high priority (row 2)."""
    epss_percentile: int = Field(90, ge=50, le=99)


class AppSettings(BaseModel):
    alerts: AlertSettings = Field(default_factory=AlertSettings)
    explain_level: ExplainLevel = "normal"
    policy: PolicySettings = Field(default_factory=PolicySettings)
    priority: PrioritySettings = Field(default_factory=PrioritySettings)


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
    openrouter_model: str = Field("anthropic/claude-haiku-5.5", min_length=3, max_length=100,
                                  pattern=r"^[\w.\-]+/[\w.:\-]+$")
    local_url: str = Field("http://localhost:11434/v1", max_length=200)  # checked by the SSRF guard on save
    local_model: str = Field("", max_length=200, pattern=r"^[\w.:/@\-]*$")
    temperature: float = Field(0.2, ge=0, le=2)
    max_steps: int = Field(6, ge=1, le=8)  # 6 (B22): the research workflow is four tool rounds and an answer
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

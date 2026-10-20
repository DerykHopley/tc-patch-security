"""What the owner sets on Settings instead of .env (B26, #70): live or snapshot data, the quiet hours' time zone, the
alert link address, the ntfy server, SMTP's port, the Telegram chat id, and the channels' secrets.

One rule for every one of them (`effective`): the environment wins when it sets it, else the owner's saved value, else
the default. They are saved in the owner's state, next to their other settings (the state file is git-ignored
locally; deployed, the bucket is private). Secrets are write-only: `status` says only whether one is set and where
from, never its value, and no message here names a value.
"""
import dataclasses
import zoneinfo
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.config import MOVABLE, SECRETS, Settings
from app.errors import InputError
from app.notify import reachable_from_phone

Url = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200, pattern=r"^https?://[^\s/?#]+[^\s]*$")]
Secret = Annotated[str, StringConstraints(min_length=1, max_length=500)]
Email = Annotated[str, StringConstraints(strip_whitespace=True, max_length=200, pattern=r"^[^@\s]+@[^@\s]+$")]
Source = Literal["env", "saved", "default"]
# B57: Telegram's form, "<bot id>:<secret>" (docs/SOURCE-CHECKS.md). A refusal never quotes it: the 400 handler gives
# pydantic's message, which names the rule, not the input
TelegramToken = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^[0-9]{1,20}:[A-Za-z0-9_-]{20,100}$")]


class ServerSettings(BaseModel):
    """The owner's saved values. None: nothing saved, so the environment's value or the default applies."""
    data_mode: Literal["snapshot", "live"] | None = None
    alert_tz: str | None = Field(None, max_length=64)  # an IANA name, e.g. Europe/London
    app_url: Url | None = None  # alerts link back to the CVE at this address
    ntfy_url: Url | None = None
    smtp_port: int | None = Field(None, ge=1, le=65535)
    smtp_starttls: bool | None = None
    # B57: a chat's id (a number; a group's is negative) or a channel's @username, as Telegram's sendMessage takes it
    telegram_chat_id: Annotated[str, StringConstraints(strip_whitespace=True,
                                                       pattern=r"^(-?[0-9]{1,20}|@[A-Za-z0-9_]{5,32})$")] | None = None
    # The secrets (config.SECRETS): write-only
    ntfy_topic: Annotated[str, StringConstraints(pattern=r"^[-_A-Za-z0-9]{1,64}$")] | None = None  # ntfy's rule
    ntfy_token: Secret | None = None
    smtp_host: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200,
                                                pattern=r"^[A-Za-z0-9.\-:\[\]]+$")] | None = None
    smtp_user: Secret | None = None
    smtp_password: Secret | None = None
    alert_email_from: Email | None = None
    alert_email_to: Email | None = None
    telegram_bot_token: TelegramToken | None = None
    nvd_api_key: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)] | None = None

    @field_validator("alert_tz")
    @classmethod
    def _zone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                zoneinfo.ZoneInfo(value)
            except (zoneinfo.ZoneInfoNotFoundError, ValueError):
                raise ValueError("must be a time zone name like UTC or Europe/London") from None
        return value

    @field_validator("app_url", "ntfy_url")
    @classmethod
    def _no_slash(cls, value: str | None) -> str | None:
        return value.rstrip("/") if value else value


class ServerUpdate(ServerSettings):
    """A change from Settings: a field left out stays as saved, a value saves it, null removes the saved one."""
    model_config = ConfigDict(extra="forbid")


def source(env: Settings, saved: ServerSettings, name: str) -> Source:
    if name in env.env_set:
        return "env"
    return "saved" if getattr(saved, name) is not None else "default"


def effective(env: Settings, saved: ServerSettings) -> Settings:
    """The settings the app runs on: `env` (from the environment, defaults filled in) with the owner's saved values
    wherever the environment didn't set one."""
    changes = {name: value for name, value in saved.model_dump().items()
               if value is not None and name not in env.env_set}
    return dataclasses.replace(env, **changes) if changes else env


def status(env: Settings, saved: ServerSettings) -> dict:
    """What Settings shows: each plain setting's value and where it comes from; for a secret only whether it's set
    and where from. `env_names`: the environment variable of each, for "set in the server's environment"."""

    now = effective(env, saved)
    return {
        "fields": {name: {"value": getattr(now, name), "source": source(env, saved, name)} for name in MOVABLE},
        "secrets": {name: {"set": bool(getattr(now, name)), "source": source(env, saved, name)} for name in SECRETS},
        "env_names": {**MOVABLE, **SECRETS},
        "app_url_reachable": reachable_from_phone(now.app_url),
        # B28: where live data comes from (FEEDS, .env only): real, or the made-up test data, shown as a warning
        "feeds": now.feeds,
    }


def updated(env: Settings, saved: ServerSettings, change: ServerUpdate) -> ServerSettings:
    """The saved values after `change`. A setting the environment sets can't be changed here: the environment wins,
    so a saved value would never apply."""
    locked = sorted({**MOVABLE, **SECRETS}[name] for name in change.model_fields_set if name in env.env_set)
    if locked:
        raise InputError(f"{', '.join(locked)} {'is' if len(locked) == 1 else 'are'} set in the server's environment, "
                         "which wins. Remove it from backend/.env and restart the server to set it here.",
                         "set_in_env")
    return saved.model_copy(update={name: getattr(change, name) for name in change.model_fields_set})

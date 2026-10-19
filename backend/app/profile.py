"""Your profile (B48, #97; the decisions of #77): anonymous by default, an optional display name.

Patch needs nothing but Clerk's user id (the token's `sub`). The name is one the user gives Patch on Settings, kept in
their own state (part `profile`), never read from the session token. It is used in the user menu and in new decision
records ("Decided by <name>", else "you"). Nobody else's view shows it.
"""
import re

from pydantic import BaseModel, ConfigDict, Field

NAME_MAX = 60  # characters once cleaned: the menu card and a record's "by" line stay one short line

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ProfileUpdate(BaseModel):
    """`PUT /profile`: the display name, or null (or empty) to remove it. The length is checked after `clean_name`."""
    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, max_length=1000)


def clean_name(name: str | None) -> str | None:
    """Plain text on one line: control characters dropped, runs of spaces made one, trimmed; None when empty."""
    text = " ".join(_CONTROL.sub(" ", name or "").split())
    return text or None

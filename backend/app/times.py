"""Times as the app writes them: ISO 8601 in UTC, to the second (`2026-10-16T09:00:00+00:00`)."""
import datetime as dt


def iso_utc(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).isoformat(timespec="seconds")

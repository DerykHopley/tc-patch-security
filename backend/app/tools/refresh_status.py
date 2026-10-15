"""refresh_status (B19): when the data was last checked, whether the schedule is on, and what the last run did.

Reads the refresh log and the user's schedule settings, the same data as Settings' "Refresh runs" card and the
dashboard's freshness card; it never starts a check. B06's check_updates (which runs one) may take this over
(DECISIONS.md, 2026-10-16).
"""
import datetime as dt
from typing import Literal

from pydantic import BaseModel

from app.refresh import schedule_due
from app.tools.registry import ToolResult, ToolSpec, register


class NoArgs(BaseModel):
    pass


class Schedule(ToolResult):
    hours: int
    paused: bool
    next_due: str | None  # ISO 8601, UTC; None: paused, snapshot mode, or never checked (the next tick runs)


class LastRun(ToolResult):
    trigger: Literal["button", "chat", "schedule", "cli"]
    started: str
    result: Literal["ok", "partial", "failed"]
    new: int
    kev_added: int
    rescored: int
    failed_sources: list[str]  # nvd, kev, osv or epss


class RefreshStatus(ToolResult):
    mode: Literal["snapshot", "live"]
    last_checked: str | None  # the last run where every source answered
    schedule: Schedule
    last_run: LastRun | None
    message: str  # the status in plain words, for the answer


TRIGGER = {"button": "Check now", "chat": "a chat check", "schedule": "the schedule", "cli": "the command line"}
SOURCE = {"nvd": "NVD", "kev": "CISA KEV", "osv": "OSV", "epss": "EPSS"}


def _utc(iso: str) -> str:
    return dt.datetime.fromisoformat(iso).astimezone(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")


def _every(hours: int) -> str:
    return "every hour" if hours == 1 else f"every {hours} hours"


def _message(mode: str, last_checked, schedule: Schedule, last: LastRun | None, as_of: str) -> str:
    if mode == "snapshot":
        return (f"The data is a frozen snapshot as of {as_of}: nothing checks for updates, so the schedule doesn't "
                "run.")
    parts = [f"Last checked in full {_utc(last_checked)}." if last_checked else
             "Not checked in full yet: the live data is still the snapshot, or a run had a source missing."]
    if last:
        found = ", ".join(f"{n} {w}" for n, w in ((last.new, "new"), (last.kev_added, "added to KEV"),
                                                   (last.rescored, "rescored")) if n) or "nothing new"
        missing = f"; {', '.join(SOURCE.get(s, s) for s in last.failed_sources)} didn't answer" \
            if last.failed_sources else ""
        parts.append(f"The last run ({TRIGGER[last.trigger]}, {_utc(last.started)}) was {last.result}: "
                     f"{found}{missing}.")
    if schedule.paused:
        parts.append("The schedule is paused: no scheduled check starts until you resume it on Settings. "
                     "Check now still works.")
    elif schedule.next_due:
        parts.append(f"The schedule is on: {_every(schedule.hours)}, the next check from {_utc(schedule.next_due)}.")
    else:
        parts.append(f"The schedule is on: {_every(schedule.hours)}; the next tick runs a check.")
    return " ".join(parts)


def run(args: NoArgs, deps, ctx) -> dict:
    a = deps.state.settings().alerts  # the user's own schedule (per user with B09)
    refresher = deps.refresher
    due = schedule_due(refresher, a.schedule_hours) if refresher and not a.schedule_paused else None
    schedule = Schedule(hours=a.schedule_hours, paused=a.schedule_paused,
                        next_due=due.isoformat(timespec="seconds") if due else None)
    last = refresher.last_result() if refresher else None
    last_run = LastRun(trigger=last.trigger, started=last.started, result=last.status, new=last.counts.new,
                       kev_added=last.counts.kev_added, rescored=last.counts.rescored,
                       failed_sources=[f.source for f in last.feeds if not f.ok]) if last else None
    mode = deps.settings.data_mode
    last_checked = refresher.last_checked() if refresher else None
    return RefreshStatus(mode=mode, last_checked=last_checked, schedule=schedule, last_run=last_run,
                         message=_message(mode, last_checked, schedule, last_run, deps.as_of)).model_dump()


register(ToolSpec(
    name="refresh_status",
    description="When the CVE data was last checked for updates, whether the scheduled check is on or paused, "
                "and what the last check found. Reads only: it never starts a check.",
    args_model=NoArgs, result=RefreshStatus, run=run))

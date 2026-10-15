"""check_updates (B06, #39): "anything new since Monday?" Patch runs the refresh and says what it found.

The one refresh (app.refresh, `Refresher.run("chat")`): the same lock and 5-minute rule as Check now and the schedule.
Refused as too soon (or running), it answers from the last run, with when the next check is allowed. It needs no
confirmation: a refresh changes the shared CVE data, never the user's statuses or watchlist. Its output is wrapped as
untrusted like every tool's (agent.py).

It returns the run's counts, the new CVEs and the user's alerts from that run, each listed CVE a numbered source.
In snapshot mode there is nothing to fetch: it says so, with the snapshot's date, and never fails, so the model check
(which runs on the snapshot) gets the same answer every time.
"""
from typing import Literal

from pydantic import BaseModel

from app.alerts import DEFAULT_USER as ALERTS_USER
from app.config import DEFAULT_USER
from app.rag.chunking import chunk_cve
from app.rag.pipeline import to_source
from app.refresh import RefreshResult, schedule_status
from app.tools.registry import PriorityLevel, Severity, ToolResult, ToolSpec, register
from app.watched import WatchedCves

LISTED = 10  # new CVEs and alerts listed each; the counts give the totals
NOTE = ("What the feeds brought and the alerts the rules sent for this user. Explain them; don't add CVEs or "
        "alerts that aren't listed. Nothing here changed any CVE status or the watchlist.")
SNAPSHOT_NOTE = ("The data is a frozen snapshot, so there is nothing new to fetch. Say so, with its date; the app "
                 "checks the feeds only in live mode.")


class UpdatesArgs(BaseModel):
    """No arguments: the check is always the same."""


class UpdateCounts(ToolResult):
    new: int
    updated: int  # every changed record, the rescored and the KEV additions included
    kev_added: int
    rescored: int


class NewCve(ToolResult):
    n: int | None  # its source number; None when the CVE has since left the data
    id: str
    product: str | None
    severity: Severity | None
    kev: bool
    watched: bool  # its product is on the user's watchlist
    priority: PriorityLevel | None  # the rules' level; None off the watchlist


class UpdateAlert(ToolResult):
    n: int | None
    cve: str
    reason: str  # app.alerts.REASONS: kev, kev_recheck, new, new_unscored, now_critical, due_soon, overdue
    priority: int  # 5/4/3/2
    held: bool  # held through quiet hours: sent when they end


class UpdatesRefusal(ToolResult):
    reason: Literal["too_soon", "running", "snapshot"]
    next_allowed: str | None  # ISO 8601, UTC; None in snapshot mode
    message: str


class UpdatesSchedule(ToolResult):
    """B19: the scheduled check, as the user set it on Settings."""
    hours: int  # every N hours
    paused: bool  # paused: no scheduled check starts (this check and Check now still run)
    next_due: str | None  # ISO 8601, UTC; None when paused, in snapshot mode, or never checked (the next tick runs)


class UpdatesResult(ToolResult):
    """check_updates: this check, or the last one when refused, with what it found for this user."""
    mode: Literal["live", "snapshot"]
    as_of: str  # the data's date
    ran: bool  # this call ran a check
    refusal: UpdatesRefusal | None
    last_checked: str | None  # the reported run's start (ISO 8601, UTC); None before any run, or in snapshot mode
    trigger: str | None  # who started the reported run: button, chat, schedule, cli
    ok: bool | None  # True: the run wrote a new version; False: every feed failed and nothing changed
    status: Literal["ok", "partial", "failed"] | None  # B20: partial = some feeds failed, the rest was written
    problems: list[str]  # "source: message" for each failed feed or alert delivery
    counts: UpdateCounts
    new_cves: list[NewCve]  # the first LISTED, newest first
    alerts: list[UpdateAlert]  # the first LISTED, in the order sent (KEV and new before reminders)
    alerts_total: int
    schedule: UpdatesSchedule  # B19: "is the schedule on?"
    note: str


def _alerts_of(result: RefreshResult, user_id: str) -> list[dict]:
    """The user's alerts in the run, one per (CVE, reason), digests unpacked. The refresh keys the one local user as
    app.alerts' "default" until per-user state (B09) makes the ids one."""
    key = ALERTS_USER if user_id == DEFAULT_USER else user_id
    out: dict[tuple[str, str], dict] = {}
    for entry in result.alerts.get(key, []):
        for a in entry["alerts"]:
            out.setdefault((a["cve"], a["reason"]), {**a, "held": entry["kind"] == "held"})
    return list(out.values())


def run(args: UpdatesArgs, deps, ctx) -> dict:
    empty = {"last_checked": None, "trigger": None, "ok": None, "status": None, "problems": [],
             "counts": UpdateCounts(new=0, updated=0, kev_added=0, rescored=0).model_dump(), "new_cves": [],
             "alerts": [], "alerts_total": 0}
    empty["schedule"] = schedule_status(deps.refresher, deps.state.settings().alerts)  # B19
    if deps.refresher is None:
        return {"mode": "snapshot", "as_of": deps.as_of, "ran": False, **empty, "note": SNAPSHOT_NOTE,
                "refusal": {"reason": "snapshot", "next_allowed": None,
                            "message": f"The data is a frozen snapshot as of {deps.as_of}: nothing to check."}}
    reply = deps.refresher.run("chat")
    if reply.ran:
        deps.sync()  # the new CVEs are in the knowledge base before they're listed (as Check now does)
    base = {"mode": "live", "as_of": deps.as_of, "ran": reply.ran, "note": NOTE,
            "refusal": reply.refusal.model_dump() if reply.refusal else None}
    result = reply.result
    if result is None:  # refused before any run
        return {**base, **empty}

    k, watched = deps.knowledge, WatchedCves.of(deps)
    numbers: dict[str, int | None] = {}

    def source(cve_id: str) -> int | None:  # one numbered source per listed CVE
        if cve_id not in numbers:
            cve = k.cves.get(cve_id)
            numbers[cve_id] = None
            if cve is not None:
                s = to_source(len(ctx.sources) + 1, chunk_cve(cve, k.products[cve["product"]])[0], None)
                ctx.sources.append(s)
                numbers[cve_id] = s.n
        return numbers[cve_id]

    new_cves = []
    for cve_id in result.new_cves[:LISTED]:
        n, cve = source(cve_id), k.cves.get(cve_id)
        a = watched.assess(cve_id) if cve else None
        new_cves.append({"n": n, "id": cve_id, "product": k.products[cve["product"]] if cve else None,
                         "severity": cve["severity"] if cve else None, "kev": bool(k.cves.kev.get(cve_id)),
                         "watched": bool(a and a.watched),
                         "priority": a.priority.level if a and a.priority else None})
    alerts = _alerts_of(result, ctx.user_id)
    return {**base, "last_checked": result.started, "trigger": result.trigger, "ok": result.ok,
            "status": result.status,
            "problems": [f"{e.source}: {e.message}" for e in result.errors],
            "counts": result.counts.model_dump(), "new_cves": new_cves,
            "alerts": [{**a, "n": source(a["cve"])} for a in alerts[:LISTED]], "alerts_total": len(alerts),
            "schedule": schedule_status(deps.refresher, deps.state.settings().alerts)}  # after the run: its next due


register(ToolSpec(
    name="check_updates",
    description="Check the feeds now for what's new: new CVEs, KEV additions, rescored CVEs, and the alerts sent to "
                "the user. Use it when the user asks what's new, or for anything new since a day or a date. No "
                "arguments. At most one check per 5 minutes: a refused check returns the last check's results and "
                "when the next is allowed. It also says whether the scheduled check is on or paused and when it is "
                "next due, so use it for 'when did you last check?' and 'is the schedule on?' too. Cite the listed "
                "CVEs as [n]. It changes no CVE status.",
    args_model=UpdatesArgs,
    result=UpdatesResult,
    run=run,
))

"""Alerts (B04, spec #31 "Diff and alert rules", "Delivery"): what changed, what to alert, and sending it once.

Pure functions, with table tests (tests/test_alerts.py):
- `diff(previous, current)`: two live versions' files -> new CVEs, CVEs added to KEV, rescored CVEs, changed fixed
  versions.
- `rules(diff, rows, settings, as_of)`: the diff and one user's watched CVEs (WatchedCves rows: status, verdict,
  priority and due date at the as-of date) -> the alerts, as (CVE, reason, priority, de-duplication key).
- `first_check(alerts)` (B34): a user's first check sends what it found, and notes the reminders unsent.
- `in_quiet_hours(t, start, end)` and `digest(alerts, ...)`: when to hold, and one message for many.
- `alert_counts(entries)` (B34): one run's alerts by what happened: sent, recorded only, failed, held.

`Alerter` (below the pure part) runs them after a refresh for each user (B09): rules, de-duplicate against the
user's state, hold in quiet hours, digest above the limit, deliver and log the result per channel, and try a failed
channel again at the next check, at most 3 tries (B41, `still_true` drops what stopped being true). Only the owner's
alerts go to the channels (theirs, from the environment); other users' are recorded and shown in the app only.
"""
import datetime as dt
import uuid
import zoneinfo
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.knowledge import load_knowledge
from app.notify import Transports, format_alert, send_on
from app.times import iso_utc
from app.watched import WatchedCves


@dataclass(frozen=True)
class Diff:
    """What changed between two live versions. Ids in the new version's order (newest first)."""
    new: tuple[str, ...] = ()  # CVEs not in the previous version
    kev_added: dict[str, str] = field(default_factory=dict)  # CVE -> the date CISA added it
    rescored: dict[str, tuple[str | None, str | None]] = field(default_factory=dict)  # CVE -> (severity before, after)
    fixed_changed: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = field(default_factory=dict)  # (before, after)


def _fixed(osv_cves: dict, cve_id: str) -> tuple[str, ...]:
    return tuple(sorted({v for e in osv_cves.get(cve_id, []) for v in e.get("fixed") or []}))


def diff(previous: dict, current: dict) -> Diff:
    """Two live versions' files (LiveData.read()) -> what changed. A CVE added to KEV is one that is in the new
    KEV list and wasn't in the previous one, whenever it was published: KEV also adds old CVEs."""
    before = {r["id"]: r for r in previous["cves.json"]["cves"]}
    rows = current["cves.json"]["cves"]
    kev_before = {v["cveID"] for v in previous["kev.json"]}
    osv_before, osv_now = previous["osv.json"]["cves"], current["osv.json"]["cves"]
    rescored, fixed_changed = {}, {}
    for r in rows:
        old = before.get(r["id"])
        if old is None:
            continue
        if (old["severity"], old["cvss"]) != (r["severity"], r["cvss"]):
            rescored[r["id"]] = (old["severity"], r["severity"])
        if (was := _fixed(osv_before, r["id"])) != (now := _fixed(osv_now, r["id"])):
            fixed_changed[r["id"]] = (was, now)
    return Diff(new=tuple(r["id"] for r in rows if r["id"] not in before),
                kev_added={v["cveID"]: v["dateAdded"] for v in current["kev.json"] if v["cveID"] not in kev_before},
                rescored=rescored, fixed_changed=fixed_changed)


# --- The alert rules ------------------------------------------------------------------------------------------------

REASONS = ("kev", "kev_recheck", "new", "new_unscored", "now_critical", "due_soon", "overdue")
DUE_SOON_DAYS = 3
_SEVERITY = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


@dataclass(frozen=True)
class Alert:
    cve: str
    reason: str  # one of REASONS
    priority: int  # 5/4/3/2, from the CVE's priority (urgent, high, normal, low)
    key: str  # the de-duplication key: "CVE|reason", or "CVE|overdue|<ISO week>" so overdue repeats weekly


def _week(as_of: str) -> str:
    year, week, _ = dt.date.fromisoformat(as_of).isocalendar()
    return f"{year}-W{week:02d}"


def rules(d: Diff, rows: dict[str, dict], s, as_of: str) -> list[Alert]:
    """The reasons table (ALERTS-PLAN.md and its 2026-10-13 update) over one user's watched CVEs.

    `rows`: CVE id -> its WatchedCves row (status, verdict, open, due_date, overdue, alert_priority) at `as_of`;
    a CVE without a row isn't watched and never alerts. `s`: the user's AlertSettings.
    - kev: in the diff's KEV additions; skipped when the verdict or the status says not affected, or accepted.
    - kev_recheck: added to KEV while marked fixed.
    - new / new_unscored: new in the diff, at or above min_severity / with no severity yet; the same skips as kev.
    - now_critical: rescored from below critical to critical while open.
    - due_soon: open, not "not affected" by the verdict, and at most 3 days before its due date. Always on.
    - overdue: open, not "not affected" by the verdict, past its due date (the priority's overdue). Always on, keyed
      by ISO week, so it repeats once a week.
    Alerts off gives nothing. Order: the diff's reasons per CVE first, then due_soon and overdue.
    """
    if not s.enabled:
        return []
    out: list[Alert] = []

    def add(r: dict, reason: str, key: str | None = None) -> None:
        out.append(Alert(cve=r["id"], reason=reason, priority=r["alert_priority"], key=key or f"{r['id']}|{reason}"))

    def touches_you(r: dict) -> bool:  # kev and new skip what doesn't touch you
        return r["verdict"] != "not_affected" and r["status"] not in ("not_affected", "accepted")

    for cve_id in dict.fromkeys([*d.kev_added, *d.new, *d.rescored]):
        r = rows.get(cve_id)
        if r is None:
            continue
        if cve_id in d.kev_added:
            if r["status"] == "fixed":
                if s.kev_recheck:
                    add(r, "kev_recheck")
            elif s.kev and touches_you(r):
                add(r, "kev")
        if cve_id in d.new and touches_you(r):
            severity = _SEVERITY.get(r["severity"] or "")
            if severity is None:
                if s.unscored:
                    add(r, "new_unscored")
            elif severity >= _SEVERITY[s.min_severity]:
                add(r, "new")
        if cve_id in d.rescored and s.now_critical and r["open"]:
            before, after = d.rescored[cve_id]
            if after == "CRITICAL" and before != "CRITICAL":
                add(r, "now_critical")

    today = dt.date.fromisoformat(as_of)
    for r in rows.values():
        if not r["open"] or r["verdict"] == "not_affected" or not r["due_date"]:
            continue
        if r["overdue"]:
            add(r, "overdue", f"{r['id']}|overdue|{_week(as_of)}")
        elif 0 <= (dt.date.fromisoformat(r["due_date"]) - today).days <= DUE_SOON_DAYS:
            add(r, "due_soon")
    return out


REMINDERS = ("due_soon", "overdue")  # about a due date, not about something the check found


def first_check(alerts: list[Alert]) -> tuple[list[Alert], list[str]]:
    """B34: a user's first check sends only what it found (new CVEs, KEV additions, rescores), never reminders: a
    first alert of "272 overdue" teaches you to ignore alerts. -> (the alerts to send, the keys to note unsent).
    The reminders' keys are noted as if sent, so a second check soon after doesn't send them either: overdue comes
    back with next week's key, and a CVE that falls due later still gets its due_soon or overdue then."""
    return ([a for a in alerts if a.reason not in REMINDERS],
            [a.key for a in alerts if a.reason in REMINDERS])


# --- Quiet hours and the digest -------------------------------------------------------------------------------------

def in_quiet_hours(t: dt.time, start: str | None, end: str | None) -> bool:
    """Quiet hours run from `start` up to `end` ("HH:MM"), past midnight when start > end. Both are needed."""
    if not start or not end or start == end:
        return False
    a, b = dt.time.fromisoformat(start), dt.time.fromisoformat(end)
    return a <= t < b if a < b else t >= a or t < b


def batch(messages: list[dict], digest_over: int) -> list[list[dict]]:
    """The messages to send: each alert on its own, or every alert in one digest when there are more than
    `digest_over`."""
    return [messages] if len(messages) > digest_over else [[m] for m in messages]


DIGEST_WORDS = {"kev": "in CISA KEV", "kev_recheck": "to recheck", "new": "new", "new_unscored": "new, not scored",
                "now_critical": "now critical", "due_soon": "due soon", "overdue": "overdue"}


def digest(messages: list[dict], app_url: str) -> dict:
    """One message for many alerts: counts by reason, the highest priority, a link to the CVEs page. Like every
    alert, structured fields only; the ids are in the app, so a lock screen shows no more than counts."""
    counts: dict[str, int] = {}
    for m in messages:
        counts[m["reason"]] = counts.get(m["reason"], 0) + 1
    ordered = sorted(counts.items(), key=lambda x: REASONS.index(x[0]))
    words = [f"{n} {DIGEST_WORDS[r]}" for r, n in ordered]
    reminders = sum(n for r, n in ordered if r in REMINDERS)
    if 0 < reminders < len(messages):  # B34: it mixes kinds: what the check found, then the reminders as one count
        words = [f"{n} {DIGEST_WORDS[r]}" for r, n in ordered if r not in REMINDERS]
        words.append(f"{reminders} reminder{'' if reminders == 1 else 's'}")
    return {"title": f"{len(messages)} alerts for your watchlist", "body": " · ".join(words),
            "priority": max(m["priority"] for m in messages), "tags": ["digest"], "click": f"{app_url}/cves"}


# --- After a refresh: rules, de-duplicate, hold or send, log ---------------------------------------------------------

class Alerter:
    """The refresh's step 4 for each user (app.users.Users.ids: the owner and everyone with saved state): the
    alerts for what changed, sent once. After a good fetch it also keeps the diff's new CVEs as each user's "new since
    last check" (B05), whether alerts are on or not.

    The alerts log has one entry per message sent, newest first: `kind` "alert" (one alert, with its `cve` and
    `reason`) or "digest" (several, `cve` and `reason` None), `alerts` [{cve, reason, priority}], the message
    (`title`, `body`, `priority`, `tags`, `click`), `at`, `id` (B41), and `channels`: per channel, sent or failed
    with its error. A failed send is tried again at the next check (B41, `_retry`), and its channel's result in the
    entry says `tries`, `retry` (another try is due) and `dropped`.
    Alerts held in quiet hours come back in the run's result as kind "held", with no channels, and are logged when
    they are sent. Test alerts from Settings share the log as kind "test". Another user's entries have no channels
    and `in_app_only` true: nothing was sent, and quiet hours hold nothing for them.
    """

    def __init__(self, settings, users, transports: Callable[[], Transports]):
        self.settings, self.users, self.transports = settings, users, transports

    def __call__(self, previous: dict | None, current: dict | None, folder: Path | None,
                 now: dt.datetime, complete: bool = True) -> dict[str, list[dict]]:
        """`previous` and `current`: the live versions before and after the run, `folder` the current one's
        folder (None, None, None after a failed fetch: then only held alerts can go out). `complete` False: a
        partial run (B20), which doesn't count as a check for "new since last check". Per user id."""
        knowledge = load_knowledge(folder) if folder is not None else None
        changes = diff(previous, current) if current is not None and previous is not None else None
        return {user: self._for_user(user, self.users.state(user), changes, knowledge, now, complete)
                for user in self.users.ids()}

    def _for_user(self, user, state, changes: Diff | None, knowledge, now: dt.datetime,
                  complete: bool = True) -> list[dict]:
        at = iso_utc(now)
        first = changes is not None and not state.checked_before()  # B34: before this run notes it
        if changes is not None:  # B05: the CVEs page's "new since last check", alerts on or off
            state.note_new_cves(list(changes.new), at, complete)
        s = state.settings().alerts
        if not s.enabled:
            return []
        owner = user == self.settings.owner
        local = now.astimezone(zoneinfo.ZoneInfo(self.settings.alert_tz)).time()
        quiet = owner and in_quiet_hours(local, s.quiet_start, s.quiet_end)
        out = []
        if not quiet and (held := state.take_held_alerts()):
            out += self._send(state, [held], s, at, owner)  # quiet hours are over: what they held, as one message
        if changes is None or knowledge is None:
            return out
        as_of = now.astimezone(dt.UTC).date().isoformat()
        rows = {r["id"]: r for r in WatchedCves(knowledge, state, as_of).rows(status="all")}
        if not quiet:  # B41: quiet hours hold retries too
            out += self._retry(state, rows, s, as_of, at)
        alerts = rules(changes, rows, s, as_of)
        if first:
            alerts, noted = first_check(alerts)
            state.claim_alerts(noted, at)
        fresh = state.claim_alerts([a.key for a in alerts], at)
        messages = [{"cve": a.cve, "reason": a.reason, "key": a.key,
                     **format_alert(knowledge.cves.get(a.cve), a.reason, knowledge, self.settings.app_url,
                                    due=rows[a.cve])}
                    for a in alerts if a.key in fresh]
        if not messages:
            return out
        if quiet:
            state.hold_alerts(messages)
            return out + [_entry("held", [m], m, at, []) for m in messages]
        return out + self._send(state, batch(messages, s.digest_over), s, at, owner)

    def _send(self, state, groups: list[list[dict]], s, at: str, owner: bool) -> list[dict]:
        transports, out, retries = self.transports(), [], []
        for group in groups:
            one = len(group) == 1
            message = group[0] if one else digest(group, self.settings.app_url)
            if owner:
                channels = [_tried(send_on(c, message, self.settings, transports), 1) for c in s.channels]
                entry = _entry("alert" if one else "digest", group, message, at, channels) | {"id": uuid.uuid4().hex}
                if failed := [c["channel"] for c in channels if c.get("retry")]:
                    retries.append({"id": entry["id"], "kind": entry["kind"], "channels": failed, "tries": 1,
                                    "alerts": [_with_key(m, at) for m in group]})
                out.append(entry)
            else:  # the channels are the owner's: another user's alert stays in the app
                out.append(_entry("alert" if one else "digest", group, message, at, []) | {"in_app_only": True})
        state.log_alerts(out)  # on top of the log in the order sent: KEV and new CVEs above the reminders
        if retries:
            state.save_retries(state.retries() + retries)
        return out

    def _retry(self, state, rows: dict[str, dict], s, as_of: str, at: str) -> list[dict]:
        """B41: try each failed send again, on the channels that failed only, up to MAX_TRIES tries in all. An
        alert no longer true (`still_true`) is dropped from it; with none left, or none of its channels still
        picked, the retry is dropped. Each try updates its alerts-log entry in place, and comes back as this run's
        entry (`retry` true, the retried channels only), so the run's counts say what the retry did."""
        pending = state.retries()
        if not pending:
            return []
        transports, out, kept = self.transports(), [], []
        for r in pending:
            alerts = still_true(r["alerts"], rows, s, as_of)
            channels = [c for c in r["channels"] if c in s.channels]
            if not alerts or not channels:
                state.update_alert_channels(r["id"], [_dropped(c, r["tries"]) for c in r["channels"]])
                continue
            message = alerts[0] if len(alerts) == 1 else digest(alerts, self.settings.app_url)
            tries = r["tries"] + 1
            results = [_tried(send_on(c, message, self.settings, transports), tries) for c in channels]
            state.update_alert_channels(r["id"], results)
            out.append(_entry("alert" if len(alerts) == 1 else "digest", alerts, message, at, results)
                       | {"retry": True})
            if failed := [c["channel"] for c in results if c.get("retry")]:
                kept.append({**r, "alerts": alerts, "channels": failed, "tries": tries})
        state.save_retries(kept)
        return out


def alert_counts(entries: list[dict]) -> dict[str, int]:
    """B34: one run's alerts for one user (alerts-log entries), counted by what happened to each. Each alert in a
    digest counts. An alert is **sent** when at least one channel sent it (it reached you); else **failed** when a
    channel failed or wasn't set up; else **recorded only**: the dry run, no channel picked, or another user's alert
    (in the app only). **held**: kept for quiet hours. "Sent" never counts a dry run, so the line can't claim alerts
    went out that didn't."""
    out = {"sent": 0, "recorded": 0, "failed": 0, "held": 0}
    for e in entries:
        if e["kind"] == "held":
            out["held"] += len(e["alerts"]) or 1
            continue
        channels = e.get("channels", [])
        result = ("sent" if any(c["sent"] for c in channels) else
                  "failed" if any(c.get("error") for c in channels) else "recorded")
        out[result] += len(e["alerts"])
    return out


def _entry(kind: str, group: list[dict], message: dict, at: str, channels: list[dict]) -> dict:
    one = group[0] if len(group) == 1 else {}
    return {"at": at, "kind": kind, "cve": one.get("cve"), "reason": one.get("reason"),
            "alerts": [{"cve": m["cve"], "reason": m["reason"], "priority": m["priority"]} for m in group],
            **{k: message[k] for k in ("title", "body", "priority", "tags", "click")}, "channels": channels}


MAX_TRIES = 3  # B41: a failed send is tried again on the next checks, at most 3 tries in all


def _tried(result: dict, tries: int) -> dict:
    """B41: a channel's result with its try count. A failed send gets `retry` true while tries are left. A channel
    not set up isn't retried: nothing was tried, and it fails the same way until the owner sets it up."""
    if result["error_code"] != "notify_failed":
        return result if tries == 1 else result | {"tries": tries, "retry": False}
    return result | {"tries": tries, "retry": tries < MAX_TRIES}


def _dropped(channel: str, tries: int) -> dict:
    """B41: a retry dropped: no alert in it is still true (the CVE closed meanwhile), or the channel was unticked."""
    return {"channel": channel, "sent": False, "error": "Not tried again: no longer needed.",
            "error_code": "notify_failed", "tries": tries, "retry": False, "dropped": True}


def _with_key(message: dict, at: str) -> dict:
    """A message with its de-duplication key. Held messages saved before B41 have none: rebuilt as `rules` makes it,
    overdue by the ISO week of the send."""
    if "key" in message:
        return message
    week = f"|{_week(at[:10])}" if message["reason"] == "overdue" else ""
    return message | {"key": f"{message['cve']}|{message['reason']}{week}"}


def still_true(alerts: list[dict], rows: dict[str, dict], s, as_of: str) -> list[dict]:
    """B41: the alerts (messages with their `key`) that `rules` would still give today, so a retry never sends one
    that stopped being true: the CVE was closed (fixed, accepted, not affected; kev_recheck excepted, which is about
    a fixed CVE), unwatched, or its reason turned off.
    The diff that found them is gone, so each alert's own reason stands in for it; due_soon and overdue come from the
    rows, and overdue's key has its ISO week, so last week's reminder is never sent late."""
    found = Diff(new=tuple(a["cve"] for a in alerts if a["reason"] in ("new", "new_unscored")),
                 kev_added={a["cve"]: "" for a in alerts if a["reason"] in ("kev", "kev_recheck")},
                 rescored={a["cve"]: (None, "CRITICAL") for a in alerts if a["reason"] == "now_critical"})
    keys = {a.key for a in rules(found, rows, s, as_of)
            if a.reason == "kev_recheck" or rows[a.cve]["open"]}  # a new CVE marked fixed since: closed, not sent
    return [a for a in alerts if a["key"] in keys]

"""The refresh (B02, spec #31 "The refresh"): one function that every trigger calls.

Check now on the dashboard, the CLI (`uv run python -m app.refresh`), and later the chat's check_updates (B06) and
the schedule (B03) all call `Refresher.run(trigger)`. Its steps:

1. Fetch: NVD rows modified since the last check, the KEV catalogue, OSV by package, EPSS for every CVE.
2. Build with the shared code (app.cve_build), on top of the current live version.
3. Write the new live version (app.live_data). The server picks it up on its next request (Deps.sync).
4. For each user: diff, alert rules, de-duplicate, deliver, log (app.alerts, B04). After a failed fetch, only
   alerts held through quiet hours can go out.
5. Move `last_checked`, and log the run.

Each feed is its own step with its own result (B20). A feed that fails leaves its own data as it was; the feeds that
answered are built and written, and the run is "partial". Only when every feed fails is nothing written ("failed").
`last_checked` moves only when every feed answered, so the next run asks NVD again from there and covers the gap.
One lock (a file lock, so the CLI and the server share it) and at most one run per 5 minutes, whoever triggers it.
A refused run says when the next one is allowed, with the last run's result.
"""
import argparse
import contextlib
import datetime as dt
import fcntl
import json
import logging
import sys
import time
from collections.abc import Callable, Iterator, Sequence
from typing import Literal

from pydantic import BaseModel, model_validator

from app import cve_build
from app.config import DEFAULT_USER  # the alerts map is keyed by user id (B09)
from app.config import FIXTURES, Settings
from app.feeds import FeedError, Feeds, make_feeds
from app.live_data import LiveData
from app.store import LIVE_PREFIX, GcsStore, open_bucket
from app.times import iso_utc

log = logging.getLogger(__name__)

MIN_GAP = dt.timedelta(minutes=5)  # at most one run per 5 minutes, across every trigger (spec #31)
RUNS_KEPT = 20  # runs kept in the log
Trigger = Literal["button", "chat", "schedule", "cli"]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)



class Counts(BaseModel):
    new: int = 0  # CVEs not in the previous version
    updated: int = 0  # CVEs whose record changed (rescored and added to KEV included)
    kev_added: int = 0  # CVEs newly in CISA KEV
    rescored: int = 0  # CVEs whose severity or CVSS score changed


class FeedProblem(BaseModel):
    source: str  # nvd, kev, epss or osv
    message: str


class FeedResult(BaseModel):
    """One feed's step in a run (B20): it answered, or why it didn't."""
    source: str  # nvd, kev, osv or epss, in the order they are asked
    ok: bool
    message: str | None = None  # why it failed; None when it answered


Status = Literal["ok", "partial", "failed"]


class RefreshResult(BaseModel):
    """One run: what it found, or why it stopped."""
    trigger: str
    started: str  # ISO 8601, UTC
    finished: str
    ok: bool  # True: a version was written (every feed answered, or some did: see status). False: nothing written
    counts: Counts
    new_cves: list[str]  # the new CVEs' ids, newest first
    version: int | None  # the live version written; None when nothing was
    # the feeds that failed (ok False: every one did), and failed alerts ("alerts": the data was still written)
    errors: list[FeedProblem]
    alerts: dict[str, list[dict]] = {}  # per user id, this run's alerts-log entries, and those held (app.alerts)
    # B20: ok (every feed answered), partial (some did; their data was written) or failed (none did; nothing written).
    # Only the feeds decide it: a failed alert doesn't make a run partial.
    status: Status = "ok"
    feeds: list[FeedResult] = []  # each feed's step; empty in runs logged before B20

    @model_validator(mode="before")
    @classmethod
    def _status_of_older_runs(cls, data):
        """A run logged before B20 has no status: it was ok or failed."""
        if isinstance(data, dict) and "status" not in data:
            data = data | {"status": "ok" if data.get("ok") else "failed"}
        return data


class Refusal(BaseModel):
    reason: Literal["too_soon", "running"]
    next_allowed: str  # ISO 8601, UTC
    message: str


class CheckReply(BaseModel):
    """What a trigger gets back: this run's result, or a refusal with the last run's result (None before any run)."""
    ran: bool
    result: RefreshResult | None
    refusal: Refusal | None = None


# --- Step 2: build the new version on top of the previous one (pure) ------------------------------------------------

def build_version(previous: dict, nvd_rows: list[dict] | None, kev: dict | None, osv_raw: dict[str, list[dict]] | None,
                  epss_raw: dict | None, cwe_to_web: dict[str, str], now: dt.datetime) -> tuple[dict, Counts, list[str]]:
    """The previous version's files and the fetched data -> the new version's files, the counts and the new ids.

    A fetched NVD row replaces the CVE's record (or adds it); a row that is rejected or no longer names a tracked
    product drops it. KEV is joined again for every CVE, so an old CVE that CISA just added is marked too.
    A feed that failed is None (B20): its part of the previous version is kept as it was, and its retrieved date.
    """
    today = now.date().isoformat()
    before = {r["id"]: r for r in previous["cves.json"]["cves"]}
    # KEV failed: the previous version's KEV entries stand in for the catalogue
    catalogue = {v["cveID"]: v for v in (kev["vulnerabilities"] if kev is not None else previous["kev.json"])}
    records = {i: dict(r) for i, r in before.items()}
    for row in nvd_rows or []:
        rec = cve_build.cve_record(row, cwe_to_web, set(catalogue))
        if rec is None:
            records.pop(row["id"], None)
        else:
            records[row["id"]] = rec
    for r in records.values():
        r["kev"] = r["id"] in catalogue
    rows = sorted(records.values(), key=lambda r: (r["published"], r["id"]), reverse=True)
    kev_rows = [{k: catalogue[r["id"]].get(k) for k in cve_build.KEV_FIELDS} for r in rows if r["kev"]]
    ids = [r["id"] for r in rows]

    new = [i for i in ids if i not in before]
    kept = [i for i in ids if i in before]
    counts = Counts(
        new=len(new),
        updated=sum(records[i] != before[i] for i in kept),
        kev_added=sum(records[i]["kev"] and not before.get(i, {}).get("kev") for i in ids),
        rescored=sum((records[i]["severity"], records[i]["cvss"]) != (before[i]["severity"], before[i]["cvss"])
                     for i in kept),
    )

    old_epss, old_osv = previous["epss.json"], previous["osv.json"]
    epss = cve_build.epss_scores(epss_raw, ids) if epss_raw is not None else {"date": old_epss["date"], "scores": {}}
    old_scores = old_epss["scores"]
    scores = {i: epss["scores"].get(i) or old_scores[i] for i in sorted(ids) if i in epss["scores"] or i in old_scores}
    if osv_raw is not None:
        osv = cve_build.osv_versions(osv_raw, set(ids), today)
    else:  # OSV failed: the previous version's versions, for the CVEs still there
        osv = {"counts": old_osv["counts"], "cves": {i: v for i, v in old_osv["cves"].items() if i in records}}
    check = cve_build.product_check(rows, osv["cves"])

    manifest = json.loads(json.dumps(previous["manifest.json"]))
    manifest["as_of"] = today
    manifest["note"] = "Live data: the snapshot, refreshed from the feeds by app/refresh.py."
    manifest["product_check"] = check["counts"]
    refreshed = {  # a failed feed (None) keeps its count and retrieved date
        "nvd": {"count": len(rows)} if nvd_rows is not None else None,
        "kev": {"count": len(kev_rows), "name": f"CISA KEV {kev.get('catalogVersion')}"} if kev is not None else None,
        "osv": {"count": osv["counts"]["cves"], "as_of": today} if osv_raw is not None else None,
        "epss": {"count": len(scores), "as_of": epss["date"]} if epss_raw is not None else None,
    }
    for source in manifest["sources"]:
        if refreshed.get(source["id"]):
            source.update(refreshed[source["id"]], retrieved=today)

    files = {
        "cves.json": previous["cves.json"] | {"cves": rows},
        "kev.json": kev_rows,
        "epss.json": {"date": epss["date"], "retrieved": today if epss_raw is not None else old_epss["retrieved"],
                      "counts": {"scored": len(scores), "missing": len(ids) - len(scores)}, "scores": scores},
        "osv.json": old_osv | ({"as_of": today, "retrieved": today} if osv_raw is not None else {})
                    | {"counts": osv["counts"], "cves": osv["cves"]},
        "product_check.json": check,
        "manifest.json": manifest,
    }
    return files, counts, new


# --- The run ------------------------------------------------------------------------------------------------------

class Refresher:
    """The refresh over one live folder. `clock` gives the time (tests move it)."""

    def __init__(self, live: LiveData, feeds: Feeds, clock: Callable[[], dt.datetime] = utc_now,
                 alerter: Callable[..., dict[str, list[dict]]] | None = None):
        self.live, self.feeds, self.clock = live, feeds, clock
        self.alerter = alerter  # step 4 (app.alerts.Alerter); None: no alerts

    # The run log: last checked and the newest runs first, in refresh.json next to the versions. Shared by every user
    # (B09), so it lives in the live data's store.
    def _log(self) -> dict:
        return self.live.store.read("refresh.json")[0] or {"last_checked": None, "runs": []}

    def _save_log(self, data: dict) -> None:
        self.live.store.write("refresh.json", data)

    def _log_skip(self, log_data: dict, trigger: str, reason: str, now: dt.datetime, next_allowed: dt.datetime):
        """B19: a refused run, kept apart from `runs` so the 5-minute rule and the banner only ever see real runs.
        The same refusal again (same trigger, same next allowed time) counts up instead of adding a line."""
        skipped = log_data.setdefault("skipped", [])
        if skipped and (skipped[0]["trigger"], skipped[0]["next_allowed"]) == (trigger, iso_utc(next_allowed)):
            skipped[0]["times"] += 1
        else:
            skipped.insert(0, {"trigger": trigger, "started": iso_utc(now), "reason": reason,
                               "next_allowed": iso_utc(next_allowed), "times": 1})
        log_data["skipped"] = skipped[:RUNS_KEPT]
        self._save_log(log_data)

    def history(self, user_id: str = DEFAULT_USER) -> list[dict]:
        """B19: the last 20 runs and refusals, newest first, as the "Refresh runs" card shows them. The runs are
        shared (one refresh for everyone); the alert counts are `user_id`'s own (per user with B09)."""
        data = self._log()
        rows = [_run_row(RefreshResult.model_validate(r), user_id) for r in data["runs"]]
        rows += [{**_EMPTY_ROW, **s, "result": "skipped"} for s in data.get("skipped", [])]
        # in the same second, a skip comes after the run that made it too soon, so it goes above it
        return sorted(rows, key=lambda r: (r["started"], r["result"] == "skipped"), reverse=True)[:RUNS_KEPT]

    def last_checked(self) -> str | None:
        return self._log()["last_checked"]

    def last_result(self) -> RefreshResult | None:
        runs = self._log()["runs"]
        return RefreshResult.model_validate(runs[0]) if runs else None

    def next_allowed(self) -> dt.datetime | None:
        last = self.last_result()
        return dt.datetime.fromisoformat(last.started) + MIN_GAP if last else None

    @contextlib.contextmanager
    def _lock(self) -> Iterator[bool]:
        """The one lock: True when this caller holds it. A file lock, so a CLI run and the server share it."""
        self.live.root.mkdir(parents=True, exist_ok=True)
        with open(self.live.root / "refresh.lock", "w") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)

    def running(self) -> bool:
        with self._lock() as held:
            return not held

    def status(self) -> dict:
        nxt = self.next_allowed()
        last = self.last_result()
        return {"last_checked": self.last_checked(), "running": self.running(),
                "next_allowed": iso_utc(nxt) if nxt else None, "last_result": last.model_dump() if last else None}

    def _refuse(self, trigger: str, reason: str, now: dt.datetime, next_allowed: dt.datetime,
                log_data: dict | None) -> CheckReply:
        at = next_allowed.astimezone(dt.UTC).strftime("%H:%M UTC")
        message = (f"A check is running now. The next one is allowed at {at}." if reason == "running" else
                   f"Checked less than 5 minutes ago. The next check is allowed at {at}.")
        if log_data is not None:  # B19: the history shows it; "running" is left out (another run holds the log)
            self._log_skip(log_data, trigger, reason, now, next_allowed)
        return CheckReply(ran=False, result=self.last_result(),
                          refusal=Refusal(reason=reason, next_allowed=iso_utc(next_allowed), message=message))

    def run(self, trigger: Trigger) -> CheckReply:
        with self._lock() as held:
            now = self.clock()
            if not held:
                return self._refuse(trigger, "running", now, now + MIN_GAP, None)
            nxt = self.next_allowed()
            if nxt and now < nxt:
                return self._refuse(trigger, "too_soon", now, nxt, self._log())
            result = self._run(trigger, now)
            log_data = self._log()
            log_data["runs"] = [result.model_dump(), *log_data["runs"]][:RUNS_KEPT]
            if result.status == "ok":
                log_data["last_checked"] = result.started  # step 5; a run where any feed failed leaves it alone
            self._save_log(log_data)
        c = result.counts
        if result.ok:
            log.info("Refresh (%s) at %s: %d new, %d updated, %d added to KEV, %d rescored, version %s, %s",
                     trigger, result.started, c.new, c.updated, c.kev_added, c.rescored, result.version,
                     _took(result))
            if result.status == "partial":
                log.warning("Refresh (%s) at %s was partial: %d of %d sources updated; %s", trigger, result.started,
                            sum(f.ok for f in result.feeds), len(result.feeds),
                            "; ".join(f"{e.source}: {e.message}" for e in result.errors))
        else:
            log.warning("Refresh (%s) at %s failed after %s: %s", trigger, result.started, _took(result),
                        "; ".join(f"{e.source}: {e.message}" for e in result.errors))
        return CheckReply(ran=True, result=result)

    def _run(self, trigger: str, now: dt.datetime) -> RefreshResult:
        began = time.monotonic()
        previous = self.live.read()
        since = self.last_checked()
        start = dt.datetime.fromisoformat(since) if since else dt.datetime.fromisoformat(
            previous["manifest.json"]["as_of"]).replace(tzinfo=dt.UTC)
        steps: list[FeedResult] = []

        def fetch(source: str, call: Callable):
            """Step 1, one feed: its data, or None when it failed (recorded, and the other feeds still run)."""
            try:
                data = call()
            except Exception as e:  # any failure of this feed: its data stays as it was
                steps.append(FeedResult(source=source, ok=False,
                                        message=str(e) if isinstance(e, FeedError) else f"{type(e).__name__}: {e}"))
                return None
            steps.append(FeedResult(source=source, ok=True))
            return data

        nvd_rows = fetch("nvd", lambda: self.feeds.nvd_modified(start, now))
        kev = fetch("kev", self.feeds.kev)
        osv_raw = fetch("osv", lambda: {cve_build.package_key(e, n): self.feeds.osv(e, n)
                                        for p in cve_build.PACKAGES.values() for e, n in p["packages"]})
        ids = sorted({r["id"] for r in previous["cves.json"]["cves"]} | {r["id"] for r in nvd_rows or []})
        epss_raw = fetch("epss", lambda: self.feeds.epss(ids))
        failed = [FeedProblem(source=f.source, message=f.message or "") for f in steps if not f.ok]
        if len(failed) == len(steps):  # no feed answered: nothing to build, nothing written
            alerts, problems = self._alerts(None, None, None, now)  # quiet hours may have ended: held alerts go
            return self._result(trigger, now, began, ok=False, alerts=alerts, errors=[*failed, *problems],
                                feeds=steps)
        cwe_to_web = json.loads((FIXTURES / "owasp.json").read_text())["cwe_to_web"]
        files, counts, new = build_version(previous, nvd_rows, kev, osv_raw, epss_raw, cwe_to_web, now)  # step 2
        version = self.live.write(files)  # step 3
        alerts, problems = self._alerts(previous, files, self.live.folder(version), now,  # step 4, partial runs too
                                        complete=not failed)
        return self._result(trigger, now, began, ok=True, counts=counts, new_cves=new, version=version,
                            alerts=alerts, errors=[*failed, *problems], feeds=steps)

    def send_held(self) -> dict[str, list[dict]]:
        """Send what quiet hours held, if they are over, without fetching (a scheduled tick that isn't due)."""
        with self._lock() as held:
            return self._alerts(None, None, None, self.clock())[0] if held else {}

    def _alerts(self, previous, files, folder, now, complete: bool = True) -> tuple[dict[str, list[dict]],
                                                                                 list[FeedProblem]]:
        """Step 4. A failure here is logged and reported, but the new data stays written. `complete`: every feed
        answered, so the run moves last checked (B05 counts "new since last check" from those runs only)."""
        if self.alerter is None:
            return {}, []
        try:
            if complete:
                return self.alerter(previous, files, folder, now), []
            return self.alerter(previous, files, folder, now, complete=False), []
        except Exception as e:
            log.exception("Alerts after the refresh failed")
            return {}, [FeedProblem(source="alerts", message=f"{type(e).__name__}: {e}")]

    def _result(self, trigger, now, began, ok, counts=None, new_cves=(), version=None, errors=(),
                alerts=None, feeds=()) -> RefreshResult:
        finished = now + dt.timedelta(seconds=time.monotonic() - began)
        status = "failed" if not ok else "partial" if any(not f.ok for f in feeds) else "ok"  # the feeds decide
        return RefreshResult(trigger=trigger, started=iso_utc(now), finished=iso_utc(finished), ok=ok,
                             counts=counts or Counts(), new_cves=list(new_cves), version=version, errors=list(errors),
                             alerts=alerts or {}, status=status, feeds=list(feeds))

    def reset(self) -> None:
        """The fake feeds only: the live data back to the snapshot and an empty run log (the browser check)."""
        with self._lock():
            self.live.reset()
            self._save_log({"last_checked": None, "runs": [], "skipped": []})


_EMPTY_ROW = {"finished": None, "duration_s": None, "counts": None, "new_cves": [], "version": None, "feeds": [],
              "errors": [], "alerts_sent": 0, "alerts_held": 0, "reason": None, "next_allowed": None, "times": 1}


def _run_row(r: RefreshResult, user_id: str) -> dict:
    """One run as a history row (B19): its result (ok, partial, failed), how long it took, and the alerts it sent
    `user_id` (each alert in a digest counts) or held for quiet hours."""
    entries = r.alerts.get(user_id, [])
    sent = sum(len(e["alerts"]) for e in entries if e["kind"] in ("alert", "digest"))
    seconds = (dt.datetime.fromisoformat(r.finished) - dt.datetime.fromisoformat(r.started)).total_seconds()
    return {**_EMPTY_ROW, "trigger": r.trigger, "started": r.started, "finished": r.finished, "result": r.status,
            "duration_s": round(seconds, 1), "counts": r.counts.model_dump(), "new_cves": r.new_cves,
            "version": r.version, "feeds": [f.model_dump() for f in r.feeds],
            "errors": [e.model_dump() for e in r.errors], "alerts_sent": sent,
            "alerts_held": sum(e["kind"] == "held" for e in entries)}


def _took(result: RefreshResult) -> str:
    seconds = (dt.datetime.fromisoformat(result.finished) - dt.datetime.fromisoformat(result.started)).total_seconds()
    return f"{seconds:.1f} s"


def make_refresher(settings: Settings, feeds: Feeds | None = None, clock=utc_now, alerter=None,
                   bucket=None) -> Refresher:
    """STORE=gcs (B13): the live data is in the bucket under `live/`; LIVE_PATH is this instance's local copy."""
    b = open_bucket(settings, bucket)
    live = LiveData(settings.live_path, GcsStore(b, LIVE_PREFIX) if b is not None else None)
    return Refresher(live, feeds or make_feeds(settings), clock, alerter)


def cli_alerter(settings: Settings):
    """The CLI's alerts: the state file and the real channels, as the server's (app.deps)."""
    from app.alerts import Alerter
    from app.app_settings import default_dev_settings, default_settings
    from app.notify import Transports
    from app.users import Users

    users = Users.for_settings(settings, None, default_settings(settings), default_dev_settings(settings))
    return Alerter(settings, users, Transports)


# --- The schedule (B03): an hourly timer calls this; Settings' schedule_hours decides whether it runs ---------------

SCHEDULE_SLACK = dt.timedelta(minutes=10)  # a timer tick this early still counts, so 6 hours doesn't drift to 7


def schedule_due(refresher: Refresher, schedule_hours: int) -> dt.datetime | None:
    """When the scheduled refresh is next due: `schedule_hours` after the last good check (a failed run doesn't count,
    so the next tick tries again), less the slack. None: never checked, so due now."""
    last = refresher.last_checked()
    return dt.datetime.fromisoformat(last) + dt.timedelta(hours=schedule_hours) - SCHEDULE_SLACK if last else None


def schedule_status(refresher: Refresher | None, alerts) -> dict:
    """B19: the schedule as the owner set it (`alerts`: the owner's AlertSettings, B09: the refresh is shared, so
    the owner's Settings decide it): every N hours, paused or not, and when the next scheduled run is due (None:
    paused, snapshot mode, or never checked, so the next tick runs). The dashboard, Settings' "Refresh runs" card and
    check_updates all say it from here."""
    due = schedule_due(refresher, alerts.schedule_hours) if refresher and not alerts.schedule_paused else None
    return {"hours": alerts.schedule_hours, "paused": alerts.schedule_paused,
            "next_due": iso_utc(due) if due else None}


def run_scheduled(refresher: Refresher, schedule_hours: int, paused: bool = False) -> CheckReply | None:
    """The scheduled refresh: the same run as Check now, or None (skipped, nothing fetched) when it isn't due yet
    or the schedule is paused (B19). Either way, what quiet hours held still goes out: pausing stops the fetch, not
    the alerts already found."""
    if paused:
        log.info("Scheduled refresh skipped: the schedule is paused.")
        refresher.send_held()
        return None
    due = schedule_due(refresher, schedule_hours)
    if due and refresher.clock() < due:
        log.info("Scheduled refresh skipped: last checked %s, next due %s (every %d h).",
                 refresher.last_checked(), iso_utc(due), schedule_hours)
        refresher.send_held()  # B04: quiet hours may have ended since the last run
        return None
    return refresher.run("schedule")


def _schedule(settings: Settings):
    """The owner's alert settings: schedule_hours and schedule_paused (B19). The refresh is shared, so the owner's
    Settings decide it (B09)."""
    from app.app_settings import default_dev_settings, default_settings
    from app.users import Users

    users = Users.for_settings(settings, None, default_settings(settings), default_dev_settings(settings))
    return users.state(settings.owner).read().settings.alerts


def scheduled_tick(refresher: Refresher, alerts) -> dict:
    """One tick of the schedule, as the systemd timer's CLI (`--schedule`) and Cloud Scheduler's route (B13) both
    answer it. `alerts`: the owner's alert settings (schedule_hours, schedule_paused). The run's reply, or the skip:
    `{"ran": false, "skipped": "paused" | "not_due", ...}`."""
    hours = alerts.schedule_hours
    reply = run_scheduled(refresher, hours, alerts.schedule_paused)
    if reply is not None:
        return reply.model_dump()
    if alerts.schedule_paused:
        return {"ran": False, "skipped": "paused", "last_checked": refresher.last_checked(), "schedule_hours": hours}
    due = schedule_due(refresher, hours)
    return {"ran": False, "skipped": "not_due", "last_checked": refresher.last_checked(),
            "next_due": iso_utc(due) if due else None, "schedule_hours": hours}


def main(argv: Sequence[str] = ()) -> int:
    """`uv run python -m app.refresh`: one run, as Check now does it. Prints the reply as JSON.

    `--schedule` (the hourly systemd timer, deploy/systemd/): run only if Settings' schedule_hours have passed since
    the last check and the schedule isn't paused (B19); otherwise print the skip and exit 0.
    """
    parser = argparse.ArgumentParser(prog="python -m app.refresh", description="Refresh the live CVE data.")
    parser.add_argument("--schedule", action="store_true",
                        help="the scheduled run: skip unless the Settings schedule has passed since the last check")
    args = parser.parse_args(list(argv))
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    settings = Settings.from_env()
    settings.check()
    if settings.data_mode != "live":
        print("DATA_MODE is snapshot: the data is frozen. Set DATA_MODE=live to refresh it.", file=sys.stderr)
        return 2
    refresher = make_refresher(settings, alerter=cli_alerter(settings))
    if args.schedule:
        body = scheduled_tick(refresher, _schedule(settings))
        print(json.dumps(body, indent=1))
        if "skipped" in body:
            return 0
        reply = CheckReply.model_validate(body)
    else:
        reply = refresher.run("cli")
        print(reply.model_dump_json(indent=1))
    return 0 if reply.ran and reply.result and reply.result.status == "ok" else 1  # partial is 1 too: a feed failed


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

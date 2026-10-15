"""The refresh (B02, spec #31 "The refresh"): one function that every trigger calls.

Check now on the dashboard, the CLI (`uv run python -m app.refresh`), and later the chat's check_updates (B06) and
the schedule (B03) all call `Refresher.run(trigger)`. Its steps:

1. Fetch: NVD rows modified since the last check, the KEV catalogue, OSV by package, EPSS for every CVE.
2. Build with the shared code (app.cve_build), on top of the current live version.
3. Write the new live version (app.live_data). The server picks it up on its next request (Deps.sync).
4. (B04: for each user, diff, alert rules, de-duplicate, deliver, log.)
5. Move `last_checked`, and log the run.

A fetch failure stops before step 3: the data and `last_checked` stay as they were, so the next run covers the gap.
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

from pydantic import BaseModel

from app import cve_build
from app.config import FIXTURES, Settings
from app.feeds import FeedError, Feeds, make_feeds
from app.live_data import LiveData, write_json

log = logging.getLogger(__name__)

MIN_GAP = dt.timedelta(minutes=5)  # at most one run per 5 minutes, across every trigger (spec #31)
RUNS_KEPT = 20  # runs kept in the log
Trigger = Literal["button", "chat", "schedule", "cli"]


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def _iso(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).isoformat(timespec="seconds")


class Counts(BaseModel):
    new: int = 0  # CVEs not in the previous version
    updated: int = 0  # CVEs whose record changed (rescored and added to KEV included)
    kev_added: int = 0  # CVEs newly in CISA KEV
    rescored: int = 0  # CVEs whose severity or CVSS score changed


class FeedProblem(BaseModel):
    source: str  # nvd, kev, epss or osv
    message: str


class RefreshResult(BaseModel):
    """One run: what it found, or why it stopped."""
    trigger: str
    started: str  # ISO 8601, UTC
    finished: str
    ok: bool  # False: a fetch failed, nothing was written
    counts: Counts
    new_cves: list[str]  # the new CVEs' ids, newest first
    version: int | None  # the live version written; None when nothing was
    errors: list[FeedProblem]
    alerts: dict[str, list[dict]] = {}  # per user id, the alerts this run sent (B04 fills it)


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

def build_version(previous: dict, nvd_rows: list[dict], kev: dict, osv_raw: dict[str, list[dict]], epss_raw: dict,
                  cwe_to_web: dict[str, str], now: dt.datetime) -> tuple[dict, Counts, list[str]]:
    """The previous version's files and the fetched data -> the new version's files, the counts and the new ids.

    A fetched NVD row replaces the CVE's record (or adds it); a row that is rejected or no longer names a tracked
    product drops it. KEV is joined again for every CVE, so an old CVE that CISA just added is marked too.
    """
    today = now.date().isoformat()
    before = {r["id"]: r for r in previous["cves.json"]["cves"]}
    catalogue = {v["cveID"]: v for v in kev["vulnerabilities"]}
    records = {i: dict(r) for i, r in before.items()}
    for row in nvd_rows:
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

    epss = cve_build.epss_scores(epss_raw, ids)
    old_scores = previous["epss.json"]["scores"]
    scores = {i: epss["scores"].get(i) or old_scores[i] for i in sorted(ids) if i in epss["scores"] or i in old_scores}
    osv = cve_build.osv_versions(osv_raw, set(ids), today)
    check = cve_build.product_check(rows, osv["cves"])

    manifest = json.loads(json.dumps(previous["manifest.json"]))
    manifest["as_of"] = today
    manifest["note"] = "Live data: the snapshot, refreshed from the feeds by app/refresh.py."
    manifest["product_check"] = check["counts"]
    refreshed = {
        "nvd": {"count": len(rows)},
        "kev": {"count": len(kev_rows), "name": f"CISA KEV {kev.get('catalogVersion')}"},
        "osv": {"count": osv["counts"]["cves"], "as_of": today},
        "epss": {"count": len(scores), "as_of": epss["date"]},
    }
    for source in manifest["sources"]:
        if source["id"] in refreshed:
            source.update(refreshed[source["id"]], retrieved=today)

    files = {
        "cves.json": previous["cves.json"] | {"cves": rows},
        "kev.json": kev_rows,
        "epss.json": {"date": epss["date"], "retrieved": today,
                      "counts": {"scored": len(scores), "missing": len(ids) - len(scores)}, "scores": scores},
        "osv.json": previous["osv.json"] | {"as_of": today, "retrieved": today, "counts": osv["counts"],
                                            "cves": osv["cves"]},
        "product_check.json": check,
        "manifest.json": manifest,
    }
    return files, counts, new


# --- The run ------------------------------------------------------------------------------------------------------

class Refresher:
    """The refresh over one live folder. `clock` gives the time (tests move it)."""

    def __init__(self, live: LiveData, feeds: Feeds, clock: Callable[[], dt.datetime] = utc_now):
        self.live, self.feeds, self.clock = live, feeds, clock

    # The run log: last checked and the newest runs first, in refresh.json next to the versions.
    def _log(self) -> dict:
        path = self.live.root / "refresh.json"
        return json.loads(path.read_text()) if path.exists() else {"last_checked": None, "runs": []}

    def _save_log(self, data: dict) -> None:
        write_json(self.live.root / "refresh.json", data)

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
                "next_allowed": _iso(nxt) if nxt else None, "last_result": last.model_dump() if last else None}

    def _refuse(self, reason: str, next_allowed: dt.datetime) -> CheckReply:
        at = next_allowed.astimezone(dt.UTC).strftime("%H:%M UTC")
        message = (f"A check is running now. The next one is allowed at {at}." if reason == "running" else
                   f"Checked less than 5 minutes ago. The next check is allowed at {at}.")
        return CheckReply(ran=False, result=self.last_result(),
                          refusal=Refusal(reason=reason, next_allowed=_iso(next_allowed), message=message))

    def run(self, trigger: Trigger) -> CheckReply:
        with self._lock() as held:
            now = self.clock()
            if not held:
                return self._refuse("running", now + MIN_GAP)
            nxt = self.next_allowed()
            if nxt and now < nxt:
                return self._refuse("too_soon", nxt)
            result = self._run(trigger, now)
            log_data = self._log()
            log_data["runs"] = [result.model_dump(), *log_data["runs"]][:RUNS_KEPT]
            if result.ok:
                log_data["last_checked"] = result.started  # step 5; a failed fetch leaves it alone
            self._save_log(log_data)
        c = result.counts
        if result.ok:
            log.info("Refresh (%s) at %s: %d new, %d updated, %d added to KEV, %d rescored, version %s, %s",
                     trigger, result.started, c.new, c.updated, c.kev_added, c.rescored, result.version,
                     _took(result))
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
        source = "nvd"
        try:  # step 1: fetch
            nvd_rows = self.feeds.nvd_modified(start, now)
            source = "kev"
            kev = self.feeds.kev()
            source = "osv"
            osv_raw = {cve_build.package_key(e, n): self.feeds.osv(e, n)
                       for p in cve_build.PACKAGES.values() for e, n in p["packages"]}
            source = "epss"
            ids = sorted({r["id"] for r in previous["cves.json"]["cves"]} | {r["id"] for r in nvd_rows})
            epss_raw = self.feeds.epss(ids)
        except Exception as e:  # any feed failure: stop before writing anything
            message = str(e) if isinstance(e, FeedError) else f"{type(e).__name__}: {e}"
            return self._result(trigger, now, began, ok=False, errors=[FeedProblem(source=source, message=message)])
        cwe_to_web = json.loads((FIXTURES / "owasp.json").read_text())["cwe_to_web"]
        files, counts, new = build_version(previous, nvd_rows, kev, osv_raw, epss_raw, cwe_to_web, now)  # step 2
        version = self.live.write(files)  # step 3
        return self._result(trigger, now, began, ok=True, counts=counts, new_cves=new, version=version)

    def _result(self, trigger, now, began, ok, counts=None, new_cves=(), version=None, errors=()) -> RefreshResult:
        finished = now + dt.timedelta(seconds=time.monotonic() - began)
        return RefreshResult(trigger=trigger, started=_iso(now), finished=_iso(finished), ok=ok,
                             counts=counts or Counts(), new_cves=list(new_cves), version=version, errors=list(errors))

    def reset(self) -> None:
        """The fake feeds only: the live data back to the snapshot and an empty run log (the browser check)."""
        with self._lock():
            self.live.reset()
            self._save_log({"last_checked": None, "runs": []})


def _took(result: RefreshResult) -> str:
    seconds = (dt.datetime.fromisoformat(result.finished) - dt.datetime.fromisoformat(result.started)).total_seconds()
    return f"{seconds:.1f} s"


def make_refresher(settings: Settings, feeds: Feeds | None = None, clock=utc_now) -> Refresher:
    return Refresher(LiveData(settings.live_path), feeds or make_feeds(settings), clock)


# --- The schedule (B03): an hourly timer calls this; Settings' schedule_hours decides whether it runs ---------------

SCHEDULE_SLACK = dt.timedelta(minutes=10)  # a timer tick this early still counts, so 6 hours doesn't drift to 7


def schedule_due(refresher: Refresher, schedule_hours: int) -> dt.datetime | None:
    """When the scheduled refresh is next due: `schedule_hours` after the last good check (a failed run doesn't count,
    so the next tick tries again), less the slack. None: never checked, so due now."""
    last = refresher.last_checked()
    return dt.datetime.fromisoformat(last) + dt.timedelta(hours=schedule_hours) - SCHEDULE_SLACK if last else None


def run_scheduled(refresher: Refresher, schedule_hours: int) -> CheckReply | None:
    """The scheduled refresh: the same run as Check now, or None (skipped, nothing fetched) when it isn't due yet."""
    due = schedule_due(refresher, schedule_hours)
    if due and refresher.clock() < due:
        log.info("Scheduled refresh skipped: last checked %s, next due %s (every %d h).",
                 refresher.last_checked(), _iso(due), schedule_hours)
        return None
    return refresher.run("schedule")


def _schedule_hours(settings: Settings) -> int:
    from app.app_settings import default_settings
    from app.state import State

    return State(settings.state_path, None, default_settings(settings)).read().settings.alerts.schedule_hours


def main(argv: Sequence[str] = ()) -> int:
    """`uv run python -m app.refresh`: one run, as Check now does it. Prints the reply as JSON.

    `--schedule` (the hourly systemd timer, deploy/systemd/): run only if Settings' schedule_hours have passed since
    the last check; otherwise print the skip and exit 0.
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
    refresher = make_refresher(settings)
    if args.schedule:
        hours = _schedule_hours(settings)
        reply = run_scheduled(refresher, hours)
        if reply is None:
            due = schedule_due(refresher, hours)
            print(json.dumps({"ran": False, "skipped": "not_due", "last_checked": refresher.last_checked(),
                              "next_due": _iso(due) if due else None, "schedule_hours": hours}, indent=1))
            return 0
    else:
        reply = refresher.run("cli")
    print(reply.model_dump_json(indent=1))
    return 0 if reply.ran and reply.result and reply.result.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

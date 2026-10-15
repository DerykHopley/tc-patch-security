"""The Feeds adapter: the outside data the live refresh reads (spec #31 "Feeds").

One protocol with four calls. Each answers in the shape `app.cve_build` takes, so the refresh never sees a
service's own reply format:
- NVD: CVE rows modified between two dates, as in snapshot_raw/nvd_ai.json (id, published, status, description,
  cwes, score, severity, vendor_products).
- KEV: the whole catalogue, as CISA publishes it (`vulnerabilities`, `catalogVersion`).
- EPSS: `{"date", "rows": [{cve, epss, percentile, date}]}` for a list of CVE ids.
- OSV: the records for one package, as OSV.dev returns them.

`FakeFeeds` is the test fake (B02): snapshot_raw/ plus a day's data set from fixtures/fake_feeds/, no network.
The real one, over plain HTTP, is B03 (#36).
"""
import datetime as dt
import json
from typing import Protocol

from app.config import FIXTURES, ROOT

RAW = ROOT / "snapshot_raw"
FAKE_DAYS = FIXTURES / "fake_feeds"


class FeedError(RuntimeError):
    """A feed didn't answer properly. `source`: nvd, kev, epss or osv."""

    def __init__(self, source: str, message: str):
        super().__init__(message)
        self.source = source


class Feeds(Protocol):
    def nvd_modified(self, start: dt.datetime, end: dt.datetime) -> list[dict]: ...
    def kev(self) -> dict: ...
    def epss(self, cve_ids: list[str]) -> dict: ...
    def osv(self, ecosystem: str, name: str) -> list[dict]: ...


def _read(path):
    return json.loads(path.read_text())


class FakeFeeds:
    """What the four services say on `day` (1 or 2): the snapshot's raw downloads with that day's data set on top.

    NVD answers with the day's rows only (nothing else was modified since the snapshot), whatever the dates; the
    other three answer in full, as the real services do. `calls` records each call, for tests. `fail`: a source
    that raises FeedError, to test a failed fetch.
    """

    def __init__(self, day: int = 2, fail: str | None = None):
        self.day = day
        self.fail = fail
        self.calls: list[tuple] = []

    def _day(self) -> dict:
        return _read(FAKE_DAYS / f"day{self.day}.json")

    def _call(self, source: str, *args) -> dict:
        self.calls.append((source, *args))
        if self.fail == source:
            raise FeedError(source, f"The fake {source} feed is set to fail.")
        return self._day()

    def nvd_modified(self, start: dt.datetime, end: dt.datetime) -> list[dict]:
        return self._call("nvd", start, end)["nvd"]

    def kev(self) -> dict:
        day = self._call("kev")
        raw = _read(RAW / "kev.json")
        return raw | {"catalogVersion": day["catalogVersion"], "vulnerabilities": raw["vulnerabilities"] + day["kev"]}

    def epss(self, cve_ids: list[str]) -> dict:
        day = self._call("epss", tuple(cve_ids))
        wanted = set(cve_ids)
        rows = {r["cve"]: r for r in _read(RAW / "epss.json")["rows"]} | {r["cve"]: r for r in day["epss"]}
        return {"date": day["date"], "rows": [r for cve, r in rows.items() if cve in wanted]}

    def osv(self, ecosystem: str, name: str) -> list[dict]:
        key = f"{ecosystem}/{name}"
        day = self._call("osv", key)
        return _read(RAW / "osv.json")["packages"].get(key, []) + day["osv"].get(key, [])


def make_feeds(settings) -> Feeds:
    """The feeds FEEDS names. Only the fake for now (B02); B03 adds the real ones."""
    return FakeFeeds(day=settings.fake_feeds_day)

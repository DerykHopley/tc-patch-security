"""The Feeds adapter: the outside data the live refresh reads (spec #31 "Feeds").

One protocol with four calls. Each answers in the shape `app.cve_build` takes, so the refresh never sees a
service's own reply format:
- NVD: CVE rows modified between two dates, as in snapshot_raw/nvd_ai.json (id, published, status, description,
  cwes, score, severity, vendor_products).
- KEV: the whole catalogue, as CISA publishes it (`vulnerabilities`, `catalogVersion`).
- EPSS: `{"date", "rows": [{cve, epss, percentile, date}]}` for a list of CVE ids.
- OSV: the records for one package, as OSV.dev returns them.

`FakeFeeds` is the test fake (B02): snapshot_raw/ plus a day's data set from fixtures/fake_feeds/, no network.
`HttpFeeds` is the real one (B03, #36): plain HTTP with timeouts to fixed URLs; nothing a user types reaches them.
Facts relied on (windows, rate limits, batching) are in docs/SOURCE-CHECKS.md.
"""
import collections
import datetime as dt
import json
import re
import time
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass
from typing import Protocol

import httpx

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


# --- The real feeds (B03) ------------------------------------------------------------------------------------------

NVD_WINDOW = dt.timedelta(days=120)  # NVD's limit on lastModStartDate..lastModEndDate
NVD_PAGE = 2000  # NVD's largest resultsPerPage
NVD_PACE = 5, 50  # requests per 30 s without and with an API key
PACE_WINDOW = 30.0
USER_AGENT = "tc-patch-security/0.2 (+https://github.com/DerykHopley/tc-patch-security)"


@dataclass(frozen=True)
class FeedUrls:
    """Where the four services live. Fixed in code; tests point them at a local fake server."""
    nvd: str = "https://services.nvd.nist.gov/rest/json/cves/2.0"
    kev: str = "https://www.cisa.gov/sites/default/files/feeds/known_exploited_vulnerabilities.json"
    epss: str = "https://api.first.org/data/v1/epss"
    osv: str = "https://api.osv.dev/v1/query"

    @classmethod
    def at(cls, base: str) -> "FeedUrls":
        return cls(nvd=f"{base}/nvd", kev=f"{base}/kev", epss=f"{base}/epss", osv=f"{base}/osv")


def nvd_windows(start: dt.datetime, end: dt.datetime) -> list[tuple[dt.datetime, dt.datetime]]:
    """[start, end] in back-to-back windows of at most 120 days, so a long gap is still covered."""
    out = []
    while start < end:
        out.append((start, min(start + NVD_WINDOW, end)))
        start = out[-1][1]
    return out


def _nvd_time(t: dt.datetime) -> str:
    return t.astimezone(dt.UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def nvd_row(vuln: dict) -> dict:
    """One NVD API 2.0 record -> the snapshot's raw row (snapshot_raw/nvd_ai.json), as feasibility/fetch.py made it."""
    c = vuln["cve"]
    desc = next((d["value"] for d in c.get("descriptions", []) if d.get("lang") == "en"), "")
    cwes = sorted({d["value"] for w in c.get("weaknesses", []) for d in w.get("description", [])
                   if d.get("value", "").startswith("CWE-")})
    score = severity = None
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30"):
        if c.get("metrics", {}).get(key):
            data = c["metrics"][key][0]["cvssData"]
            score, severity = data.get("baseScore"), data.get("baseSeverity")
            break
    cpes = sorted({":".join(m["criteria"].split(":")[3:5]) for cfg in c.get("configurations", [])
                   for n in cfg.get("nodes", []) for m in n.get("cpeMatch", [])})
    return {"id": c["id"], "published": c["published"], "lastModified": c.get("lastModified"),
            "status": c.get("vulnStatus"), "description": desc, "cwes": cwes, "score": score,
            "severity": severity, "vendor_products": cpes[:20]}


class Pacer:
    """At most `limit` requests in any `window` seconds: waits (with `sleep`) before a request that would break it."""

    def __init__(self, limit: int, window: float, clock: Callable[[], float], sleep: Callable[[float], None]):
        self.limit, self.window, self.clock, self.sleep = limit, window, clock, sleep
        self.sent: collections.deque[float] = collections.deque()

    def wait(self) -> None:
        if len(self.sent) >= self.limit:
            pause = self.sent[0] + self.window - self.clock()
            if pause > 0:
                self.sleep(pause)
            self.sent.popleft()
        self.sent.append(self.clock())


class HttpFeeds:
    """The four services over plain HTTP. Any failure (timeout, refused, an HTTP error, a reply we can't read) is a
    FeedError naming the source. No retries: the refresh stops before writing, and the next run covers the gap.

    `nvd_api_key` (optional) raises NVD's pace from 5 to 50 requests per 30 s. `clock` and `sleep` pace NVD; tests
    pass fakes.
    """

    def __init__(self, nvd_api_key: str = "", timeout: float = 30.0, urls: FeedUrls = FeedUrls(),
                 clock: Callable[[], float] = time.monotonic, sleep: Callable[[float], None] = time.sleep):
        self.nvd_api_key, self.urls, self.timeout = nvd_api_key, urls, timeout
        self.client = httpx.Client(timeout=timeout, headers={"User-Agent": USER_AGENT}, follow_redirects=False)
        self.nvd_pacer = Pacer(NVD_PACE[1] if nvd_api_key else NVD_PACE[0], PACE_WINDOW, clock, sleep)

    def _json(self, source: str, method: str, url: str, **kw):
        name = source.upper()
        try:
            reply = self.client.request(method, url, **kw)
        except httpx.TimeoutException:
            raise FeedError(source, f"{name} didn't answer within {self.timeout:g} s.") from None
        except httpx.HTTPError as e:
            raise FeedError(source, f"{name} couldn't be reached ({type(e).__name__}).") from None
        if reply.status_code != 200:
            raise FeedError(source, f"{name} answered HTTP {reply.status_code}.")
        try:
            return reply.json()
        except ValueError:
            raise FeedError(source, f"{name} answered with something that isn't JSON.") from None

    def nvd_modified(self, start: dt.datetime, end: dt.datetime) -> list[dict]:
        headers = {"apiKey": self.nvd_api_key} if self.nvd_api_key else {}
        rows = []
        for a, b in nvd_windows(start, end):
            index = 0
            while True:
                self.nvd_pacer.wait()
                page = self._json("nvd", "GET", self.urls.nvd, headers=headers, params={
                    "lastModStartDate": _nvd_time(a), "lastModEndDate": _nvd_time(b),
                    "resultsPerPage": NVD_PAGE, "startIndex": index})
                try:
                    vulns = page["vulnerabilities"]
                    rows += [nvd_row(v) for v in vulns]
                    total = int(page["totalResults"])
                except (KeyError, TypeError, ValueError, IndexError) as e:
                    raise FeedError("nvd", f"NVD's reply has an unexpected shape ({type(e).__name__}: {e}).") from None
                index += len(vulns)
                if not vulns or index >= total:
                    break
        return rows

    def kev(self) -> dict:
        catalogue = self._json("kev", "GET", self.urls.kev)
        if not isinstance(catalogue, dict) or not isinstance(catalogue.get("vulnerabilities"), list):
            raise FeedError("kev", "KEV's reply has no list of vulnerabilities.")
        return catalogue

    def epss(self, cve_ids: list[str], date: str | None = None) -> dict:
        """The latest scores (or as of `date`, for the snapshot build). Only well-formed CVE ids go in the URL."""
        rows = []
        for batch in epss_batches([i for i in cve_ids if CVE_ID.fullmatch(i)]):
            query = urllib.parse.urlencode({**({"date": date} if date else {}), "limit": len(batch)})
            reply = self._json("epss", "GET", f"{self.urls.epss}?{query}&cve={','.join(batch)}")
            if not isinstance(reply, dict) or not isinstance(reply.get("data"), list):
                raise FeedError("epss", "EPSS's reply has no data list.")
            rows += reply["data"]
        today = dt.datetime.now(dt.UTC).date().isoformat()
        latest = max((r.get("date", "") for r in rows), default="") or date or today
        return {"date": latest, "rows": rows}

    def osv(self, ecosystem: str, name: str) -> list[dict]:
        """Every record for one package, page by page, trimmed to what the build reads."""
        records, body = [], {"package": {"ecosystem": ecosystem, "name": name}}
        while True:
            reply = self._json("osv", "POST", self.urls.osv, json=body)
            try:
                records += [osv_trim(v) for v in reply.get("vulns", [])]
            except (KeyError, TypeError, AttributeError) as e:
                raise FeedError("osv", f"OSV's reply has an unexpected shape ({type(e).__name__}: {e}).") from None
            if not reply.get("next_page_token"):
                return records
            body = {**body, "page_token": reply["next_page_token"]}


CVE_ID = re.compile(r"CVE-\d{4}-\d{4,}")
EPSS_MAX_CVE_CHARS = 2000  # EPSS's limit on the comma-separated cve= list


def epss_batches(cve_ids: list[str]) -> list[list[str]]:
    """As few batches as the 2,000-character cve= limit allows, in order."""
    batches, batch = [], []
    for cve in cve_ids:
        if batch and len(",".join(batch + [cve])) > EPSS_MAX_CVE_CHARS:
            batches.append(batch)
            batch = []
        batch.append(cve)
    return batches + [batch] if batch else batches


def osv_trim(record: dict) -> dict:
    """Keep what the build reads. The `versions` lists can run to hundreds of entries per package."""
    out = {k: record[k] for k in ("id", "aliases", "published", "modified", "withdrawn") if k in record}
    out.setdefault("aliases", [])
    out["affected"] = [{"package": {"ecosystem": a["package"]["ecosystem"], "name": a["package"]["name"]},
                        "ranges": a.get("ranges", [])} for a in record.get("affected", []) if "package" in a]
    return out


def make_feeds(settings) -> Feeds:
    """The feeds FEEDS names: the fake (B02, the default) or the real services (B03)."""
    if settings.feeds == "real":
        return HttpFeeds(nvd_api_key=settings.nvd_api_key)
    return FakeFeeds(day=settings.fake_feeds_day)

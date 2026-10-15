"""The real Feeds adapter (B03, #36), against a local fake HTTP server: never the real services. Check ids: B03.n.

Seam: the Feeds protocol (`app.feeds.HttpFeeds`), as the refresh calls it. Each test points the adapter at the fake
server and gives it a fake clock whose sleep moves time on, so pacing is checked without waiting.
"""
import datetime as dt

import pytest

from app.feeds import FeedError, FeedUrls, HttpFeeds

UTC = dt.UTC


class FakeTime:
    """monotonic() and sleep() for the adapter: sleeping moves the time on at once."""

    def __init__(self):
        self.now = 0.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


@pytest.fixture
def time_():
    return FakeTime()


def feeds_for(fake_http, time_, **kw) -> HttpFeeds:
    fake_http.clock = time_
    return HttpFeeds(urls=FeedUrls.at(fake_http.url), clock=time_, sleep=time_.sleep, **kw)


def nvd_vuln(cve_id: str, product: str = "langflow:langflow", status: str = "Analyzed") -> dict:
    """One CVE as NVD API 2.0 returns it (the fields we read)."""
    vendor, name = product.split(":")
    return {"cve": {
        "id": cve_id, "published": "2026-10-14T08:15:00.000", "lastModified": "2026-10-15T06:40:00.000",
        "vulnStatus": status,
        "descriptions": [{"lang": "es", "value": "Otro texto."},
                         {"lang": "en", "value": "Langflow  lets a user run code."}],
        "weaknesses": [{"description": [{"lang": "en", "value": "CWE-94"}, {"lang": "en", "value": "NVD-CWE-noinfo"}]}],
        "metrics": {"cvssMetricV31": [{"cvssData": {"baseScore": 9.1, "baseSeverity": "CRITICAL"}}]},
        "configurations": [{"nodes": [{"cpeMatch": [{"criteria": f"cpe:2.3:a:{vendor}:{name}:*:*:*:*:*:*:*:*"}]}]}],
    }}


def nvd_pages(by_window: dict[str, list[dict]], page_size: int = 2000):
    """An NVD handler: the vulnerabilities for each lastModStartDate, paged by startIndex."""
    def handler(seen):
        vulns = by_window.get(seen.query["lastModStartDate"], [])
        start = int(seen.query.get("startIndex", 0))
        size = min(page_size, int(seen.query["resultsPerPage"]))
        return 200, {"resultsPerPage": len(vulns[start:start + size]), "startIndex": start,
                     "totalResults": len(vulns), "vulnerabilities": vulns[start:start + size]}
    return handler


# --- B03.1: NVD's modified-since query in windows of at most 120 days, every page ---------------------------------

def test_b03_1_nvd_splits_a_long_gap_into_120_day_windows_and_reads_every_page(fake_http, time_):
    fake_http.on("/nvd", nvd_pages({
        "2026-01-01T00:00:00.000Z": [nvd_vuln("CVE-2026-0001")],
        "2026-05-01T00:00:00.000Z": [nvd_vuln("CVE-2026-0002"), nvd_vuln("CVE-2026-0003"),
                                     nvd_vuln("CVE-2026-0004")],
        "2026-08-29T00:00:00.000Z": [nvd_vuln("CVE-2026-0005", status="Rejected")],
    }, page_size=2))
    feeds = feeds_for(fake_http, time_)

    rows = feeds.nvd_modified(dt.datetime(2026, 1, 1, tzinfo=UTC), dt.datetime(2026, 10, 15, 9, 30, tzinfo=UTC))

    windows = [(s.query["lastModStartDate"], s.query["lastModEndDate"], s.query["startIndex"])
               for s in fake_http.hits("/nvd")]
    assert windows == [  # 287 days: three windows, the middle one on two pages
        ("2026-01-01T00:00:00.000Z", "2026-05-01T00:00:00.000Z", "0"),
        ("2026-05-01T00:00:00.000Z", "2026-08-29T00:00:00.000Z", "0"),
        ("2026-05-01T00:00:00.000Z", "2026-08-29T00:00:00.000Z", "2"),
        ("2026-08-29T00:00:00.000Z", "2026-10-15T09:30:00.000Z", "0"),
    ]
    assert all(s.query["resultsPerPage"] == "2000" for s in fake_http.hits("/nvd"))
    assert [r["id"] for r in rows] == ["CVE-2026-0001", "CVE-2026-0002", "CVE-2026-0003", "CVE-2026-0004",
                                       "CVE-2026-0005"]
    assert rows[0] == {  # the snapshot's raw row shape (snapshot_raw/nvd_ai.json), as app.cve_build reads it
        "id": "CVE-2026-0001", "published": "2026-10-14T08:15:00.000", "lastModified": "2026-10-15T06:40:00.000",
        "status": "Analyzed", "description": "Langflow  lets a user run code.", "cwes": ["CWE-94"],
        "score": 9.1, "severity": "CRITICAL", "vendor_products": ["langflow:langflow"]}
    assert rows[4]["status"] == "Rejected"  # passed on: the build drops it


# --- B03.2: NVD paced to 5 requests per 30 s, or 50 with a key ------------------------------------------------------

def _many_pages(fake_http, pages: int):
    fake_http.on("/nvd", nvd_pages({"2026-10-13T00:00:00.000Z": [nvd_vuln(f"CVE-2026-{i:04d}")
                                                                 for i in range(pages)]}, page_size=1))


def test_b03_2_nvd_without_a_key_sends_at_most_5_requests_in_any_30_seconds(fake_http, time_):
    _many_pages(fake_http, 12)
    feeds = feeds_for(fake_http, time_)

    rows = feeds.nvd_modified(dt.datetime(2026, 10, 13, tzinfo=UTC), dt.datetime(2026, 10, 15, tzinfo=UTC))

    assert len(rows) == 12
    assert [s.at for s in fake_http.hits("/nvd")] == [0.0] * 5 + [30.0] * 5 + [60.0] * 2
    assert all("apikey" not in s.headers for s in fake_http.hits("/nvd"))


def test_b03_2_nvd_with_a_key_sends_it_and_may_send_50_in_30_seconds(fake_http, time_):
    _many_pages(fake_http, 52)
    feeds = feeds_for(fake_http, time_, nvd_api_key="test-key")

    feeds.nvd_modified(dt.datetime(2026, 10, 13, tzinfo=UTC), dt.datetime(2026, 10, 15, tzinfo=UTC))

    assert [s.at for s in fake_http.hits("/nvd")] == [0.0] * 50 + [30.0] * 2
    assert {s.headers["apikey"] for s in fake_http.hits("/nvd")} == {"test-key"}


# --- B03.3: the KEV catalogue --------------------------------------------------------------------------------------

def test_b03_3_kev_is_the_whole_catalogue_as_cisa_publishes_it(fake_http, time_):
    catalogue = {"catalogVersion": "2026.10.15", "count": 1,
                 "vulnerabilities": [{"cveID": "CVE-2024-37014", "dateAdded": "2026-10-15"}]}
    fake_http.on("/kev", lambda seen: (200, catalogue))

    assert feeds_for(fake_http, time_).kev() == catalogue
    assert fake_http.hits("/kev")[0].method == "GET"


# --- B03.4: EPSS batched under 2,000 characters a query ------------------------------------------------------------

def epss_handler(seen):
    ids = seen.query["cve"].split(",")
    return 200, {"status": "OK", "total": len(ids), "offset": 0, "limit": int(seen.query["limit"]),
                 "data": [{"cve": i, "epss": "0.01", "percentile": "0.5", "date": "2026-10-15"} for i in ids]}


def test_b03_4_epss_asks_for_every_cve_in_batches_of_at_most_2000_characters(fake_http, time_):
    fake_http.on("/epss", epss_handler)
    ids = [f"CVE-2026-{10000 + i}" for i in range(300)]  # 14 characters each: 300 make 4,499 with commas

    reply = feeds_for(fake_http, time_).epss(ids)

    batches = [s.query["cve"].split(",") for s in fake_http.hits("/epss")]
    assert len(batches) == 3
    assert all(len(",".join(b)) <= 2000 for b in batches)
    assert [i for b in batches for i in b] == ids
    assert [int(s.query["limit"]) for s in fake_http.hits("/epss")] == [len(b) for b in batches]  # no 100-row cut
    assert "date" not in fake_http.hits("/epss")[0].query  # live: the latest scores
    assert reply["date"] == "2026-10-15"
    assert [r["cve"] for r in reply["rows"]] == ids


def test_b03_4_epss_as_of_a_date_and_only_well_formed_cve_ids_in_the_url(fake_http, time_):
    fake_http.on("/epss", epss_handler)

    feeds_for(fake_http, time_).epss(["CVE-2025-3248", "CVE-2025-1&x=1", "not-a-cve"], date="2026-10-13")

    assert [(s.query["cve"], s.query["date"]) for s in fake_http.hits("/epss")] == [("CVE-2025-3248", "2026-10-13")]


# --- B03.5: OSV by package ------------------------------------------------------------------------------------------

def test_b03_5_osv_queries_one_package_reads_every_page_and_keeps_what_the_build_reads(fake_http, time_):
    record = {"id": "GHSA-aaaa", "aliases": ["CVE-2026-0001"], "published": "2026-10-01T00:00:00Z",
              "modified": "2026-10-02T00:00:00Z", "details": "Long text the build doesn't read.",
              "affected": [{"package": {"ecosystem": "PyPI", "name": "langflow", "purl": "pkg:pypi/langflow"},
                            "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.3.0"}]}],
                            "versions": ["1.0", "1.1", "1.2"]}]}

    def handler(seen):
        if "page_token" not in seen.body:
            return 200, {"vulns": [record], "next_page_token": "p2"}
        return 200, {"vulns": [{"id": "PYSEC-bbbb", "affected": [{"package": {"ecosystem": "PyPI",
                                                                              "name": "langflow"}}]}]}
    fake_http.on("/osv", handler)

    records = feeds_for(fake_http, time_).osv("PyPI", "langflow")

    assert [s.body for s in fake_http.hits("/osv")] == [
        {"package": {"ecosystem": "PyPI", "name": "langflow"}},
        {"package": {"ecosystem": "PyPI", "name": "langflow"}, "page_token": "p2"}]
    assert records == [
        {"id": "GHSA-aaaa", "aliases": ["CVE-2026-0001"], "published": "2026-10-01T00:00:00Z",
         "modified": "2026-10-02T00:00:00Z",
         "affected": [{"package": {"ecosystem": "PyPI", "name": "langflow"},
                       "ranges": [{"type": "ECOSYSTEM", "events": [{"introduced": "0"}, {"fixed": "1.3.0"}]}]}]},
        {"id": "PYSEC-bbbb", "aliases": [],
         "affected": [{"package": {"ecosystem": "PyPI", "name": "langflow"}, "ranges": []}]}]


# --- B03.6: a timeout, an HTTP error or a bad reply is a FeedError, and the refresh writes nothing ----------------

@pytest.mark.parametrize("handler, message", [
    (lambda seen: (503, {"message": "Service Unavailable"}), "NVD answered HTTP 503."),
    (lambda seen: (403, "Forbidden"), "NVD answered HTTP 403."),
    (lambda seen: (200, "<html>maintenance</html>"), "NVD answered with something that isn't JSON."),
    (lambda seen: (200, {"vulnerabilities": [{"cve": {}}], "totalResults": 1}), "NVD's reply has an unexpected"),
    (lambda seen: (200, {}, 1.0), "NVD didn't answer within 0.2 s."),
])
def test_b03_6_a_failed_nvd_call_is_a_feed_error_naming_the_source(fake_http, time_, handler, message):
    fake_http.on("/nvd", handler)
    feeds = feeds_for(fake_http, time_, timeout=0.2)

    with pytest.raises(FeedError) as e:
        feeds.nvd_modified(dt.datetime(2026, 10, 13, tzinfo=UTC), dt.datetime(2026, 10, 15, tzinfo=UTC))

    assert e.value.source == "nvd" and str(e.value).startswith(message)


def test_b03_6_a_service_that_is_down_is_a_feed_error(time_):
    feeds = HttpFeeds(urls=FeedUrls.at("http://127.0.0.1:9"), clock=time_, sleep=time_.sleep, timeout=1)  # discard port

    with pytest.raises(FeedError) as e:
        feeds.kev()

    assert e.value.source == "kev" and "couldn't be reached" in str(e.value)


def _all_four(fake_http, nvd=None):
    fake_http.on("/nvd", nvd or nvd_pages({}))
    fake_http.on("/kev", lambda seen: (200, {"catalogVersion": "2026.10.15", "vulnerabilities": []}))
    fake_http.on("/epss", epss_handler)
    fake_http.on("/osv", lambda seen: (200, {"vulns": []}))


@pytest.fixture
def refresher(tmp_path, fake_http, time_):
    """The real refresh over its own live folder, the real Feeds adapter pointed at the fake server, at 09:00."""
    from app.live_data import LiveData
    from app.refresh import Refresher

    class Clock:
        at = dt.datetime(2026, 10, 15, 9, tzinfo=UTC)

        def __call__(self):
            return self.at

    feeds = feeds_for(fake_http, time_, timeout=0.2)
    return Refresher(LiveData(tmp_path / "live"), feeds, Clock())


@pytest.mark.parametrize("failing", ["nvd", "kev", "epss", "osv"])
@pytest.mark.parametrize("how", ["503", "timeout"])
def test_b03_6_a_503_or_timeout_leaves_the_data_and_last_checked_alone_and_the_next_run_covers_the_gap(
        fake_http, refresher, caplog, failing, how):
    _all_four(fake_http)
    first = refresher.run("schedule").result
    assert first.ok and first.version == 2

    _all_four(fake_http, nvd=nvd_pages({"2026-10-15T09:00:00.000Z": [nvd_vuln("CVE-2026-99201")]}))
    fake_http.on(f"/{failing}", (lambda s: (503, {})) if how == "503" else (lambda s: (200, {}, 1.0)))
    refresher.clock.at += dt.timedelta(hours=6)
    with caplog.at_level("WARNING", logger="app.refresh"):
        failed = refresher.run("schedule").result

    # B20: one feed down is a partial run. The other three are written; the failed one's data and last_checked stay.
    assert failed.status == "partial" and failed.version == 3 and [e.source for e in failed.errors] == [failing]
    assert "was partial: 3 of 4 sources updated" in caplog.text and f"{failing}: {failing.upper()} " in caplog.text
    assert refresher.live.version() == 3
    assert refresher.last_checked() == "2026-10-15T09:00:00+00:00"

    _all_four(fake_http, nvd=nvd_pages({"2026-10-15T09:00:00.000Z": [nvd_vuln("CVE-2026-99201")]}))
    refresher.clock.at += dt.timedelta(hours=1)
    again = refresher.run("schedule").result

    # the new CVE came with the partial run unless NVD was the feed that failed
    assert again.status == "ok" and again.version == 4
    assert again.new_cves == (["CVE-2026-99201"] if failing == "nvd" else [])
    assert fake_http.hits("/nvd")[-1].query["lastModStartDate"] == "2026-10-15T09:00:00.000Z"  # from the last good run


# --- B03.7: FEEDS=real picks this adapter; the NVD key is optional ------------------------------------------------

def test_b03_7_feeds_real_is_the_http_adapter_with_the_optional_nvd_key(monkeypatch):
    from app.config import Settings
    from app.feeds import FakeFeeds, make_feeds

    monkeypatch.setenv("FEEDS", "real")
    monkeypatch.setenv("NVD_API_KEY", "  my-key ")
    settings = Settings.from_env()
    settings.check()
    feeds = make_feeds(settings)
    assert isinstance(feeds, HttpFeeds) and feeds.nvd_api_key == "my-key" and feeds.nvd_pacer.limit == 50
    assert feeds.urls == FeedUrls()  # the fixed public URLs; nothing in the environment changes them
    assert make_feeds(Settings(feeds="real")).nvd_pacer.limit == 5
    assert isinstance(make_feeds(Settings()), FakeFeeds)  # the fake stays the default


# --- B03.8: the schedule: an hourly timer runs the CLI, which skips until schedule_hours has passed ---------------

class MovingClock:
    def __init__(self, at: dt.datetime):
        self.at = at

    def __call__(self) -> dt.datetime:
        return self.at


@pytest.fixture
def scheduled(tmp_path):
    from app.feeds import FakeFeeds
    from app.live_data import LiveData
    from app.refresh import Refresher

    clock = MovingClock(dt.datetime(2026, 10, 14, 9, tzinfo=UTC))
    return Refresher(LiveData(tmp_path / "live"), FakeFeeds(day=1), clock)


def test_b03_8_the_scheduled_run_skips_until_schedule_hours_have_passed_since_last_checked(scheduled, caplog):
    from app.refresh import run_scheduled

    assert run_scheduled(scheduled, schedule_hours=6).result.trigger == "schedule"  # never checked: runs
    calls = len(scheduled.feeds.calls)

    for hours in (1, 2, 3, 4, 5):  # the hourly timer
        scheduled.clock.at = dt.datetime(2026, 10, 14, 9 + hours, 0, 20, tzinfo=UTC)
        with caplog.at_level("INFO", logger="app.refresh"):
            assert run_scheduled(scheduled, schedule_hours=6) is None
    assert len(scheduled.feeds.calls) == calls  # a skip fetches nothing
    assert "Scheduled refresh skipped: last checked 2026-10-14T09:00:00+00:00, next due 2026-10-14T14:50" in caplog.text

    scheduled.clock.at = dt.datetime(2026, 10, 14, 14, 55, tzinfo=UTC)  # the timer's tick a little early still counts
    assert run_scheduled(scheduled, schedule_hours=6).ran


def test_b03_8_a_failed_scheduled_run_is_tried_again_on_the_next_tick(scheduled):
    from app.refresh import run_scheduled

    run_scheduled(scheduled, schedule_hours=24)
    scheduled.feeds.fail = "nvd"
    scheduled.clock.at += dt.timedelta(hours=24)
    assert run_scheduled(scheduled, schedule_hours=24).result.status == "partial"  # NVD down (B20)

    scheduled.feeds.fail = None
    scheduled.clock.at += dt.timedelta(hours=1)
    assert run_scheduled(scheduled, schedule_hours=24).result.status == "ok"  # last_checked didn't move, so it's still due


def test_b03_8_the_cli_with_schedule_reads_schedule_hours_from_settings(tmp_path, monkeypatch, capsys):
    import json

    from app import refresh
    from app.app_settings import AppSettings, AlertSettings
    from app.state import State

    state = tmp_path / "state.json"
    State(state, None).save_settings(AppSettings(alerts=AlertSettings(schedule_hours=24)))
    for name, value in {"DATA_MODE": "live", "LIVE_PATH": str(tmp_path / "live"), "STATE_PATH": str(state),
                        "FEEDS": "fake"}.items():
        monkeypatch.setenv(name, value)

    assert refresh.main(["--schedule"]) == 0
    assert json.loads(capsys.readouterr().out)["result"]["trigger"] == "schedule"
    assert refresh.main(["--schedule"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ran"] is False and out["skipped"] == "not_due" and out["schedule_hours"] == 24
    gap = dt.datetime.fromisoformat(out["next_due"]) - dt.datetime.fromisoformat(out["last_checked"])
    assert gap == dt.timedelta(hours=23, minutes=50)
    assert len(json.loads((tmp_path / "live" / "refresh.json").read_text())["runs"]) == 1


def test_b03_9_install_writes_the_hourly_timer_and_the_service_running_the_cli(tmp_path):
    import subprocess

    from app.config import ROOT

    script = ROOT.parent / "deploy" / "systemd" / "install.sh"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "cfg"),
           "UV": "/opt/uv/bin/uv"}
    run = subprocess.run([str(script), "--no-reload"], env=env, capture_output=True, text=True, check=True)

    units = tmp_path / "cfg" / "systemd" / "user"
    service = (units / "patch-refresh.service").read_text()
    timer = (units / "patch-refresh.timer").read_text()
    assert f"WorkingDirectory={ROOT}\n" in service
    assert "ExecStart=/opt/uv/bin/uv run --env-file .env python -m app.refresh --schedule\n" in service
    assert "Type=oneshot" in service and "@" not in service.split("[Unit]", 1)[1]
    assert "OnCalendar=hourly\n" in timer and "Persistent=true\n" in timer and "WantedBy=timers.target" in timer
    assert "systemctl --user enable --now patch-refresh.timer" in run.stdout  # it says how; it doesn't start it

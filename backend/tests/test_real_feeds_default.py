"""Live mode reads the real feeds by default (B28, #74). Check ids: B28.n.

Seams: the settings and `make_feeds` (which feeds the app and the CLI build), the conftest guard (no test reaches
the real services), the HTTP API (the owner sees which feeds; a live folder of the other kind is refused) and the CLI
(the schedule in snapshot mode). No test calls the network: the real feeds are only ever built, never asked.
"""
import json

import pytest

from app.config import Settings
from app.feeds import FakeFeeds, FeedUrls, HttpFeeds, make_feeds


# --- B28.1: FEEDS defaults to real, in code and from the environment -------------------------------------------

@pytest.mark.builds_real_feeds
def test_b28_1_feeds_default_to_the_real_services(monkeypatch):
    monkeypatch.delenv("FEEDS", raising=False)
    assert Settings().feeds == "real" and Settings.from_env().feeds == "real"
    feeds = make_feeds(Settings())
    assert isinstance(feeds, HttpFeeds) and feeds.urls == FeedUrls()
    assert isinstance(make_feeds(Settings(feeds="fake")), FakeFeeds)  # tests, run.sh and container.sh say fake


# --- B28.2: the conftest guard fails a test that builds the real feeds ------------------------------------------

def test_b28_2_building_the_real_feeds_without_the_fake_server_fails_the_test():
    with pytest.raises(pytest.fail.Exception, match="real feeds"):
        make_feeds(Settings())


def test_b28_2_the_fake_http_server_is_allowed(fake_http):
    assert HttpFeeds(urls=FeedUrls.at(fake_http.url)).urls.nvd.startswith("http://127.0.0.1")


@pytest.mark.builds_real_feeds
def test_b28_2_even_a_marked_test_cannot_ask_a_real_service():
    with pytest.raises(pytest.fail.Exception, match="network"):
        make_feeds(Settings()).kev()


# --- B28.4: a scheduled tick in snapshot mode is a skip, not a failure -------------------------------------------

def test_b28_4_a_scheduled_tick_in_snapshot_mode_skips_and_exits_0(monkeypatch, capsys, tmp_path):
    from app import refresh

    monkeypatch.setenv("DATA_MODE", "snapshot")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    assert refresh.main(["--schedule"]) == 0
    out = capsys.readouterr()
    assert json.loads(out.out) == {"ran": False, "skipped": "snapshot"}
    assert "skipped: the data is the frozen snapshot" in out.err


def test_b28_4_a_manual_run_in_snapshot_mode_still_exits_2(monkeypatch, capsys, tmp_path):
    from app import refresh

    monkeypatch.setenv("DATA_MODE", "snapshot")
    monkeypatch.setenv("STATE_PATH", str(tmp_path / "state.json"))
    assert refresh.main() == 2 and "frozen snapshot" in capsys.readouterr().err


# --- B28.3: a live folder holds one kind of data: the kind that wrote it -----------------------------------------

def written_by(path, kind: str | None) -> None:
    """A live folder as a run of `kind` leaves it (None: as before B28, which recorded nothing)."""
    from app.live_data import LiveData

    live = LiveData(path)
    live.version()  # the copy of the snapshot
    if kind is not None:
        live.write(live.read(), feeds=kind)


def start(tmp_path, index_dir, feeds, **changes):
    """A live app's start-up on `tmp_path / "live"`, as the server does it."""
    from app.deps import build_deps

    kind = "fake" if isinstance(feeds, FakeFeeds) else "real"
    s = Settings(llm_provider="fake", feeds=kind, state_path=tmp_path / "state.json", index_path=index_dir,
                 data_mode="live", live_path=tmp_path / "live", **changes)
    return build_deps(s, feeds=feeds)


def real_feeds(fake_http) -> HttpFeeds:
    """The real adapter, pointed at the local fake server: real by kind, never the network."""
    return HttpFeeds(urls=FeedUrls.at(fake_http.url))


def test_b28_3_a_run_records_which_feeds_wrote_the_live_data(tmp_path, index_dir, index):
    from app.live_data import LiveData
    from tests.test_settings_over_env import App

    app = App(tmp_path, index_dir, data_mode="live")
    assert LiveData(app.settings.live_path).feeds() is None  # the copy of the snapshot: no feeds wrote it yet
    assert app.owner.post("/refresh").json()["ran"]
    assert LiveData(app.settings.live_path).feeds() == "fake"


def test_b28_3_the_real_feeds_refuse_live_data_the_fake_feeds_wrote(tmp_path, index_dir, fake_http):
    from app.live_data import MixedFeeds

    written_by(tmp_path / "live", "fake")
    with pytest.raises(MixedFeeds) as e:  # the start-up stops, before any request
        start(tmp_path, index_dir, real_feeds(fake_http))
    message = str(e.value)
    assert str(tmp_path / "live") in message and "the fake feeds (FEEDS=fake)" in message
    assert "move it aside" in message and "LIVE_PATH" in message
    assert fake_http.hits("/nvd") == []  # nothing was fetched


def test_b28_3_the_fake_feeds_refuse_live_data_the_real_feeds_wrote(tmp_path, index_dir):
    from app.live_data import MixedFeeds

    written_by(tmp_path / "live", "real")
    with pytest.raises(MixedFeeds, match=r"the real feeds \(FEEDS=real\)"):
        start(tmp_path, index_dir, FakeFeeds(day=1))


def test_b28_3_live_data_with_no_record_is_accepted_and_recorded_on_the_next_write(tmp_path, index_dir, index,
                                                                                    fake_http):
    """The owner's data/live from before B28 (created by the real feeds, recorded nothing): kept, not refused."""
    from fastapi.testclient import TestClient

    from app.live_data import LiveData, MixedFeeds
    from app.main import create_app

    written_by(tmp_path / "live", None)
    deps = start(tmp_path, index_dir, FakeFeeds(day=1))
    assert TestClient(create_app(deps)).post("/refresh").json()["ran"]
    assert LiveData(tmp_path / "live").feeds() == "fake"
    with pytest.raises(MixedFeeds, match="fake feeds"):  # from now on the record holds
        start(tmp_path, index_dir, real_feeds(fake_http))


def test_b28_3_the_cli_stops_with_the_message_and_exit_2(tmp_path, monkeypatch, capsys):
    from app import refresh

    written_by(tmp_path / "live", "real")
    for name, value in {"DATA_MODE": "live", "LIVE_PATH": str(tmp_path / "live"),
                        "STATE_PATH": str(tmp_path / "state.json"), "FEEDS": "fake"}.items():
        monkeypatch.setenv(name, value)
    for argv in ([], ["--schedule"]):
        assert refresh.main(argv) == 2
        assert "real feeds" in capsys.readouterr().err


def test_b28_3_switching_to_live_on_settings_refuses_a_folder_of_the_other_kind(tmp_path, index_dir, index):
    from tests.test_settings_over_env import App

    written_by(tmp_path / "live", "real")
    app = App(tmp_path, index_dir)  # snapshot mode, FEEDS=fake
    r = app.owner.put("/settings/server", json={"data_mode": "live"})
    assert (r.status_code, r.json()["error"]["code"]) == (400, "mixed_feeds")
    assert str(tmp_path / "live") in r.json()["error"]["message"]
    assert app.owner.get("/health").json()["mode"] == "snapshot"  # not saved: the app still works
    assert app.owner.get("/settings").json()["server"]["fields"]["data_mode"]["value"] == "snapshot"

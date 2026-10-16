"""The Cloud Run deploy (B13, #44): state and live data in Cloud Storage, the scheduled refresh route, the cold start.

Seam 1 (the HTTP API) and the state store's interface, against the fake bucket (tests/fake_gcs.py): no test calls
Google Cloud or any network. Check ids: B13.n.
"""
import dataclasses

import pytest

from app.config import ConfigError, Settings

SECRET = "s" * 40  # a scheduler secret as the deploy makes one: openssl rand -hex 32 (64 characters)


# --- B13.1: the deployed service's settings -------------------------------------------------------------------------

def test_b13_1_store_bucket_and_scheduler_secret_come_from_the_environment(monkeypatch):
    monkeypatch.setenv("STORE", " GCS ")
    monkeypatch.setenv("GCS_BUCKET", "patch-state-123")
    monkeypatch.setenv("SCHEDULER_SECRET", SECRET)
    s = Settings.from_env()
    assert (s.store, s.gcs_bucket, s.scheduler_secret) == ("gcs", "patch-state-123", SECRET)


def test_b13_1_the_cloud_run_template_names_real_settings_and_starts_once_filled_in(monkeypatch):
    """deploy/cloudrun/env.example.yaml (DEPLOY.md, step 6), with its <...> filled in and the secrets Secret Manager
    adds, gives settings that pass the start-up check."""
    import re

    import yaml

    from app.config import ROOT
    from test_auth import PUBLIC

    env = yaml.safe_load((ROOT.parent / "deploy" / "cloudrun" / "env.example.yaml").read_text())
    names = {f.name.upper() for f in dataclasses.fields(Settings)}
    assert set(env) <= names, set(env) - names
    for name in names:
        monkeypatch.delenv(name, raising=False)
    filled = {k: re.sub(r"<[A-Z_.]+>", "x1", str(v)) for k, v in env.items()} | {"CLERK_JWT_KEY": PUBLIC}
    for name, value in (filled | {"OPENROUTER_API_KEY": "sk-or-test", "SCHEDULER_SECRET": SECRET}).items():
        monkeypatch.setenv(name, value)
    s = Settings.from_env()
    s.check()
    assert (s.store, s.data_mode, s.feeds, s.auth, s.dev_panel) == ("gcs", "live", "real", True, False)
    assert s.auth_allowed_origins == ["https://patch-x1.us-central1.run.app"]


def test_b13_1_locally_the_store_is_the_files_and_there_is_no_scheduled_route(monkeypatch):
    for name in ("STORE", "GCS_BUCKET", "SCHEDULER_SECRET"):
        monkeypatch.delenv(name, raising=False)
    s = Settings.from_env()
    assert (s.store, s.gcs_bucket, s.scheduler_secret) == ("local", "", "")


@pytest.mark.parametrize(("change", "message"), [
    ({"store": "s3"}, "STORE must be local or gcs"),
    ({"store": "gcs"}, "STORE=gcs needs GCS_BUCKET"),
    ({"scheduler_secret": "short"}, "SCHEDULER_SECRET must be at least 32 characters"),
])
def test_b13_1_a_bad_deploy_setting_stops_the_start_up_plainly(change, message):
    with pytest.raises(ConfigError, match=message):
        dataclasses.replace(Settings(), **change).check()


# --- B13.2: deployed, every user's state is an object in the bucket -----------------------------------------------

@pytest.fixture
def bucket():
    from tests.fake_gcs import FakeBucket

    return FakeBucket()


def gcs_app(settings, bucket, **change):
    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.main import create_app

    s = dataclasses.replace(settings, store="gcs", gcs_bucket="patch-test", **change)
    return TestClient(create_app(build_deps(s, bucket=bucket)), raise_server_exceptions=False)


def test_b13_2_a_users_state_is_one_object_in_the_bucket_and_survives_a_restart(settings, bucket, tmp_path):
    c = gcs_app(settings, bucket)
    assert c.put("/watchlist", json={"products": ["vllm", "gradio"]}).status_code == 200
    assert "users/default.json" in bucket.objects
    assert not settings.state_path.exists()  # nothing on the instance's disk: it goes with the instance
    again = gcs_app(dataclasses.replace(settings, state_path=tmp_path / "other" / "state.json"), bucket)
    assert again.get("/watchlist").json()["watchlist"] == ["vllm", "gradio"]


class RacingBucket:
    """The fake bucket, where another instance writes the same object once, between this one's read and write."""

    def __init__(self, bucket, other_write):
        self.inner, self.other_write, self.raced = bucket, other_write, False

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def blob(self, name):
        blob = self.inner.blob(name)
        upload = blob.upload_from_string

        def racing_upload(data, content_type="application/octet-stream", if_generation_match=None):
            if not self.raced:
                self.raced = True
                self.other_write()  # the other instance's write: a new generation
            return upload(data, content_type, if_generation_match=if_generation_match)

        blob.upload_from_string = racing_upload
        return blob


def test_b13_2_a_write_that_loses_the_generation_race_reads_again_and_keeps_both_changes(knowledge, bucket):
    from app.state import State
    from app.store import GcsStore

    store = GcsStore(bucket, prefix="users/")
    State(None, knowledge, store=store, key="alice.json").set_watchlist(["vllm"])  # the object exists

    def other_instance():
        State(None, knowledge, store=store, key="alice.json").set_status("CVE-2025-3248", "fixed")

    racing = State(None, knowledge, store=GcsStore(RacingBucket(bucket, other_instance), prefix="users/"),
                   key="alice.json")
    racing.set_status("CVE-2024-8309", "fixed")
    uploads = [c for c in bucket.calls if c[0] == "upload"]
    assert all(c[2] is not None for c in uploads)  # every write carried the generation it read
    assert len(uploads) == 4  # set up, the other instance, the refused write, the retry
    assert racing.read().statuses == {"CVE-2025-3248": "fixed", "CVE-2024-8309": "fixed"}


# --- B13.3: the scheduled refresh route: its own secret, not a user -------------------------------------------------

def scheduled_app(tmp_path, index_dir, **change):
    """A live-mode app at 09:00 on day 1 on the fake feeds, with the scheduler's secret set."""
    import shutil

    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.feeds import FakeFeeds
    from app.main import create_app
    from test_refresh import DAY1, Clock

    shutil.copytree(index_dir, tmp_path / "index")
    s = Settings(llm_provider="fake", feeds="fake", state_path=tmp_path / "state.json",
                 index_path=tmp_path / "index",
                 data_mode="live", live_path=tmp_path / "live", scheduler_secret=SECRET)
    clock = Clock(f"{DAY1}T09:00:00+00:00")
    s = dataclasses.replace(s, **change)
    deps = build_deps(s, feeds=FakeFeeds(day=1, fail=",".join(s.fake_feeds_fail) or None), clock=clock)
    return TestClient(create_app(deps), raise_server_exceptions=False), clock


def tick(c, secret: str | None = SECRET):
    return c.post("/refresh/scheduled", headers={"X-Scheduler-Secret": secret} if secret is not None else {})


def test_b13_3_without_the_secret_the_scheduled_route_refuses_and_runs_nothing(tmp_path, index_dir, index):
    c, _ = scheduled_app(tmp_path, index_dir)
    for secret in (None, "", "wrong", SECRET[:-1], SECRET + "x"):
        r = tick(c, secret)
        assert r.status_code == 401, secret
        assert r.json()["error"]["code"] == "not_scheduler"
    assert c.get("/refresh").json()["last_result"] is None  # nothing ran


def test_b13_3_with_the_secret_it_runs_the_same_refresh_as_check_now(tmp_path, index_dir, index):
    from test_refresh import NEW_DAY1

    c, _ = scheduled_app(tmp_path, index_dir)
    r = tick(c)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ran"] is True and body["result"]["trigger"] == "schedule" and body["result"]["status"] == "ok"
    assert NEW_DAY1 in [row["id"] for row in c.get("/cves?status=all&since=2026-10-14").json()["rows"]]
    assert c.get("/refresh/runs").json()["runs"][0]["trigger"] == "schedule"


def test_b13_3_it_skips_until_the_settings_schedule_is_due_and_while_paused(tmp_path, index_dir, index):
    c, clock = scheduled_app(tmp_path, index_dir)
    tick(c)
    clock.advance(60)  # an hour later; the default schedule is longer
    r = tick(c)
    assert r.status_code == 200
    assert (r.json()["ran"], r.json()["skipped"]) == (False, "not_due") and r.json()["next_due"]
    settings = c.get("/settings").json()["settings"]
    settings["alerts"]["schedule_paused"] = True
    c.put("/settings", json=settings)
    clock.advance(60 * 24)
    assert tick(c).json()["skipped"] == "paused"


def test_b13_3_it_needs_no_user_with_sign_in_on(tmp_path, index_dir, index):
    """The deliberate exception to "every route needs a user" (B10): Cloud Scheduler has no Clerk session."""
    from test_auth import ORIGIN, PUBLIC

    c, _ = scheduled_app(tmp_path, index_dir, auth=True, owner="user_owner", clerk_publishable_key="pk_test_x",
                         clerk_jwt_key=PUBLIC,
                         auth_allowed_origins=[ORIGIN])
    assert c.get("/refresh").status_code == 401  # the rest of the API still needs a user
    assert tick(c, "wrong").status_code == 401
    assert tick(c).json()["ran"] is True


def test_b13_3_a_run_where_no_feed_answered_is_an_error_cloud_scheduler_shows(tmp_path, index_dir, index):
    c, _ = scheduled_app(tmp_path, index_dir, fake_feeds_fail=["nvd", "kev", "osv", "epss"])
    r = tick(c)
    assert r.status_code == 502
    assert (r.json()["ran"], r.json()["result"]["status"]) == (True, "failed")


def test_b13_3_in_the_container_the_route_is_under_api_as_the_scheduler_job_calls_it(tmp_path, index_dir, index):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><div id=root></div>")
    c, _ = scheduled_app(tmp_path, index_dir, frontend_dir=dist)
    r = c.post("/api/refresh/scheduled", headers={"X-Scheduler-Secret": SECRET})
    assert (r.status_code, r.json()["ran"]) == (200, True)


def test_b13_3_without_a_secret_set_there_is_no_scheduled_route(tmp_path, index_dir, index):
    c, _ = scheduled_app(tmp_path, index_dir, scheduler_secret="")
    assert tick(c, "").status_code == 404
    assert tick(c, SECRET).status_code == 404


def test_b13_3_in_snapshot_mode_there_is_nothing_to_refresh(tmp_path, index_dir, index):
    c, _ = scheduled_app(tmp_path, index_dir, data_mode="snapshot")
    r = tick(c)
    assert (r.status_code, r.json()["error"]["code"]) == (400, "snapshot_mode")


# --- B13.4: a cold start catches up with the live data in the bucket -------------------------------------------------

def test_b13_4_a_cold_start_on_the_baked_index_catches_up_with_the_live_data_in_the_bucket(tmp_path, index_dir, index,
                                                                                          bucket, caplog):
    """Instance one refreshes, then scales to zero. Instance two starts on an empty disk with the image's snapshot
    index: it reads the live version from the bucket and embeds only the chunks that differ from the snapshot."""
    import shutil

    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.feeds import FakeFeeds
    from app.main import create_app
    from test_refresh import DAY1, NEW_DAY1, Clock

    def instance(name: str):
        shutil.copytree(index_dir, tmp_path / name / "index")  # the image's baked index: built from the snapshot
        s = Settings(llm_provider="fake", feeds="fake", state_path=tmp_path / name / "state.json",
                     index_path=tmp_path / name / "index", data_mode="live", live_path=tmp_path / name / "live",
                     store="gcs", gcs_bucket="patch-test")
        deps = build_deps(s, feeds=FakeFeeds(day=1), clock=Clock(f"{DAY1}T09:00:00+00:00"), bucket=bucket)
        return TestClient(create_app(deps), raise_server_exceptions=False)

    one = instance("one")
    assert one.post("/refresh").json()["result"]["version"] == 2
    assert {"live/current.json", "live/refresh.json", "live/v000002/cves.json"} <= set(bucket.objects)

    with caplog.at_level("INFO", logger="app.deps"):
        two = instance("two")
    caught_up = [r.getMessage() for r in caplog.records if "caught up" in r.getMessage()]
    assert len(caught_up) == 1, caplog.text
    embedded = int(caught_up[0].split(" chunks embedded")[0].rsplit(" ", 1)[1])
    assert 0 < embedded < 50  # the day's few CVEs, not the snapshot's 1,680 chunks
    assert two.get("/health").json()["last_checked"] == f"{DAY1}T09:00:00+00:00"
    assert NEW_DAY1 in [r["id"] for r in two.get("/cves?status=all&since=2026-10-14").json()["rows"]]
    found = two.post("/dev/search", json={"query": "component sandbox flow manifest upload"}).json()
    assert NEW_DAY1 in [s["doc_id"] for s in found["final"]]

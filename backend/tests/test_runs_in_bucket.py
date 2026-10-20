"""Deployed, the model-check and retrieval runs are in the state bucket (B58, #104), not on the instance's disk.

Seams: the HTTP API (the Dev routes) and RunStore's interface, against the fake bucket (tests/fake_gcs.py), as the
other STORE=gcs tests (test_deploy.py). Check ids: B58.n.
"""
import dataclasses

import pytest
from fastapi.testclient import TestClient

from test_model_check import run_check


@pytest.fixture
def bucket():
    from tests.fake_gcs import FakeBucket

    return FakeBucket()


def instance(settings, bucket, name: str):
    """One Cloud Run instance: its own empty disk (state_path's folder), the shared bucket."""
    from app.deps import build_deps
    from app.main import create_app

    s = dataclasses.replace(settings, store="gcs", gcs_bucket="patch-test",
                            state_path=settings.state_path.parent / name / "state.json")
    return TestClient(create_app(build_deps(s, bucket=bucket)), raise_server_exceptions=False), s


def evals(bucket) -> list[str]:
    return sorted(n for n in bucket.objects if n.startswith("evals/"))


def test_b58_1_a_finished_model_check_is_one_object_in_the_bucket_written_once(settings, bucket):
    c, s = instance(settings, bucket, "one")
    run = run_check(c, {"ids": ["Q7"]})
    assert run["status"] == "done"
    assert evals(bucket) == [f"evals/models/{run['id']}.json"]
    assert [x for x in bucket.calls if x[1].startswith("evals/")] == [("upload", f"evals/models/{run['id']}.json", None)]
    assert not (s.state_path.parent / "evals").exists()  # nothing on the instance's disk


def test_b58_2_a_new_instance_lists_and_reads_the_runs_and_the_report_shows_them(settings, bucket):
    c, _ = instance(settings, bucket, "one")
    model = run_check(c, {"ids": ["Q7"]})
    retrieval = c.post("/dev/retrieval-check").json()
    assert f"evals/retrieval/{retrieval['id']}.json" in evals(bucket)

    again, s = instance(settings, bucket, "two")  # the first instance stopped; its disk went with it
    assert [r["id"] for r in again.get("/dev/model-checks").json()["runs"]] == [model["id"]]
    assert again.get(f"/dev/model-check/{model['id']}").json()["summary"] == model["summary"]
    assert [r["id"] for r in again.get("/dev/retrieval-checks").json()["runs"]] == [retrieval["id"]]
    assert again.get(f"/dev/retrieval-check/{retrieval['id']}").json()["modes"] == retrieval["modes"]
    report = again.get("/dev/report")
    assert report.status_code == 200 and retrieval["embedder"] in report.text
    assert not (s.state_path.parent / "evals").exists()


def test_b58_3_the_bucket_lists_runs_newest_first(settings, bucket):
    from app.evals.runs import RunStore

    s = dataclasses.replace(settings, store="gcs", gcs_bucket="patch-test")
    store = RunStore.for_settings(s, bucket)
    for run_id in ("20261015-100000-000-bbbb", "20261016-090000-000-cccc", "20261014-230000-000-aaaa"):
        store.save("models", {"id": run_id})
    fresh = RunStore.for_settings(s, bucket)
    assert [r["id"] for r in fresh.all("models")] == ["20261016-090000-000-cccc", "20261015-100000-000-bbbb",
                                                      "20261014-230000-000-aaaa"]
    assert fresh.get("models", "20261015-100000-000-bbbb") == {"id": "20261015-100000-000-bbbb"}
    assert fresh.get("models", "../users/default") is None  # ids only, as on disk
    assert fresh.all("retrieval") == []


def test_b58_4_locally_the_runs_stay_files_next_to_the_state_file(client, settings):
    run = run_check(client, {"ids": ["Q7"]})
    path = settings.state_path.parent / "evals" / "models" / f"{run['id']}.json"
    assert path.exists()
    assert client.get("/dev/model-checks").json()["runs"][0]["id"] == run["id"]

"""HTTP API (seam 1). Check ids: A01.n, from ticket #3."""


def test_a01_1_health_reports_status_model_and_as_of_date(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "llm": "fake", "model": "FakeLLM (scripted)", "as_of": "2026-10-13", "dev_panel": True,
                        "mode": "snapshot", "last_checked": None}


# A02 (#4): the shell shows the Dev page only when the backend allows the dev panel.
def test_a02_1_health_says_whether_the_dev_panel_is_allowed(client):
    assert client.get("/health").json()["dev_panel"] is True


def test_a02_1_health_reports_dev_panel_off(settings, knowledge):
    from dataclasses import replace

    from fastapi.testclient import TestClient

    from app.deps import build_deps
    from app.main import create_app

    off = create_app(build_deps(replace(settings, dev_panel=False), knowledge=knowledge))
    assert TestClient(off).get("/health").json()["dev_panel"] is False

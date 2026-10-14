"""HTTP API (seam 1). Check ids: A01.n, from ticket #3."""


def test_a01_1_health_reports_status_model_and_as_of_date(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "llm": "fake", "model": "FakeLLM (scripted)", "as_of": "2026-10-13"}

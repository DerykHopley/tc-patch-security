"""Am I affected? Usage, version and verdict through the HTTP API (seam 1). Check ids: A15.n, from ticket #17.

The verdict rules themselves are table-tested in test_verdict.py; these only check they're wired through.
"""
import json

import pytest


def _product(body, pid):
    return next(p for p in body["products"] if p["product"] == pid)


def _row(client, cve_id, product):
    rows = client.get(f"/cves?status=all&product={product}&limit=200").json()["rows"]
    return next(r for r in rows if r["id"] == cve_id)


# --- A15.1: per watched product, usage, optional version, internet-facing -----------------------------------------

def test_a15_1_defaults_for_each_watched_product(client):
    body = client.get("/watchlist").json()
    assert body["watchlist"] == ["langchain", "langflow", "litellm", "ollama", "open-webui"]
    assert [p["product"] for p in body["products"]] == body["watchlist"]
    assert _product(body, "langchain") == {
        "product": "langchain", "name": "LangChain", "usage": "library", "version": None,
        "internet_facing": False, "coverage": "package", "ecosystem": "PyPI"}
    assert _product(body, "langflow")["usage"] == "self_hosted"
    assert _product(body, "ollama")["ecosystem"] == "Go"


def test_a15_1_an_old_state_file_loads_with_defaults(settings, client):
    settings.state_path.write_text(json.dumps({"watchlist": ["ollama", "dify"], "statuses": {}}))
    body = client.get("/watchlist").json()
    assert _product(body, "ollama") | {} == {
        "product": "ollama", "name": "Ollama", "usage": "self_hosted", "version": None,
        "internet_facing": False, "coverage": "package", "ecosystem": "Go"}
    assert _product(body, "dify")["coverage"] == "none" and _product(body, "dify")["ecosystem"] is None


def test_a15_1_put_replaces_usage_version_and_internet_facing(client):
    r = client.put("/watchlist", json={"products": [
        {"product": "Langflow", "usage": "hosted", "version": "1.2.0", "internet_facing": True},
        "ollama"]})
    assert r.status_code == 200
    body = client.get("/watchlist").json()
    assert body["watchlist"] == ["langflow", "ollama"]
    lf = _product(body, "langflow")
    assert (lf["usage"], lf["version"], lf["internet_facing"]) == ("hosted", "1.2.0", True)
    assert _product(body, "ollama")["usage"] == "self_hosted"  # a plain name keeps what's saved: the defaults
    # A plain name keeps the saved fields; an object replaces them.
    client.put("/watchlist", json={"products": ["langflow"]})
    assert _product(client.get("/watchlist").json(), "langflow")["version"] == "1.2.0"
    client.put("/watchlist", json={"products": [{"product": "langflow"}]})
    lf = _product(client.get("/watchlist").json(), "langflow")
    assert (lf["usage"], lf["version"], lf["internet_facing"]) == ("self_hosted", None, False)


@pytest.mark.parametrize("entry,code", [
    ({"product": "ollama", "usage": "on-prem"}, "invalid_request"),
    ({"product": "ollama", "internet_facing": "very"}, "invalid_request"),
    ({"product": "ollama", "version": "latest"}, "bad_version"),
    ({"product": "langchain", "version": "1.0; rm -rf"}, "bad_version"),
    ({"product": "dify", "version": "x" * 41}, "invalid_request"),
    ({"product": "notion"}, "invalid_input"),
])
def test_a15_1_unknown_values_are_400(client, entry, code):
    r = client.put("/watchlist", json={"products": [entry]})
    assert r.status_code == 400 and r.json()["error"]["code"] == code
    assert client.get("/watchlist").json()["watchlist"] == ["langchain", "langflow", "litellm", "ollama", "open-webui"]


def test_a15_1_version_checked_by_the_products_ecosystem(client):
    ok = [{"product": "ollama", "version": "v0.1.29"}, {"product": "langchain", "version": "0.3.0rc1"},
          {"product": "flowise", "version": "3.1.0-beta.1"}, {"product": "dify", "version": "1.4.0"},
          {"product": "llama.cpp", "version": "b4500"}]
    assert client.put("/watchlist", json={"products": ok}).status_code == 200
    r = client.put("/watchlist", json={"products": [{"product": "langchain", "version": "1.x"}]})
    assert r.status_code == 400 and r.json()["error"]["message"] == \
        "'1.x' isn't a PyPI (PEP 440) version, which LangChain uses. Example: 0.3.27."


# --- A15.2 / A15.3: each CVE row carries the verdict, its reason, the fixed version and who acts ------------------

def test_a15_2_rows_carry_verdict_reason_fixed_version_and_who_acts(client):
    client.put("/watchlist", json={"products": [
        {"product": "langflow", "version": "1.2.0", "usage": "transitive"},
        {"product": "ollama", "version": "v0.1.29", "usage": "hosted"},
        {"product": "langchain"}, {"product": "dify", "version": "1.4.0"}]})
    row = _row(client, "CVE-2025-3248", "langflow")
    assert {k: row[k] for k in ("verdict", "verdict_reason", "fixed_version", "who_acts", "usage")} == {
        "verdict": "affected", "verdict_reason": "1.2.0 is before the fixed version 1.3.0 (langflow)",
        "fixed_version": "1.3.0", "who_acts": "upstream", "usage": "transitive"}
    row = _row(client, "CVE-2024-28224", "ollama")
    assert (row["verdict"], row["who_acts"]) == ("not_affected", "vendor")
    row = _row(client, "CVE-2024-8309", "langchain")
    assert (row["verdict"], row["verdict_reason"], row["fixed_version"]) == ("unknown", "no version given", "0.2.19")
    dify = client.get("/cves?product=dify&limit=1").json()["rows"][0]
    assert (dify["verdict"], dify["verdict_reason"]) == ("unknown", "no version data for this product")


def test_a15_2_filter_by_verdict(client):
    client.put("/watchlist", json={"products": [{"product": "langflow", "version": "1.3.0"}, "dify"]})
    every = client.get("/cves?status=all&limit=200").json()
    by = {v: client.get(f"/cves?status=all&limit=200&verdict={v}").json() for v in ("affected", "not_affected", "unknown")}
    assert sum(b["total"] for b in by.values()) == every["total"]
    for v, b in by.items():
        assert b["total"] > 0 and {r["verdict"] for r in b["rows"]} == {v}
    assert client.get("/cves?verdict=maybe").status_code == 400


# --- A15.4: the verdict never changes the CVE status ----------------------------------------------------------------

def test_a15_4_a_not_affected_verdict_leaves_the_cve_open(client):
    before = client.get("/dashboard").json()["kpis"]
    client.put("/watchlist", json={"products": [{"product": p, "version": v} for p, v in (
        ("langchain", None), ("langflow", "99.0.0"), ("litellm", None), ("ollama", None), ("open-webui", None))]})
    row = _row(client, "CVE-2025-3248", "langflow")
    assert row["verdict"] == "not_affected" and row["status"] == "open"
    assert row["id"] in {r["id"] for r in client.get("/cves?status=open&product=langflow&limit=200").json()["rows"]}
    assert client.get("/dashboard").json()["kpis"] == before  # open CVEs are counted by status alone

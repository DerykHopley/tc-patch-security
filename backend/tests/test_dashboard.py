"""Dashboard API (seam 1), moved from proto (its D1-D4). Check ids: A04.n, from ticket #6."""


def test_a04_1_dashboard_tiles_watchlist_and_products(client):
    d = client.get("/dashboard").json()
    assert d["as_of"] == "2026-10-13"
    assert set(d["kpis"]) == {"open", "critical", "kev", "kev_next_due", "new_30d"}
    assert d["kpis"]["open"] == sum(p["total"] for p in d["by_product"])
    assert d["kpis"]["kev"] == 9 and d["kpis"]["kev_next_due"]["due"]
    assert d["watchlist"] == ["langchain", "langflow", "litellm", "ollama", "open-webui"]
    assert len(d["products"]) == 12 and {"id": "open-webui", "name": "Open WebUI"} in d["products"]
    assert [p["product"] for p in d["by_product"]] == d["watchlist"]
    assert d["per_month"][0]["month"] == "2024-01" and d["per_month"][-1]["month"] == "2026-10"
    assert len(d["latest_incidents"]) == 5
    assert {s["name"].split()[0] for s in d["freshness"]} >= {"OWASP", "MITRE", "NVD", "CISA"}


def test_a04_1_new_in_the_30_days_up_to_the_as_of_date(client):
    rows = [r for offset in (0, 200, 400) for r in client.get(f"/cves?status=all&limit=200&offset={offset}").json()["rows"]]
    assert len(rows) == client.get("/cves?status=all&limit=1").json()["total"]
    expected = sum("2026-09-13" < r["published"] <= "2026-10-13" for r in rows)
    assert expected > 0
    assert client.get("/dashboard").json()["kpis"]["new_30d"] == expected


def test_a04_1_marking_fixed_changes_the_tiles(client):
    before = client.get("/dashboard").json()["kpis"]
    client.patch("/cves/CVE-2025-3248", json={"status": "fixed"})  # Langflow, critical, in KEV
    after = client.get("/dashboard").json()["kpis"]
    assert after["open"] == before["open"] - 1
    assert after["critical"] == before["critical"] - 1
    assert after["kev"] == before["kev"] - 1


def test_a04_2_cves_sorted_kev_first_then_cvss_then_newest(client):
    rows = client.get("/cves?limit=200").json()["rows"]
    keys = [(not r["kev"], -(r["cvss"] or 0)) for r in rows]
    assert keys == sorted(keys)
    for a, b in zip(rows, rows[1:]):
        if (a["kev"], a["cvss"]) == (b["kev"], b["cvss"]):
            assert a["published"] >= b["published"]
    assert rows[0]["kev"] and all(r["status"] == "open" for r in rows)


def test_a04_2_cves_filtered_by_product_severity_and_status(client):
    body = client.get("/cves?product=Open WebUI&severity_min=high&limit=5").json()
    assert body["total"] > 5 and len(body["rows"]) == 5
    assert all(r["product"] == "open-webui" and r["severity"] in ("HIGH", "CRITICAL") for r in body["rows"])
    client.patch("/cves/CVE-2024-8309", json={"status": "not_affected"})
    rows = client.get("/cves?status=not_affected").json()["rows"]
    assert [(r["id"], r["status"]) for r in rows] == [("CVE-2024-8309", "not_affected")]


def test_a04_2_cves_page_at_most_200(client):
    total = client.get("/cves?status=all&limit=1").json()["total"]
    assert total > 200
    assert len(client.get("/cves?status=all&limit=200").json()["rows"]) == 200
    last = client.get(f"/cves?status=all&limit=200&offset={total - 5}").json()["rows"]
    assert len(last) == 5


def test_a04_2_bad_params_get_a_plain_400(client):
    for query, words in (("status=closed", "status must be"), ("product=notion", "isn't a product"),
                         ("severity_min=huge", "severity_min must be")):
        r = client.get(f"/cves?{query}")
        assert r.status_code == 400 and words in r.json()["error"]["message"], query
    assert client.get("/cves?limit=500").status_code == 400
    assert client.get("/cves?offset=-1").status_code == 400


def test_a04_3_row_actions_mark_fixed_not_affected_and_reopen(client):
    def status():
        return client.get("/cves?status=all&product=langchain&limit=200").json()["rows"]

    assert client.patch("/cves/CVE-2024-8309", json={"status": "fixed"}).json() == {"id": "CVE-2024-8309", "status": "fixed"}
    assert next(r for r in status() if r["id"] == "CVE-2024-8309")["status"] == "fixed"
    client.patch("/cves/CVE-2024-8309", json={"status": "not_affected"})
    assert next(r for r in status() if r["id"] == "CVE-2024-8309")["status"] == "not_affected"
    client.patch("/cves/CVE-2024-8309", json={"status": "open"})
    assert next(r for r in status() if r["id"] == "CVE-2024-8309")["status"] == "open"


def test_a04_3_row_action_errors(client):
    r = client.patch("/cves/CVE-1999-0001", json={"status": "fixed"})
    assert r.status_code == 404 and "isn't in the snapshot" in r.json()["error"]["message"]
    assert client.patch("/cves/CVE-2024-8309", json={"status": "done"}).status_code == 400


def test_a04_4_watchlist_add_and_remove_from_the_fixed_list(client):
    assert client.put("/watchlist", json={"products": ["vLLM", "ollama", "Ollama"]}).json() == {"watchlist": ["vllm", "ollama"]}
    assert client.get("/watchlist").json() == {"watchlist": ["vllm", "ollama"]}
    assert client.get("/dashboard").json()["watchlist"] == ["vllm", "ollama"]
    assert {r["product"] for r in client.get("/cves?limit=200").json()["rows"]} == {"vllm", "ollama"}


def test_a04_4_unknown_product_rejected_with_a_plain_message(client):
    r = client.put("/watchlist", json={"products": ["ollama", "notion"]})
    assert r.status_code == 400
    assert r.json()["error"]["message"].startswith("'notion' isn't a product I track. Choose from: ")
    assert client.get("/watchlist").json()["watchlist"] == ["langchain", "langflow", "litellm", "ollama", "open-webui"]


def test_a04_5_one_state_shared_with_what_the_chat_uses(client, deps):
    # The chat's tools change deps.state; the dashboard reads the same state, and the other way round.
    deps.state.watch("vLLM")
    deps.state.set_status("CVE-2024-8309", "fixed")
    assert "vllm" in client.get("/dashboard").json()["watchlist"]
    assert [r["id"] for r in client.get("/cves?status=fixed").json()["rows"]] == ["CVE-2024-8309"]
    client.put("/watchlist", json={"products": ["ollama"]})
    client.patch("/cves/CVE-2025-1975", json={"status": "not_affected"})
    snap = deps.state.snapshot()
    assert snap["watchlist"] == ["ollama"] and snap["statuses"]["CVE-2025-1975"] == "not_affected"

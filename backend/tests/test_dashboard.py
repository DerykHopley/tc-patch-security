"""Dashboard API (seam 1), moved from proto (its D1-D4). Check ids: A04.n, from ticket #6."""


def test_a04_1_dashboard_tiles_watchlist_and_products(client):
    d = client.get("/dashboard").json()
    assert d["as_of"] == "2026-10-13"
    assert set(d["kpis"]) == {"open", "critical", "kev", "kev_next_due", "kev_overdue", "overdue", "new_30d", "new_since",
                             "no_fix", "review_due", "accepted"}  # the last three: A16b
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


def test_a04_2_cves_open_and_kev_first(client):
    # The full order is the priority's since A16: test_priority_api.py::test_a16_5_sorted_by_priority_then_due_date
    rows = client.get("/cves?limit=200").json()["rows"]
    assert rows[0]["kev"] and all(r["status"] == "open" for r in rows)


def test_a04_2_cves_filtered_by_product_severity_and_status(client):
    body = client.get("/cves?product=Open WebUI&severity_min=high&limit=5").json()
    assert body["total"] > 5 and len(body["rows"]) == 5
    assert all(r["product"] == "open-webui" and r["severity"] in ("HIGH", "CRITICAL") for r in body["rows"])
    client.patch("/cves/CVE-2024-8309", json={"status": "not_affected", "justification": "component_not_present"})
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

    r = client.patch("/cves/CVE-2024-8309", json={"status": "fixed"}).json()
    assert (r["id"], r["status"], r["decision"]["status"]) == ("CVE-2024-8309", "fixed", "fixed")
    assert next(r for r in status() if r["id"] == "CVE-2024-8309")["status"] == "fixed"
    client.patch("/cves/CVE-2024-8309", json={"status": "not_affected", "justification": "component_not_present"})
    assert next(r for r in status() if r["id"] == "CVE-2024-8309")["status"] == "not_affected"
    client.patch("/cves/CVE-2024-8309", json={"status": "open"})
    assert next(r for r in status() if r["id"] == "CVE-2024-8309")["status"] == "open"


def test_a04_3_row_action_errors(client):
    r = client.patch("/cves/CVE-1999-0001", json={"status": "fixed"})
    assert r.status_code == 404 and "isn't in the snapshot" in r.json()["error"]["message"]
    assert client.patch("/cves/CVE-2024-8309", json={"status": "done"}).status_code == 400


def test_a04_4_watchlist_add_and_remove_from_the_fixed_list(client):
    assert client.put("/watchlist", json={"products": ["vLLM", "ollama", "Ollama"]}).json()["watchlist"] == ["vllm", "ollama"]
    assert client.get("/watchlist").json()["watchlist"] == ["vllm", "ollama"]
    assert client.get("/dashboard").json()["watchlist"] == ["vllm", "ollama"]
    assert {r["product"] for r in client.get("/cves?limit=200").json()["rows"]} == {"vllm", "ollama"}


def test_a04_4_unknown_product_rejected_with_a_plain_message(client):
    r = client.put("/watchlist", json={"products": ["ollama", "notion"]})
    assert r.status_code == 400
    assert r.json()["error"]["message"].startswith("'notion' isn't a product I track. Choose from: ")
    assert client.get("/watchlist").json()["watchlist"] == ["langchain", "langflow", "litellm", "ollama", "open-webui"]


def _row(client, cve_id, product):
    rows = client.get(f"/cves?status=all&product={product}&limit=200").json()["rows"]
    return next(r for r in rows if r["id"] == cve_id)


def test_a14_7_rows_carry_epss_and_possible_match(client):
    row = _row(client, "CVE-2024-8309", "langchain")  # product from the CPE
    assert row["epss"] == {"score": 0.13738, "percentile": 0.96438, "date": "2026-10-13"}
    assert row["possible_match"] is False
    assert _row(client, "CVE-2026-105740", "langflow")["possible_match"] is True  # from text, OSV doesn't say
    assert _row(client, "CVE-2026-105741", "langflow")["possible_match"] is False  # from text, OSV confirms
    assert all("epss" in r and "possible_match" in r for r in client.get("/cves?limit=200").json()["rows"])


def test_a14_7_freshness_shows_every_licence_attribution_and_the_nvd_notice(client):
    sources = {s["id"]: s for s in client.get("/dashboard").json()["freshness"]}
    assert set(sources) == {"owasp_llm", "owasp_web", "atlas", "nvd", "kev", "osv", "epss"}
    assert all(s["licence"] and s["attribution"] for s in sources.values())
    assert sources["epss"]["attribution"] == "EPSS by FIRST" and sources["kev"]["licence"] == "CC0 1.0"
    assert sources["nvd"]["notice"].startswith("This product uses the NVD API but is not endorsed")


def test_a04_5_one_state_shared_with_what_the_chat_uses(client, deps):
    # The chat's tools change deps.state; the dashboard reads the same state, and the other way round.
    deps.state.watch("vLLM")
    deps.state.set_status("CVE-2024-8309", "fixed")
    assert "vllm" in client.get("/dashboard").json()["watchlist"]
    assert [r["id"] for r in client.get("/cves?status=fixed").json()["rows"]] == ["CVE-2024-8309"]
    client.put("/watchlist", json={"products": ["ollama"]})
    client.patch("/cves/CVE-2025-1975", json={"status": "not_affected", "justification": "component_not_present"})
    stack = deps.state.read()
    assert stack.watchlist == ("ollama",) and stack.statuses["CVE-2025-1975"] == "not_affected"


# --- A04b (#26): the tiles link to the CVEs page with their filter, so the API needs two more ---------------------

def test_a04b_1_kev_filter_matches_the_kev_tile(client):
    body = client.get("/cves?kev=true&limit=200").json()
    assert body["total"] == 9  # the KEV tile (A04.1)
    assert all(r["kev"] and r["status"] == "open" for r in body["rows"])
    assert client.get("/cves?kev=false&limit=1").json()["total"] == client.get("/cves?limit=1").json()["total"] - 9


def test_a04b_2_published_since_filter_matches_the_new_tile(client):
    kpis = client.get("/dashboard").json()["kpis"]
    assert kpis["new_since"] == "2026-09-14"  # the first of the 30 days up to the as-of date, 2026-10-13
    body = client.get("/cves?status=all&published_since=2026-09-14&limit=200").json()
    assert body["total"] == kpis["new_30d"] > 0
    assert all(r["published"] >= "2026-09-14" for r in body["rows"])


def test_a04b_2_bad_published_since_gets_a_plain_400(client):
    r = client.get("/cves?published_since=last-week")
    assert r.status_code == 400 and "published_since must be a date" in r.json()["error"]["message"]


# --- A15b (#30): the dashboard's watchlist becomes a product filter ------------------------------------------------

def _all(client, query: str) -> list[dict]:
    """Every row of a /cves query, across pages."""
    total = client.get(f"/cves?{query}&limit=1").json()["total"]
    return [r for offset in range(0, total, 200)
            for r in client.get(f"/cves?{query}&limit=200&offset={offset}").json()["rows"]]


def test_a15b_3_dashboard_filtered_by_several_products(client):
    whole = client.get("/dashboard").json()
    d = client.get("/dashboard?product=ollama,langflow").json()
    assert d["filter"] == ["langflow", "ollama"]  # applied, in watchlist order
    assert d["watchlist"] == whole["watchlist"]  # the filter narrows the view; it never changes the watchlist
    assert [p["product"] for p in d["by_product"]] == ["langflow", "ollama"]
    open_rows = [r for p in ("langflow", "ollama") for r in _all(client, f"status=open&product={p}")]
    assert 0 < d["kpis"]["open"] == len(open_rows) < whole["kpis"]["open"]
    assert d["kpis"]["critical"] == sum(r["severity"] == "CRITICAL" for r in open_rows)
    assert 0 < d["kpis"]["kev"] == sum(r["kev"] for r in open_rows)
    every = [r for p in ("langflow", "ollama") for r in _all(client, f"status=all&product={p}")]
    assert sum(m["count"] for m in d["per_month"]) == sum(r["published"] <= d["as_of"] for r in every)
    assert sum(o["count"] for o in d["by_owasp"]) + d["owasp_unmapped"] == len(open_rows)
    assert d["latest_incidents"] == whole["latest_incidents"] and d["freshness"] == whole["freshness"]


def test_a15b_3_no_filter_means_every_watched_product(client):
    d = client.get("/dashboard").json()
    assert d["filter"] == []
    assert [p["product"] for p in d["by_product"]] == d["watchlist"]


def test_a15b_3_unknown_or_unwatched_products_are_ignored(client):
    whole = client.get("/dashboard").json()
    d = client.get("/dashboard?product=Open WebUI,notion,vllm,;drop table").json()
    assert d["filter"] == ["open-webui"]  # by name too, as the CVEs page takes it; the rest ignored, no error
    assert d["kpis"]["open"] == len(_all(client, "status=open&product=open-webui"))
    for query in ("product=notion", "product=vllm", "product=", "product=,,"):
        r = client.get(f"/dashboard?{query}")
        assert r.status_code == 200 and r.json()["filter"] == [] and r.json()["kpis"] == whole["kpis"], query


def test_a15b_3_each_chip_says_whether_its_product_has_open_kev_cves(client):
    d = client.get("/dashboard?product=ollama").json()  # not narrowed by the filter: a chip per watched product
    chips = {c["product"]: c for c in d["watched"]}
    assert list(chips) == d["watchlist"]
    langflow = _all(client, "status=open&product=langflow")
    assert chips["langflow"] == {"product": "langflow", "name": "Langflow", "open": len(langflow),
                                 "kev": sum(r["kev"] for r in langflow)}
    assert chips["langflow"]["kev"] > 0 and chips["langchain"]["kev"] == 0


def test_a15b_3_the_cves_query_takes_the_dashboards_products_so_tile_links_carry_them(client):
    d = client.get("/dashboard?product=langflow,ollama").json()
    both = client.get("/cves?product=langflow,Ollama&limit=200").json()
    assert both["total"] == d["kpis"]["open"] and {r["product"] for r in both["rows"]} == {"langflow", "ollama"}
    assert client.get("/cves?product=langflow,ollama&kev=true").json()["total"] == d["kpis"]["kev"]
    for bad in ("langflow,notion", "langflow,,ollama", ","):  # the CVEs page's rule: an unknown product is a 400
        r = client.get(f"/cves?product={bad}")
        assert r.status_code == 400 and "isn't a product I track" in r.json()["error"]["message"], bad


def test_a15b_4_the_filter_follows_the_watchlist(client, deps):
    deps.state.unwatch("langflow")  # what Patch's update_watchlist and the Settings card both do: one state
    d = client.get("/dashboard?product=langflow,ollama").json()
    assert d["filter"] == ["ollama"] and "langflow" not in {c["product"] for c in d["watched"]}

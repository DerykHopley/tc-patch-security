"""The page for one CVE (B35, #85) through the HTTP API: GET /cves/{id}. Check ids: B35.n.

The page shows everything Patch knows about one CVE: the full summary, the product and its affected versions, the
facts (severity, EPSS, KEV, OWASP with its list), the assessment (verdict, decision, priority, due date) and the
links out. The assessment's rules are tested in test_watched.py; this checks the page's answer is wired to them.
"""
AS_OF = "2026-10-13"
FIXABLE = "CVE-2025-3248"  # Langflow, critical, in KEV, fixed in 1.3.0, OWASP A05 (web)
LONG = "CVE-2026-105741"  # Langflow, a description longer than the list's 220 characters
NOT_WATCHED = "CVE-2026-109311"  # vLLM: not on the default watchlist
TWO_PACKAGES = "CVE-2024-12704"  # LlamaIndex: two OSV packages, one with no fixed version


def _row(client, cve_id):
    rows = client.get("/cves?status=all&limit=200&product=langflow").json()["rows"]
    return next(r for r in rows if r["id"] == cve_id)


# --- B35.1: one CVE's page: the facts, the full summary and the links out ------------------------------------------

def test_b35_1_the_page_has_the_full_summary_and_the_facts(client, knowledge):
    r = client.get(f"/cves/{LONG}")
    assert r.status_code == 200
    page = r.json()
    cve = knowledge.cves.get(LONG)
    assert len(cve["description"]) > 220  # the list cuts it; the page doesn't
    assert page["description"] == cve["description"]
    assert (page["id"], page["product"], page["product_name"]) == (LONG, "langflow", "Langflow")
    assert (page["severity"], page["cvss"], page["published"]) == (cve["severity"], cve["cvss"], cve["published"])


def test_b35_1_owasp_with_its_name_and_its_list(client):
    owasp = client.get(f"/cves/{FIXABLE}").json()["owasp"]
    assert owasp["code"] == "A05"
    assert owasp["title"].startswith("A05:2025 ")
    assert owasp["list"] == "OWASP Top 10 2025 (web applications)"
    assert owasp["url"].startswith("https://github.com/OWASP/")


def test_b35_1_kev_epss_and_the_links_to_nvd_and_osv(client):
    page = client.get(f"/cves/{FIXABLE}").json()
    assert page["kev"]["deadline"] and page["kev"]["date_added"] and page["kev"]["required_action"]
    assert 0 <= page["epss"]["percentile"] <= 1
    assert page["url"] == f"https://nvd.nist.gov/vuln/detail/{FIXABLE}"
    assert page["osv_url"] == f"https://osv.dev/vulnerability/{FIXABLE}"


def test_b35_1_the_affected_versions_per_package(client):
    affected = client.get(f"/cves/{TWO_PACKAGES}").json()["affected"]
    assert [(a["package"], a["ecosystem"]) for a in affected] == [("llama-index", "PyPI"), ("llama-index-core", "PyPI")]
    assert affected[0]["ranges"] == [{"introduced": "0", "fixed": None, "last_affected": "0.12.5"}]
    assert affected[1]["ranges"] == [{"introduced": "0", "fixed": "0.12.6", "last_affected": None}]
    assert affected[1]["advisory"] == "GHSA-j3wr-m6xh-64hg"


# --- B35.2: the assessment is the CVEs page's row, so the two pages never disagree ----------------------------------

def test_b35_2_a_watched_cve_carries_its_row_from_the_cves_page(client):
    page = client.get(f"/cves/{FIXABLE}").json()
    assert page["watched"] is True
    assert page["row"] == _row(client, FIXABLE)
    assert page["row"]["priority"] and page["row"]["due_date"]


def test_b35_2_a_decision_shows_on_the_page_with_its_history(client):
    client.patch(f"/cves/{FIXABLE}", json={"status": "fixed", "note": "Upgraded to 1.3.0"})
    row = client.get(f"/cves/{FIXABLE}").json()["row"]
    assert row["status"] == "fixed"
    assert [h["status"] for h in row["history"]] == ["fixed"]
    assert row["history"][0]["note"] == "Upgraded to 1.3.0"


def test_b35_2_a_cve_off_the_watchlist_has_facts_and_a_verdict_but_no_row(client):
    page = client.get(f"/cves/{NOT_WATCHED}").json()
    assert page["watched"] is False
    assert page["row"] is None
    assert page["product"] == "vllm"
    assert page["verdict"] in ("affected", "not_affected", "unknown")


def test_b35_2_lower_case_ids_are_read_as_upper_case(client):
    r = client.get(f"/cves/{FIXABLE.lower()}")
    assert r.status_code == 200 and r.json()["id"] == FIXABLE


# --- B35.3: an unknown or malformed id is a clear 404 ----------------------------------------------------------------

def test_b35_3_an_unknown_cve_is_a_404_that_says_so(client):
    r = client.get("/cves/CVE-1999-0001")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert "CVE-1999-0001" in r.json()["error"]["message"]


def test_b35_3_a_malformed_id_is_a_404_too(client):
    r = client.get("/cves/not-a-cve")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"

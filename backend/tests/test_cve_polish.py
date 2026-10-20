"""CVE list and page polish (B44, #94) through the HTTP API. Check ids: B44.n.

The list's OWASP cell shows a bare code ("A05"); its tooltip names the category and the list it comes from, as the
CVE's page does (B35), so a row says which list without a second request.
"""
FIXABLE = "CVE-2025-3248"  # Langflow, OWASP A05 (web)


def _row(client, cve_id):
    rows = client.get("/cves?status=all&limit=200&product=langflow").json()["rows"]
    return next(r for r in rows if r["id"] == cve_id)


def test_b44_1_a_row_names_its_owasp_category_and_list(client):
    r = _row(client, FIXABLE)
    assert r["owasp"] == "A05"
    assert r["owasp_title"] == "A05:2025 Injection"
    assert r["owasp_list"] == "OWASP Top 10 2025 (web applications)"


def test_b44_1_a_row_without_a_category_has_no_list(client):
    rows = client.get("/cves?status=all&limit=200").json()["rows"]
    bare = next(r for r in rows if r["owasp"] is None)
    assert (bare["owasp_title"], bare["owasp_list"]) == (None, None)

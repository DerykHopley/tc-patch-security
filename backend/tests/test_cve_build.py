"""The shared build code (app/cve_build.py), used by the snapshot script and the live refresh.

Check ids: B01.n, from ticket #32. Each test runs on a small fake input; the snapshot itself is
compared file by file in B01.1 (tests/test_snapshot_build.py).
"""
from app import cve_build as cb


def nvd(id_, description, vendor_products=(), cwes=(), status="Analyzed", published="2025-03-01T10:00:00.000"):
    """One row as the NVD download stores it (snapshot_raw/nvd_ai.json)."""
    return {"id": id_, "published": published, "status": status, "description": description,
            "cwes": list(cwes), "score": 9.8, "severity": "CRITICAL", "vendor_products": list(vendor_products)}


def test_b01_2_product_matched_from_the_cpe_name():
    row = nvd("CVE-2025-1000", "A flaw in a web tool.", ["open-webui:open_webui"])
    assert cb.match_product(row) == ("open-webui", "cpe")


def test_b01_2_cpe_wins_over_a_product_named_in_the_text():
    row = nvd("CVE-2025-1001", "Langflow lets an attacker ...", ["berriai:litellm"])
    assert cb.match_product(row) == ("litellm", "cpe")


def test_b01_3_product_matched_from_the_description_is_a_text_match():
    row = nvd("CVE-2025-1002", "A bug in some-app lets Flowise, and later LangChain, run code.",
              ["someone:some-app"])
    assert cb.match_product(row) == ("flowise", "text")  # the product named earliest


def test_b01_3_text_match_needs_a_whole_word():
    assert cb.match_product(nvd("CVE-2025-1003", "The mydify-plugin and vllmx tools.")) == (None, None)


def test_b01_4_cwe_mapped_to_owasp_web_category():
    cwe_to_web = {"CWE-79": "A05", "CWE-94": "A05", "CWE-862": "A01"}
    assert cb.owasp_category(["CWE-862", "CWE-79"], cwe_to_web) == "A01"  # first by code
    assert cb.owasp_category(["NVD-CWE-noinfo"], cwe_to_web) is None


KEV = {"vulnerabilities": [
    {"cveID": "CVE-2025-2000", "vulnerabilityName": "Langflow Missing Authentication", "dateAdded": "2025-05-05",
     "dueDate": "2025-05-26", "knownRansomwareCampaignUse": "Unknown", "requiredAction": "Apply mitigations.",
     "notes": "dropped", "vendorProject": "Langflow"},
    {"cveID": "CVE-2019-0001", "vulnerabilityName": "Not an LLM product", "dateAdded": "2022-01-01"},
]}


def test_b01_5_cves_joined_to_kev_and_owasp():
    rows = [
        nvd("CVE-2025-2000", "Langflow code injection.", ["langflow:langflow"], ["CWE-94"], published="2025-04-01T00:00:00"),
        nvd("CVE-2025-2001", "Gradio path  traversal.\n", cwes=["CWE-22"], published="2025-06-01T00:00:00"),
        nvd("CVE-2025-2002", "Ollama bug.", ["ollama:ollama"], status="Rejected"),  # rejected: left out
        nvd("CVE-2025-2003", "A bug in another tool."),  # no product: left out
    ]
    cves, kev = cb.build_cves(rows, {"CWE-94": "A05"}, KEV)
    assert [c["id"] for c in cves] == ["CVE-2025-2001", "CVE-2025-2000"]  # newest first
    assert cves[1] == {
        "id": "CVE-2025-2000", "published": "2025-04-01", "product": "langflow", "product_source": "cpe",
        "severity": "CRITICAL", "cvss": 9.8, "cwes": ["CWE-94"], "owasp": "A05",
        "description": "Langflow code injection.", "kev": True, "url": "https://nvd.nist.gov/vuln/detail/CVE-2025-2000"}
    assert cves[0]["product_source"] == "text" and cves[0]["kev"] is False and cves[0]["owasp"] is None
    assert cves[0]["description"] == "Gradio path traversal."  # whitespace folded
    assert kev == [{"cveID": "CVE-2025-2000", "vulnerabilityName": "Langflow Missing Authentication",
                    "dateAdded": "2025-05-05", "dueDate": "2025-05-26", "knownRansomwareCampaignUse": "Unknown",
                    "requiredAction": "Apply mitigations."}]


def rec(id_, aliases, events, package="langflow", published="2025-01-01T00:00:00Z"):
    return {"id": id_, "aliases": aliases, "published": published, "modified": published,
            "affected": [{"package": {"ecosystem": "PyPI", "name": package},
                          "ranges": [{"type": "ECOSYSTEM", "events": events}]}]}


def test_b01_6_osv_records_deduplicated_by_cve_alias_keeping_ghsa():
    raw = {"PyPI/langflow": [
        rec("PYSEC-2025-1", ["CVE-2025-3000", "GHSA-aaaa"], [{"introduced": "0"}, {"fixed": "1.3"}]),
        rec("GHSA-aaaa", ["CVE-2025-3000", "PYSEC-2025-1"], [{"introduced": "0"}, {"fixed": "1.3.0"}]),
    ]}
    out = cb.osv_versions(raw, {"CVE-2025-3000"}, as_of="2026-10-13")
    assert out["cves"] == {"CVE-2025-3000": [{
        "product": "langflow", "ecosystem": "PyPI", "package": "langflow", "advisory": "GHSA-aaaa",
        "ranges": [{"introduced": "0", "fixed": "1.3.0", "last_affected": None}], "fixed": ["1.3.0"]}]}
    assert out["counts"] == {"records": 2, "cves": 1, "not_in_snapshot": 0}


def test_b01_7_epss_attached_to_the_wanted_cves():
    raw = {"date": "2026-10-13", "rows": [
        {"cve": "CVE-2025-3000", "epss": "0.500000000", "percentile": "0.900000000", "date": "2026-10-13"},
        {"cve": "CVE-2019-0001", "epss": "0.1", "percentile": "0.2", "date": "2026-10-13"},  # not wanted
    ]}
    out = cb.epss_scores(raw, ["CVE-2025-3000", "CVE-2025-3001"])
    assert out == {"date": "2026-10-13",
                   "scores": {"CVE-2025-3000": {"score": 0.5, "percentile": 0.9, "date": "2026-10-13"}},
                   "counts": {"scored": 1, "missing": 1}}

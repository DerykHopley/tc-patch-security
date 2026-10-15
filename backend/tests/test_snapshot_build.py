"""The snapshot build (scripts/build_fixtures.py), moved from proto. Check ids: A14.n, from ticket #16.

No test calls the network: the build reads the committed raw downloads (snapshot_raw/), and the
fetch step is tested against a local fake HTTP server (tests/fake_http.py).
"""
import json

import pytest

from app.config import FIXTURES, ROOT
from scripts import build_fixtures as build

EXISTING = ["cves.json", "kev.json", "owasp.json", "atlas.json",
            *(f"owasp_llm/LLM{n:02d}.md" for n in range(1, 11)),
            *(f"owasp_web/A{n:02d}.md" for n in range(1, 11))]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    out = tmp_path_factory.mktemp("fixtures")
    build.build(ROOT / "snapshot_raw", out)
    return out


@pytest.mark.parametrize("name", EXISTING)
def test_a14_1_existing_sources_build_byte_identical(built, name):
    assert (built / name).read_bytes() == (FIXTURES / name).read_bytes()


# --- The additions on a small fake input -----------------------------------------------------

from scripts import snapshot_additions as add  # noqa: E402


def rec(id_, aliases, package, events, ecosystem="PyPI", published="2025-01-01T00:00:00Z", **extra):
    return {"id": id_, "aliases": aliases, "published": published, "modified": published,
            "affected": [{"package": {"ecosystem": ecosystem, "name": package},
                          "ranges": [{"type": "ECOSYSTEM", "events": events}]}], **extra}


FAKE_OSV = {
    "PyPI/langflow": [
        rec("PYSEC-2025-1", ["CVE-2025-0001", "GHSA-aaaa"], "langflow", [{"introduced": "0"}, {"fixed": "1.3"}]),
        rec("GHSA-aaaa", ["CVE-2025-0001", "PYSEC-2025-1"], "langflow", [{"introduced": "0"}, {"fixed": "1.3.0"}]),
        rec("GHSA-late", ["CVE-2025-0002"], "langflow", [{"introduced": "0"}, {"fixed": "2.0.0"}],
            published="2026-10-14T08:00:00Z"),  # after the snapshot date: not in it
        rec("GHSA-none", [], "langflow", [{"introduced": "0"}, {"fixed": "0.9.0"}]),  # no CVE id
        rec("GHSA-gone", ["CVE-2025-0004"], "langflow", [{"introduced": "0"}], withdrawn="2025-02-01T00:00:00Z"),
        rec("GHSA-wide", ["CVE-2099-0001"], "langflow", [{"introduced": "0"}, {"fixed": "1.0.0"}]),  # not in snapshot
    ],
    "PyPI/litellm": [
        rec("GHSA-bbbb", ["CVE-2025-0003"], "litellm",
            [{"introduced": "0"}, {"fixed": "1.2.0"}, {"introduced": "1.5.0"}, {"last_affected": "1.5.3"}]),
        rec("PYSEC-2025-9", ["CVE-2025-0005"], "litellm", [{"introduced": "0"}, {"fixed": "1.9.0"}]),
    ],
}
FAKE_CVES = [
    {"id": "CVE-2025-0001", "product": "langflow", "product_source": "text"},  # OSV agrees: confirmed
    {"id": "CVE-2025-0002", "product": "langflow", "product_source": "text"},  # OSV record too new: unknown
    {"id": "CVE-2025-0003", "product": "langflow", "product_source": "text"},  # OSV says litellm: conflicting
    {"id": "CVE-2025-0004", "product": "dify", "product_source": "text"},  # no OSV data: unknown
    {"id": "CVE-2025-0005", "product": "litellm", "product_source": "cpe"},  # from CPE: not checked
]


def test_a14_3_osv_versions_by_cve_and_package_from_ghsa():
    out = add.osv_versions(FAKE_OSV, {c["id"] for c in FAKE_CVES}, as_of="2026-10-13")
    assert sorted(out["cves"]) == ["CVE-2025-0001", "CVE-2025-0003", "CVE-2025-0005"]
    assert out["cves"]["CVE-2025-0001"] == [{
        "product": "langflow", "ecosystem": "PyPI", "package": "langflow", "advisory": "GHSA-aaaa",
        "ranges": [{"introduced": "0", "fixed": "1.3.0", "last_affected": None}], "fixed": ["1.3.0"]}]
    assert out["cves"]["CVE-2025-0003"][0]["ranges"] == [
        {"introduced": "0", "fixed": "1.2.0", "last_affected": None},
        {"introduced": "1.5.0", "fixed": None, "last_affected": "1.5.3"}]
    assert out["cves"]["CVE-2025-0003"][0]["product"] == "litellm"
    # Without a GHSA record the other one is used, and named
    assert out["cves"]["CVE-2025-0005"][0]["advisory"] == "PYSEC-2025-9"
    assert out["counts"] == {"records": 8, "cves": 3, "not_in_snapshot": 1}


def test_a14_2_every_product_mapped_to_its_packages():
    assert set(add.PACKAGES) == set(build.PRODUCTS)
    by_coverage = {c: sorted(p for p, v in add.PACKAGES.items() if v["coverage"] == c)
                   for c in ("package", "commits", "none")}
    assert len(by_coverage["package"]) == 9
    assert by_coverage["commits"] == ["llama.cpp"] and by_coverage["none"] == ["anything-llm", "dify"]
    assert ("PyPI", "langflow") in add.PACKAGES["langflow"]["packages"]
    assert ("Go", "github.com/ollama/ollama") in add.PACKAGES["ollama"]["packages"]
    assert all(v["packages"] for v in add.PACKAGES.values() if v["coverage"] == "package")


def test_a14_5_product_match_check_on_text_matched_cves():
    osv = add.osv_versions(FAKE_OSV, {c["id"] for c in FAKE_CVES}, as_of="2026-10-13")
    out = add.product_check(FAKE_CVES, osv["cves"])
    assert out["counts"] == {"text_matched": 4, "confirmed": 1, "conflicting": 1, "unknown": 2}
    assert out["cves"]["CVE-2025-0001"] == {"result": "confirmed", "osv_products": ["langflow"]}
    assert out["cves"]["CVE-2025-0003"] == {"result": "conflicting", "osv_products": ["litellm"]}
    assert out["cves"]["CVE-2025-0004"] == {"result": "unknown", "osv_products": []}
    assert "CVE-2025-0005" not in out["cves"]  # its product came from the CPE: nothing to check


FAKE_EPSS = {"date": "2026-10-13", "retrieved": "2026-10-14", "rows": [
    {"cve": "CVE-2025-0001", "epss": "0.999930000", "percentile": "0.999880000", "date": "2026-10-13"},
    {"cve": "CVE-2025-0003", "epss": "0.000420000", "percentile": "0.120000000", "date": "2026-10-13"},
]}


def test_a14_4_epss_score_percentile_and_date_per_cve():
    out = add.epss_scores(FAKE_EPSS, [c["id"] for c in FAKE_CVES])
    assert out["date"] == "2026-10-13"
    assert out["scores"]["CVE-2025-0001"] == {"score": 0.99993, "percentile": 0.99988, "date": "2026-10-13"}
    assert out["counts"] == {"scored": 2, "missing": 3}


def test_b03_10_the_snapshot_fetch_uses_the_real_feeds_adapter(tmp_path, fake_http):
    """The fetchers moved to app.feeds.HttpFeeds (batching and paging: B03.4, B03.5); --fetch saves their replies."""
    from app.feeds import FeedUrls, HttpFeeds

    fake_http.on("/osv", lambda seen: (200, {"vulns": [rec("GHSA-aaaa", ["CVE-2025-0001"], "langflow",
                                                           [{"introduced": "0"}], details="long text")]}
                                       if seen.body["package"]["name"] == "langflow" else {}))
    fake_http.on("/epss", lambda seen: (200, {"data": [
        {"cve": c, "epss": "0.1", "percentile": "0.5", "date": seen.query["date"]}
        for c in seen.query["cve"].split(",")]}))
    feeds = HttpFeeds(urls=FeedUrls.at(fake_http.url))

    build.fetch_additions(tmp_path, ["CVE-2025-0001", "CVE-2025-0002"], feeds=feeds)

    osv = json.loads((tmp_path / "osv.json").read_text())
    assert [r["id"] for r in osv["packages"]["PyPI/langflow"]] == ["GHSA-aaaa"]
    assert osv["packages"]["Go/github.com/ollama/ollama"] == []
    assert set(osv["packages"]["PyPI/langflow"][0]) == {"id", "aliases", "published", "modified", "affected"}
    epss = json.loads((tmp_path / "epss.json").read_text())
    assert epss["date"] == build.AS_OF and [r["cve"] for r in epss["rows"]] == ["CVE-2025-0001", "CVE-2025-0002"]


def test_a14_8_additions_built_from_a_small_fake_input(tmp_path):
    raw, out = tmp_path / "raw", tmp_path / "out"
    raw.mkdir(), out.mkdir()
    (raw / "osv.json").write_text(json.dumps({"retrieved": "2026-10-14", "packages": FAKE_OSV}))
    (raw / "epss.json").write_text(json.dumps(FAKE_EPSS))
    meta = add.build_additions(raw, out, FAKE_CVES, as_of="2026-10-13")
    osv = json.loads((out / "osv.json").read_text())
    assert osv["as_of"] == "2026-10-13" and sorted(osv["cves"]) == ["CVE-2025-0001", "CVE-2025-0003", "CVE-2025-0005"]
    assert osv["products"]["ollama"] == {"coverage": "package",
                                         "packages": [{"ecosystem": "Go", "name": "github.com/ollama/ollama"}]}
    assert json.loads((out / "epss.json").read_text())["scores"]["CVE-2025-0003"]["percentile"] == 0.12
    assert json.loads((out / "product_check.json").read_text())["counts"]["conflicting"] == 1
    assert meta["product_check"] == {"text_matched": 4, "confirmed": 1, "conflicting": 1, "unknown": 2}
    assert meta["osv"] == {"retrieved": "2026-10-14", "cves": 3} and meta["epss"]["scored"] == 2


def test_a14_6_manifest_licences_attributions_and_nvd_notice(built):
    m = json.loads((built / "manifest.json").read_text())
    s = {src["id"]: src for src in m["sources"]}
    assert list(s) == ["owasp_llm", "owasp_web", "atlas", "nvd", "kev", "osv", "epss"]
    assert all(src["licence"] and src["attribution"] for src in m["sources"])
    assert s["kev"]["licence"] == "CC0 1.0"
    assert s["nvd"]["notice"] == "This product uses the NVD API but is not endorsed or certified by the NVD."
    assert s["osv"]["licence"] == "CC-BY 4.0" and "GitHub Advisory Database" in s["osv"]["attribution"]
    assert s["epss"]["attribution"] == "EPSS by FIRST" and s["epss"]["as_of"] == "2026-10-13"
    pc = m["product_check"]
    assert pc["text_matched"] == 184 and pc["confirmed"] + pc["conflicting"] + pc["unknown"] == 184


@pytest.mark.parametrize("name", ["osv.json", "epss.json", "product_check.json", "manifest.json"])
def test_a14_1_committed_snapshot_is_what_the_build_gives(built, name):
    assert (built / name).read_bytes() == (FIXTURES / name).read_bytes()


def test_b01_1_snapshot_built_with_the_shared_code_matches_every_fixture(built):
    """B01 (#32): the script builds with app/cve_build.py, and every file it writes is unchanged."""
    from app import cve_build

    assert build.build_cves is cve_build.build_cves and add.osv_versions is cve_build.osv_versions
    written = sorted(p.relative_to(built).as_posix() for p in built.rglob("*") if p.is_file())
    assert len(written) == 28  # 8 JSON files and 20 OWASP pages: fixtures/ minus fake_script.json and fake_feeds/
    for name in written:
        assert (built / name).read_bytes() == (FIXTURES / name).read_bytes(), name

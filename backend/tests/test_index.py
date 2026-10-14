"""Moved from proto with its module (old ids kept in the names). Check id: A06.1."""
from app.rag.index import Filters


def test_a06_1_r4_ordered_by_score(shared):
    _, index = shared
    hits = index.search("indirect prompt injection", k=5)
    assert len(hits) == 5
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_a06_1_s2_product_severity_date_filter(shared):
    _, index = shared
    f = Filters(product="langflow", severity_min="CRITICAL", date_from="2026-01-01")
    hits = index.search("remote code execution", k=50, filters=f)
    assert hits
    assert all(h.chunk.product == "langflow" and h.chunk.severity == "CRITICAL" and h.chunk.date >= "2026-01-01"
               for h in hits)


def test_a06_1_s2_severity_min_is_this_or_worse(shared):
    _, index = shared
    hits = index.search("vulnerability", k=200, filters=Filters(severity_min="HIGH"))
    assert {h.chunk.severity for h in hits} <= {"HIGH", "CRITICAL"}
    assert {h.chunk.severity for h in hits} == {"HIGH", "CRITICAL"}


def test_a06_1_s2_cve_only_filters_exclude_other_docs(shared):
    _, index = shared
    assert all(h.chunk.doc_type == "cve" for h in index.search("prompt injection", 50, Filters(kev=True)))
    assert all(h.chunk.kev for h in index.search("code", 50, Filters(kev=True)))


def test_a06_1_s2_owasp_matches_page_and_mapped_cves(shared):
    _, index = shared
    hits = index.search("injection", k=100, filters=Filters(owasp="A05"))
    kinds = {h.chunk.doc_type for h in hits}
    assert kinds == {"owasp_web", "cve"}
    assert all(h.chunk.doc_id == "A05" or h.chunk.owasp == "A05" for h in hits)


def test_a06_1_s2_date_filter_excludes_undated_docs(shared):
    _, index = shared
    hits = index.search("prompt injection", 50, Filters(date_from="2020-01-01"))
    assert hits and all(h.chunk.date for h in hits)


def test_a06_1_r6_no_shared_words_no_hits(shared):
    _, index = shared
    assert index.search("zzqx vlorp blenth") == []

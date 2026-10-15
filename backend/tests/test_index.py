"""Search over real Chroma (temp folder, hash vectors). Moved from proto (old ids kept in the names) and
extended for Chroma. Check ids: A06.1, A09.3, A09.4, A09.5."""
import pytest

from app.rag.index import Filters, where

# Every filter case from the prototype, plus combinations. Each must hold against Chroma (A09.3, A09.5).
FILTER_CASES = [
    ("remote code execution", Filters(product="langflow", severity_min="CRITICAL", date_from="2026-01-01")),
    ("vulnerability", Filters(severity_min="HIGH")),
    ("vulnerability", Filters(severity_min="MEDIUM", date_to="2025-06-30")),
    ("server", Filters(kev=True)),
    ("code", Filters(kev=True)),
    ("injection", Filters(owasp="A05")),
    ("prompt injection", Filters(owasp="LLM01")),
    ("prompt injection", Filters(date_from="2020-01-01")),
    ("model", Filters(doc_type="atlas_technique")),
    ("data", Filters(doc_type="owasp_llm")),
    ("server", Filters(product="ollama", date_from="2025-01-01", date_to="2025-12-31")),
    ("injection", Filters(doc_type="cve", owasp="A05", severity_min="HIGH", kev=False)),
]


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
    assert {h.chunk.severity for h in hits} == {"HIGH", "CRITICAL"}


def test_a06_1_s2_cve_only_filters_exclude_other_docs(shared):
    _, index = shared
    assert all(h.chunk.doc_type == "cve" for h in index.search("prompt injection", 50, Filters(kev=True)))
    assert all(h.chunk.kev for h in index.search("code", 50, Filters(kev=True)))


def test_a06_1_s2_owasp_matches_page_and_mapped_cves(shared):
    _, index = shared
    hits = index.search("injection", k=100, filters=Filters(owasp="A05"))
    assert {h.chunk.doc_type for h in hits} == {"owasp_web", "cve"}
    assert all(h.chunk.doc_id == "A05" or h.chunk.owasp == "A05" for h in hits)


def test_a06_1_s2_date_filter_excludes_undated_docs(shared):
    _, index = shared
    hits = index.search("prompt injection", 50, Filters(date_from="2020-01-01"))
    assert hits and all(h.chunk.date for h in hits)


@pytest.mark.parametrize(("query", "filters"), FILTER_CASES)
def test_a09_5_filtered_search_never_leaves_the_filter(shared, query, filters):
    _, index = shared
    hits = index.search(query, k=100, filters=filters)
    assert hits, "each case should find something"
    outside = [h.chunk.chunk_id for h in hits if not filters.matches(h.chunk)]
    assert outside == []


def test_a09_3_date_to_includes_the_whole_day(shared):
    _, index = shared
    day = "2026-05-15"  # 59 CVEs published that day, with times after midnight
    hits = index.search("vulnerability", k=500, filters=Filters(date_from=day, date_to=day))
    assert hits and all(h.chunk.date[:10] == day for h in hits)


def test_a09_3_where_is_an_and_of_single_conditions():
    w = where(Filters(product="langflow", severity_min="HIGH", date_from="2026-01-01", date_to="2026-03-31", kev=True))
    assert w == {"$and": [
        {"doc_type": "cve"},
        {"product": "langflow"},
        {"severity_rank": {"$gte": 3}},
        {"kev": True},
        {"date": {"$gte": 20260101}},
        {"date": {"$lte": 20260331}},
    ]}


def test_a09_3_where_single_condition_and_none():
    assert where(Filters()) is None
    assert where(Filters(doc_type="owasp_llm")) == {"doc_type": "owasp_llm"}
    assert where(Filters(severity_min="LOW")) == {"$and": [{"doc_type": "cve"}, {"severity_rank": {"$gte": 1}}]}
    assert where(Filters(owasp="A05")) == {"$or": [{"owasp": "A05"}, {"doc_id": "A05"}]}


def test_a06_1_r6_off_topic_finds_nothing(shared):
    _, index = shared
    assert index.search("zzqx vlorp blenth") == []


def test_a09_4_off_topic_is_cut_by_the_score_threshold_not_a_word_gate(shared):
    # With the threshold at 0, hash collisions surface: proof there is no shared-word gate any more.
    _, index = shared
    assert index.search("zzqx vlorp blenth", min_score=0.0)
    assert index.search("zzqx vlorp blenth", min_score=index.min_score) == []


def test_a09_4_stop_words_only_finds_nothing(shared):
    _, index = shared
    assert index.search("the a of") == []

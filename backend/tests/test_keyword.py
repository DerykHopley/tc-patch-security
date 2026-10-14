"""Keyword search (BM25) and hybrid fusion. Check ids: A10.1 tokeniser, A10.2 filters, A10.3 fusion and weight,
A10.4 which retriever found each source, A10.5 exact ids and product names come first through BM25."""
import pytest

from app.llm.base import LLMReply, QueryPlan
from app.llm.fake import FakeLLM
from app.rag.index import Filters
from app.rag.keyword import BM25Index, tokenize
from app.rag.pipeline import SearchOptions, search_security
from tests.test_index import FILTER_CASES


def test_a10_1_tokeniser_keeps_ids_whole():
    tokens = tokenize("Explain CVE-2024-8309, CWE-918 and AML.T0051.001 please.")
    assert {"cve-2024-8309", "cwe-918", "aml.t0051.001"} <= set(tokens)
    # an id is never split into parts that would match other ids
    assert "2024" not in tokens and "918" not in tokens and "t0051" not in tokens


def test_a10_1_tokeniser_words_lowercase_no_stop_words_no_trailing_dot():
    assert tokenize("The Prompt Injection, in an LLM app.") == ["prompt", "injection", "llm", "app"]


def test_a10_1_tokeniser_compound_names_whole_and_in_parts():
    # "Open WebUI" and "open-webui" must both match a chunk that says either
    assert {"open-webui", "open", "webui"} <= set(tokenize("open-webui"))
    assert {"llama.cpp", "llama", "cpp"} <= set(tokenize("llama.cpp server"))


@pytest.fixture(scope="module")
def bm25(index):
    return BM25Index(index.chunks)  # the same chunks as Chroma


@pytest.mark.parametrize("query, check", [
    ("explain CVE-2024-8309", lambda c: c.doc_id == "CVE-2024-8309"),
    ("what is CWE-918?", lambda c: "CWE-918" in c.text or "CWE-918" in c.cwes),
    ("AML.T0051.001", lambda c: c.doc_id == "AML.T0051.001"),
    ("LlamaIndex vulnerabilities", lambda c: c.product == "llamaindex"),
])
def test_a10_5_bm25_finds_exact_ids_and_products_first(bm25, query, check):
    hits = bm25.search(query, k=5)
    assert hits and check(hits[0].chunk), [h.chunk.chunk_id for h in hits]
    assert [h.score for h in hits] == sorted((h.score for h in hits), reverse=True)


def test_a10_5_bm25_finds_nothing_for_unknown_words(bm25):
    assert bm25.search("zzqx vlorp blenth") == []


@pytest.mark.parametrize("query, filters", FILTER_CASES)
def test_a10_2_bm25_never_returns_a_chunk_outside_the_filter(bm25, query, filters):
    hits = bm25.search(query, k=1000, filters=filters)
    assert hits, "each case should match something, or it proves nothing"
    assert all(filters.matches(h.chunk) for h in hits)  # the rule Chroma's `where` is tested against (A09.3)


# --- Hybrid search: both retrievers per query, fused by RRF (A10.2 to A10.5) ---

class PlanLLM(FakeLLM):
    def __init__(self, semantic_query, rewrites=(), filters=None):
        super().__init__()
        self.plan = QueryPlan(semantic_query=semantic_query, rewrites=list(rewrites), filters=filters or {})

    def translate(self, question):
        return self.plan, LLMReply(estimated=True)


class Missing:
    """A vector side that finds nothing: the case where only exact words can help."""
    def search(self, query, k=10, filters=None):
        return []


class Recording:
    def __init__(self, inner):
        self.inner, self.calls = inner, []

    def search(self, query, k=10, filters=None):
        self.calls.append((query, filters))
        return self.inner.search(query, k, filters)


def hybrid(deps, llm, keyword, vector=None, opts=None):
    retrievers = {"vector": vector or deps.index, "keyword": keyword}
    return search_security("x", llm, retrievers, deps.knowledge.resolve_product, opts=opts)


@pytest.mark.parametrize("query, check", [
    ("explain CVE-2024-8309", lambda s: s.doc_id == "CVE-2024-8309"),
    ("what is CWE-918?", lambda s: s.doc_id == "A01" or s.doc_type == "cve"),
    ("AML.T0051.001", lambda s: s.doc_id == "AML.T0051.001"),
    ("LlamaIndex vulnerabilities", lambda s: s.product == "llamaindex"),
])
def test_a10_5_ids_and_products_first_even_when_vector_misses(deps, bm25, query, check):
    res = hybrid(deps, PlanLLM(query), bm25, vector=Missing())
    first = res.sources[0]
    assert first.n == 1 and check(first), [s.chunk_id for s in res.sources]
    assert res.query.found_by[1] == ["keyword"]


def test_a10_3_every_query_runs_on_both_retrievers_with_the_same_filters(deps, bm25):
    vector, keyword = Recording(deps.index), Recording(bm25)
    llm = PlanLLM("prompt injection", rewrites=["indirect prompt injection", "jailbreak defence"],
                  filters={"doc_type": "owasp_llm"})
    res = hybrid(deps, llm, keyword, vector=vector)
    queries = ["prompt injection", "indirect prompt injection", "jailbreak defence"]
    assert [q for q, _ in vector.calls] == queries and [q for q, _ in keyword.calls] == queries
    assert {f for _, f in vector.calls + keyword.calls} == {Filters(doc_type="owasp_llm")}
    assert [(r, q) for r, q, _ in res.lists] == [(r, q) for q in queries for r in ("vector", "keyword")]


@pytest.mark.parametrize("filters", [
    {"doc_type": "owasp_llm"},
    {"product": "langflow", "severity_min": "CRITICAL", "date_from": "2026-01-01"},
    {"kev": "true"},
    {"owasp": "A05"},
])
def test_a10_2_filtered_hybrid_search_stays_inside_the_filter(deps, bm25, filters):
    res = hybrid(deps, PlanLLM("injection vulnerability in a server", filters=filters), bm25)
    kept = Filters(**{k: (v == "true") if k == "kev" else v for k, v in filters.items()})
    assert res.sources and not res.query.relaxed
    for _, _, hits in res.lists:
        assert all(kept.matches(h.chunk) for h in hits)


def test_a10_3_fused_by_rrf_then_capped_per_document(deps, bm25):
    res = hybrid(deps, PlanLLM("prompt injection", rewrites=["indirect prompt injection"]), bm25)
    # Σ 1/(k + rank) worked out by hand for the first source, from the ranked lists the pipeline reports
    first = res.sources[0].chunk_id
    expected = sum(1 / (60 + rank) for _, _, hits in res.lists
                   for rank, h in enumerate(hits, start=1) if h.chunk.chunk_id == first)
    assert res.fused[0] == (first, pytest.approx(expected))
    docs = [s.doc_id for s in res.sources]
    assert all(docs.count(d) <= 2 for d in docs) and len(res.sources) == 5


def test_a10_3_keyword_weight_is_a_search_setting(deps, bm25):
    llm = PlanLLM("explain CVE-2024-8309")
    assert SearchOptions().keyword_weight == 0.5  # the default: plain RRF, both sides count the same
    vector_only = hybrid(deps, llm, bm25, opts=SearchOptions(keyword_weight=0.0))
    keyword_only = hybrid(deps, llm, bm25, opts=SearchOptions(keyword_weight=1.0))
    assert {r for r, _, _ in vector_only.lists} == {"vector"}
    assert {r for r, _, _ in keyword_only.lists} == {"keyword"}
    assert set(map(tuple, keyword_only.query.found_by.values())) == {("keyword",)}
    # between the ends, a list's RRF terms are scaled: keyword lists by 2w, vector lists by 2(1 - w)
    tilted = hybrid(deps, llm, bm25, vector=Missing(), opts=SearchOptions(keyword_weight=0.75))
    assert tilted.fused[0][1] == pytest.approx(1.5 / 61)


def test_a10_4_query_plan_says_which_retriever_found_each_source(deps, bm25):
    res = hybrid(deps, PlanLLM("prompt injection in LangChain"), bm25)
    assert set(res.query.found_by) == {s.n for s in res.sources}
    assert ["keyword", "vector"] in res.query.found_by.values()  # some source was found by both
    for s in res.sources:
        for name in res.query.found_by[s.n]:
            assert any(r == name and any(h.chunk.chunk_id == s.chunk_id for h in hits) for r, _, hits in res.lists)


def test_a10_4_chat_reply_query_plan_names_the_retrievers(client):
    body = client.post("/chat", json={"message": "How do I protect a RAG app from indirect prompt injection?"}).json()
    found_by = body["query"]["found_by"]
    assert body["sources"] and set(found_by) == {str(s["n"]) for s in body["sources"]}
    assert all(v and set(v) <= {"keyword", "vector"} for v in found_by.values())

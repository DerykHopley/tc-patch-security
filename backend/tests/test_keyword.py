"""Keyword search (BM25) and hybrid fusion. Check ids: A10.1 tokeniser, A10.2 filters, A10.3 fusion and weight,
A10.4 which retriever found each source, A10.5 exact ids and product names come first through BM25."""
import pytest

from app.rag.keyword import BM25Index, tokenize
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

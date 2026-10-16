"""The off-topic gate (#53): when no vector hit reaches the embedder's threshold, keyword (BM25) hits are dropped too,
unless the question names an exact id or product the index knows. Check ids: F53.<n>."""
import pytest

from app.evals.retrieval import OFF_TOPIC
from app.llm.base import LLMReply, QueryPlan
from app.llm.fake import FakeLLM
from app.rag.keyword import BM25Index
from app.rag.pipeline import search_security
from app.rag.vector import ChromaIndex


class PlanLLM(FakeLLM):
    def __init__(self, semantic_query, rewrites=()):
        super().__init__()
        self.plan = QueryPlan(semantic_query=semantic_query, rewrites=list(rewrites), filters={})

    def translate(self, question):
        return self.plan, LLMReply(estimated=True)


class Missing:
    """A vector side where nothing reaches the threshold: what a real embedder may do for an id-only question."""
    def search(self, query, k=10, filters=None):
        return []


@pytest.fixture(scope="module")
def bm25(index):
    return BM25Index(index.chunks)


# The hash embedder matches shared words, so "poem" or "guitar" score up to 0.26 against some chunk, above its 0.15
# collision floor. A real embedder's threshold separates topics (A20); this one stands in for it: the same index,
# opened with a threshold above every off-topic score the hash embedder gives.
STRICT = 0.3


@pytest.fixture(scope="module")
def strict(index):
    return ChromaIndex(index.collection, index.chunks, index.embedder, min_score=STRICT)


def hybrid(deps, query, keyword, vector=None):
    retrievers = {"vector": vector or deps.index, "keyword": keyword}
    return search_security(query, PlanLLM(query), retrievers, deps.knowledge.resolve_product)


@pytest.mark.parametrize("question", OFF_TOPIC)
def test_f53_1_off_topic_question_gets_no_keyword_sources(deps, bm25, strict, question):
    res = hybrid(deps, question, bm25, vector=strict)
    assert res.sources == []
    assert res.query.off_topic is True
    assert all(hits == [] for name, _, hits in res.lists if name == "keyword")


@pytest.mark.parametrize("question, check", [
    ("CVE-2024-8309", lambda s: s.doc_id == "CVE-2024-8309"),
    ("cwe-918", lambda s: s.doc_id == "A01" or s.doc_type == "cve"),
    ("AML.T0051.001", lambda s: s.doc_id == "AML.T0051.001"),
    ("LLM01", lambda s: s.doc_id == "LLM01"),
    ("LlamaIndex", lambda s: s.product == "llamaindex"),
    ("anything new in Open WebUI?", lambda s: s.product == "open-webui"),
])
def test_f53_2_exact_id_or_product_is_never_off_topic(deps, bm25, question, check):
    res = hybrid(deps, question, bm25, vector=Missing())
    assert res.query.off_topic is False
    assert res.sources and check(res.sources[0]), [s.chunk_id for s in res.sources]


@pytest.mark.parametrize("question", ["Who won the football world cup in 2022?", "llm security tips", "zzqx-123"])
def test_f53_2_numbers_and_unknown_ids_do_not_open_the_gate(deps, bm25, question):
    # a year or an id the index lacks is not an exact match; plain words go through the vector side
    assert hybrid(deps, question, bm25, vector=Missing()).query.off_topic is True


# BM25 finds "learning" (machine learning) in many chunks; for the hash embedder the made-up words dilute the one shared word
# below its threshold. A stand-in for an off-topic question under a real embedder, for the playground.
GATED = "learning zzqa zzqb zzqc zzqd zzqe zzqf zzqg"


def test_f53_4_playground_says_the_gate_closed(client, bm25):
    assert bm25.search(GATED), "BM25 must match something, or the gate proves nothing"
    body = client.post("/dev/search", json={"query": GATED}).json()
    assert body["query"]["off_topic"] is True
    assert [len(l["hits"]) for l in body["lists"] if l["retriever"] == "keyword"] == [0]
    assert body["final"] == []
    assert client.post("/dev/search", json={"query": "prompt injection"}).json()["query"]["off_topic"] is False


def test_f53_3_retrieval_check_records_where_the_gate_closes(deps, bm25, strict):
    from app.evals import retrieval

    # with a topic-level threshold, BM25's hits are dropped for every off-topic question
    t = retrieval.run(deps, strict, bm25)["threshold"]
    assert all(x["gated"] for x in t["off_topic"])
    # with the configured embedder's threshold (here the hash one), the gate costs no real question
    t = retrieval.run(deps, deps.index, bm25)["threshold"]
    assert [x["id"] for x in t["on_topic"] if x["gated"]] == []

"""Moved from proto with its module (old ids kept in the names). Check id: A06.1."""
from app.llm.base import LLMReply, QueryPlan
from app.llm.fake import FakeLLM
from app.rag.pipeline import PER_DOC_CAP, search_security

Q1 = "Which critical Langflow vulnerabilities were published in 2026?"


class PlanLLM(FakeLLM):
    def __init__(self, plan):
        super().__init__()
        self.plan = plan

    def translate(self, question):
        return self.plan, LLMReply(estimated=True)


def run(deps, query, llm=None):
    return search_security(query, llm or deps.llm, deps.retrievers, deps.knowledge.resolve_product)


def test_a06_1_s5_q1_only_critical_langflow_2026(deps):
    res = run(deps, Q1)
    assert res.sources
    for s in res.sources:
        assert (s.doc_type, s.product, s.severity) == ("cve", "langflow", "CRITICAL") and s.date >= "2026-01-01"
    assert res.query.filters == {"doc_type": "cve", "product": "langflow", "severity_min": "CRITICAL",
                                 "date_from": "2026-01-01"}


def test_a06_1_qt1_qt3_rewrites_in_reply(deps):
    res = run(deps, "How do I protect a RAG app from indirect prompt injection?")
    assert len(res.query.rewrites) == 3


def test_a06_1_r5_at_most_two_chunks_per_doc(deps):
    res = run(deps, "How do I protect a RAG app from indirect prompt injection?")
    docs = [s.doc_id for s in res.sources]
    assert all(docs.count(d) <= PER_DOC_CAP for d in docs)


def test_a06_1_s3_bad_filters_dropped_and_listed(deps):
    llm = PlanLLM(QueryPlan(semantic_query="prompt injection",
                            filters={"product": "NotAProduct", "severity_min": "huge", "date_from": "last week",
                                     "doc_type": "OWASP_LLM", "owasp": "llm01"}))
    res = run(deps, "x", llm)
    assert res.query.filters == {"doc_type": "owasp_llm", "owasp": "LLM01"}
    assert sorted(res.query.dropped_filters) == ["date_from=last week", "product=NotAProduct", "severity_min=huge"]


def test_a06_1_s3_product_aliases(deps):
    llm = PlanLLM(QueryPlan(semantic_query="xss", filters={"product": "OpenWebUI"}))
    assert run(deps, "x", llm).query.filters == {"product": "open-webui"}


def test_a06_1_s4_relaxed_when_filters_leave_nothing(deps):
    llm = PlanLLM(QueryPlan(semantic_query="prompt injection", filters={"product": "llamaindex", "kev": "true"}))
    res = run(deps, "x", llm)
    assert res.query.relaxed is True and res.sources


def test_a06_1_r8_full_text_for_llm_snippet_for_ui(deps):
    res = run(deps, "How do I protect a RAG app from indirect prompt injection?")
    long = [s for s in res.sources if len(res.texts[s.n]) > 300]
    assert long, "expected at least one chunk longer than the snippet"
    for s in long:
        assert len(s.snippet) == 300 and res.texts[s.n].startswith(s.snippet)


def test_a06_1_r6_nonsense_finds_nothing(deps):
    assert run(deps, "zzqx vlorp blenth").sources == []

"""The search_security pipeline: translate → search each query on each retriever → fuse → cap per document (T1).

Hybrid search (A10): the vector retriever (Chroma) and the keyword retriever (BM25) both run every query; a source's
score is its fused RRF score, since a cosine and a BM25 score can't be compared.
"""
from dataclasses import dataclass

from app import guard
from app.llm.base import LLM, LLMReply
from app.rag.chunking import Chunk
from app.rag.fusion import rrf
from app.rag.index import Filters, Hit, Retriever
from app.schemas import QueryInfo, Source

PER_DOC_CAP = 2  # R5
PER_QUERY_K = 10
SNIPPET = 300  # R8: the UI gets a snippet, the LLM the full chunk


@dataclass(frozen=True)
class SearchOptions:
    """The dev panel's search settings (X2). The defaults are the SPEC's values."""
    top_n: int = 5
    per_query_k: int = PER_QUERY_K
    per_doc_cap: int = PER_DOC_CAP
    rrf_k: int = 60
    use_rewrites: bool = True  # off: one search for the semantic query only
    use_filters: bool = True  # off: the LLM's filters are listed as dropped, not applied
    keyword_weight: float = 0.5  # A10: keyword (BM25) vs vector in the fusion; 0 = vector only, 1 = keyword only


@dataclass
class SearchResult:
    query: QueryInfo
    sources: list[Source]
    texts: dict[int, str]  # n -> full chunk text, for the LLM (R8)
    reply: LLMReply  # the translate call, for usage
    lists: list[tuple[str, str, list[Hit]]]  # (retriever, query, ranked hits) before fusion, for the dev panel
    fused: list[tuple[str, float]]  # (chunk_id, RRF score)


def to_source(n: int, c: Chunk, score: float | None) -> Source:
    return Source(
        n=n, chunk_id=c.chunk_id, doc_id=c.doc_id, doc_type=c.doc_type, title=c.title, section=c.section,
        date=c.date, url=c.url, snippet=c.text[:SNIPPET], score=None if score is None else round(score, 4),
        product=c.product, severity=c.severity, cvss=c.cvss, kev=c.kev if c.doc_type == "cve" else None,
    )


def _search_all(retrievers: dict[str, Retriever], queries: list[str], filters: Filters,
                k: int) -> list[tuple[str, str, list[Hit]]]:
    f = None if filters.is_empty() else filters
    return [(name, q, r.search(q, k, f)) for q in queries for name, r in retrievers.items()]


def _active(retrievers: dict[str, Retriever], keyword_weight: float) -> dict[str, float]:
    """Each retriever's RRF weight. 0.5 is plain RRF; at 0 or 1 the other side isn't run at all."""
    weights = {"keyword": 2 * keyword_weight, "vector": 2 * (1 - keyword_weight)}
    return {name: weights.get(name, 1.0) for name in retrievers if weights.get(name, 1.0) > 0}


def search_security(query: str, llm: LLM, retrievers: dict[str, Retriever], resolve_product,
                    top_n: int | None = None, start_n: int = 1, opts: SearchOptions | None = None) -> SearchResult:
    """`retrievers` by name ("vector", "keyword"): every query runs on each, all lists are fused by RRF (A10)."""
    opts = opts or SearchOptions()
    top_n = top_n or opts.top_n
    plan, reply = llm.translate(query)  # Q-T1, S1
    kept, dropped = guard.validate_filters(plan.filters, resolve_product)  # S3
    if not opts.use_filters:
        dropped += [f"{k}={v} (filters off)" for k, v in kept.items()]
        kept = {}
    filters = Filters(**kept)
    queries = [plan.semantic_query, *(plan.rewrites if opts.use_rewrites else [])]
    weights = _active(retrievers, opts.keyword_weight)
    active = {name: retrievers[name] for name in weights}

    lists = _search_all(active, queries, filters, opts.per_query_k)
    relaxed = False
    if not any(hits for _, _, hits in lists) and not filters.is_empty():  # S4
        lists = _search_all(active, queries, Filters(), opts.per_query_k)
        relaxed = True

    chunks: dict[str, Chunk] = {}
    found_by: dict[str, set[str]] = {}
    for name, _, hits in lists:
        for h in hits:
            chunks[h.chunk.chunk_id] = h.chunk
            found_by.setdefault(h.chunk.chunk_id, set()).add(name)

    per_doc: dict[str, int] = {}
    picked: list[tuple[Chunk, float]] = []
    fused = rrf([[h.chunk.chunk_id for h in hits] for _, _, hits in lists], k=opts.rrf_k,
                weights=[weights[name] for name, _, _ in lists])  # Q-T2
    for cid, score in fused:
        chunk = chunks[cid]
        if per_doc.get(chunk.doc_id, 0) >= opts.per_doc_cap:  # R5
            continue
        per_doc[chunk.doc_id] = per_doc.get(chunk.doc_id, 0) + 1
        picked.append((chunk, score))
        if len(picked) == top_n:
            break

    sources = [to_source(start_n + i, c, score) for i, (c, score) in enumerate(picked)]
    info = QueryInfo(
        original=query, semantic_query=plan.semantic_query,
        rewrites=plan.rewrites if opts.use_rewrites else [],
        filters={k: str(v).lower() if isinstance(v, bool) else v for k, v in kept.items()},
        dropped_filters=dropped, relaxed=relaxed,
        found_by={s.n: sorted(found_by[s.chunk_id]) for s in sources},
    )
    return SearchResult(query=info, sources=sources, texts={s.n: c.text for s, (c, _) in zip(sources, picked)},
                        reply=reply, lists=lists, fused=fused)

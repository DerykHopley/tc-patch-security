"""The search_security pipeline: translate → search each query → fuse → cap per document (T1)."""
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


@dataclass
class SearchResult:
    query: QueryInfo
    sources: list[Source]
    texts: dict[int, str]  # n -> full chunk text, for the LLM (R8)
    reply: LLMReply  # the translate call, for usage
    lists: list[tuple[str, list[Hit]]]  # (query, ranked hits) before fusion, for the dev panel
    fused: list[tuple[str, float]]  # (chunk_id, RRF score)


def to_source(n: int, c: Chunk, score: float | None) -> Source:
    return Source(
        n=n, chunk_id=c.chunk_id, doc_id=c.doc_id, doc_type=c.doc_type, title=c.title, section=c.section,
        date=c.date, url=c.url, snippet=c.text[:SNIPPET], score=None if score is None else round(score, 3),
        product=c.product, severity=c.severity, cvss=c.cvss, kev=c.kev if c.doc_type == "cve" else None,
    )


def _search_all(index: Retriever, queries: list[str], filters: Filters, k: int) -> list[list[Hit]]:
    return [index.search(q, k, None if filters.is_empty() else filters) for q in queries]


def search_security(query: str, llm: LLM, index: Retriever, resolve_product, top_n: int | None = None,
                    start_n: int = 1, opts: SearchOptions | None = None) -> SearchResult:
    opts = opts or SearchOptions()
    top_n = top_n or opts.top_n
    plan, reply = llm.translate(query)  # Q-T1, S1
    kept, dropped = guard.validate_filters(plan.filters, resolve_product)  # S3
    if not opts.use_filters:
        dropped += [f"{k}={v} (filters off)" for k, v in kept.items()]
        kept = {}
    filters = Filters(**kept)
    queries = [plan.semantic_query, *(plan.rewrites if opts.use_rewrites else [])]

    lists = _search_all(index, queries, filters, opts.per_query_k)
    relaxed = False
    if not any(lists) and not filters.is_empty():  # S4
        lists = _search_all(index, queries, Filters(), opts.per_query_k)
        relaxed = True

    best: dict[str, Hit] = {}
    for hits in lists:
        for h in hits:
            if h.chunk.chunk_id not in best or h.score > best[h.chunk.chunk_id].score:
                best[h.chunk.chunk_id] = h

    per_doc: dict[str, int] = {}
    picked: list[Hit] = []
    fused = rrf([[h.chunk.chunk_id for h in hits] for hits in lists], k=opts.rrf_k)  # Q-T2
    for cid, _ in fused:
        hit = best[cid]
        if per_doc.get(hit.chunk.doc_id, 0) >= opts.per_doc_cap:  # R5
            continue
        per_doc[hit.chunk.doc_id] = per_doc.get(hit.chunk.doc_id, 0) + 1
        picked.append(hit)
        if len(picked) == top_n:
            break

    sources = [to_source(start_n + i, h.chunk, h.score) for i, h in enumerate(picked)]
    info = QueryInfo(
        original=query, semantic_query=plan.semantic_query,
        rewrites=plan.rewrites if opts.use_rewrites else [],
        filters={k: str(v).lower() if isinstance(v, bool) else v for k, v in kept.items()},
        dropped_filters=dropped, relaxed=relaxed,
    )
    return SearchResult(query=info, sources=sources, texts={s.n: h.chunk.text for s, h in zip(sources, picked)},
                        reply=reply, lists=list(zip(queries, lists)), fused=fused)

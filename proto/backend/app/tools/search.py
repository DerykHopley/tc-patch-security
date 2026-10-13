"""search_security (T1): the query-translation and self-query pipeline as a tool."""
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.rag.pipeline import SearchOptions, search_security
from app.tools.registry import ToolSpec, register


class SearchArgs(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def run(args: SearchArgs, deps, ctx) -> dict:
    dev = deps.state.settings().dev  # X2: the dev panel's search settings, read per request
    opts = SearchOptions(top_n=dev.top_n, per_query_k=dev.per_query_k, per_doc_cap=dev.per_doc_cap,
                         rrf_k=dev.rrf_k, use_rewrites=dev.use_rewrites, use_filters=dev.use_filters)
    res = search_security(args.query, deps.llm, deps.index, deps.knowledge.resolve_product,
                          start_n=len(ctx.sources) + 1, opts=opts)
    ctx.add_usage(res.reply)
    ctx.sources.extend(res.sources)
    ctx.query = res.query
    keep = {"n", "doc_id", "doc_type", "title", "section", "date", "product", "severity", "kev"}
    return {
        "query": res.query.model_dump(),
        # The LLM gets the full chunk text, not the UI snippet (R8).
        "sources": [s.model_dump(include=keep, exclude_none=True) | {"text": res.texts[s.n]} for s in res.sources],
    }


register(ToolSpec(
    name="search_security",
    description=("Search the LLM-security knowledge base: OWASP Top 10 for LLM apps, OWASP Top 10 (web), "
                 "MITRE ATLAS, and CVEs in LLM products. Returns numbered sources; cite them as [n]."),
    args_model=SearchArgs,
    run=run,
))

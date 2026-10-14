"""search_security (T1): the query-translation and self-query pipeline as a tool."""
from typing import Annotated

from pydantic import BaseModel, StringConstraints

from app.rag.pipeline import SearchOptions, search_security
from app.tools.registry import ToolSpec, register


class SearchArgs(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def run(args: SearchArgs, deps, ctx) -> dict:
    opts = SearchOptions()  # the defaults; the dev panel's search tuning arrives with A11
    res = search_security(args.query, deps.llm, deps.retrievers, deps.knowledge.resolve_product,
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

"""search_security (T1): the query-translation and self-query pipeline as a tool."""
from typing import Annotated, Literal

from pydantic import BaseModel, StringConstraints

from app.rag.pipeline import search_security
from app.schemas import QueryInfo
from app.tools.registry import Severity, ToolResult, ToolSpec, register


class SearchArgs(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


class FoundSource(ToolResult):
    """A numbered source with its full chunk text. A field the chunk doesn't have is absent."""
    n: int
    doc_id: str
    doc_type: Literal["owasp_llm", "owasp_web", "atlas_technique", "atlas_mitigation", "atlas_case", "cve"]
    title: str
    section: str = None  # type: ignore[assignment]
    date: str = None  # type: ignore[assignment]
    product: str = None  # type: ignore[assignment]  # the product id
    severity: Severity = None  # type: ignore[assignment]
    kev: bool = None  # type: ignore[assignment]
    text: str


class SearchResult(ToolResult):
    query: QueryInfo
    sources: list[FoundSource]


def run(args: SearchArgs, deps, ctx) -> dict:
    res = search_security(args.query, deps.llm, deps.retrievers, deps.knowledge.resolve_product,
                          start_n=len(ctx.sources) + 1, opts=deps.search_options())  # the dev panel's tuning (A11)
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
    result=SearchResult,
    run=run,
))

"""patch_guide (#148): one section of the Patch guide (app/guide.md), for questions about using Patch itself.

The section is a numbered `guide` source, cited as [n] like the knowledge base; its url is the in-app path, so the
chat's source list opens the page. Not offered by the MCP server: it is about the web app.
"""
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.guide import SECTIONS
from app.schemas import Source
from app.tools.registry import ToolResult, ToolSpec, register

Topic = Literal[tuple(SECTIONS)]  # type: ignore[valid-type]


class GuideArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    topic: Topic


class GuideResult(ToolResult):
    """patch_guide: one section of the guide, as numbered source n."""
    n: int
    topic: str
    title: str
    path: str | None  # where it is in the app, e.g. /settings#watchlist; None when it isn't a page
    text: str


def run(args: GuideArgs, deps, ctx) -> dict:
    s = SECTIONS[args.topic]
    n = len(ctx.sources) + 1
    ctx.sources.append(Source(n=n, chunk_id=f"guide-{args.topic}", doc_id=f"guide:{args.topic}", doc_type="guide",
                              title=f"Patch guide: {s.title}", url=s.path or "", snippet=s.text))
    return {"n": n, "topic": args.topic, "title": s.title, "path": s.path, "text": s.text}


register(ToolSpec(
    name="patch_guide",
    description="How to use Patch itself: one section of Patch's own guide, by topic (getting started, the pages, "
                "the watchlist and versions, the verdict, priority, the chat, proposals, alerts, live data and Check "
                "now, web research, roles, the Dev page, the MCP server, privacy). Returns the section as numbered "
                "source n, with where it is in the app (path). Answer from its text only and cite it as [n].",
    args_model=GuideArgs,
    result=GuideResult,
    run=run,
))

"""Patch as an MCP server (B23): four read-only chat tools for other assistants (Claude Desktop, Claude Code).

Run it with `uv run python -m app.mcp_server` (stdio). The client starts it as a subprocess; see the README.
"""
import logging
import sys
from dataclasses import replace
from typing import Annotated, Literal

import anyio
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server
from pydantic import StringConstraints

from app.config import Settings
from app.deps import build_deps
from app.errors import InputError, LLMError, ToolError
from app.guard import wrap_untrusted
from app.llm.base import ToolCall
from app.state import State
from app.tools import affected
from app.tools.affected import AffectedArgs
from app.tools.registry import TOOLS, Context, ToolSpec, run_tool
from app.verdict import USAGES, check_version

log = logging.getLogger(__name__)
ANNOTATIONS = types.ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True,
                                    openWorldHint=False)


class McpAffectedArgs(AffectedArgs):
    """The chat tool's arguments, plus the version (and usage) to check: an MCP caller has no watchlist here."""
    version: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=40)] | None = None
    usage: Literal[USAGES] | None = None  # type: ignore[valid-type]  # None: the product's default


class NoStack(State):
    """Nobody's stack: no statuses, decisions or saved settings, and no writes. Another assistant gets the
    snapshot's facts and the rules' verdict for the version it gives, never the owner's watchlist (B23).
    `product`, `fields`: check_affected's call, as a one-product watchlist that lives for that call only."""

    def __init__(self, state: State, product: str | None = None, fields: dict | None = None):
        super().__init__(state.path, state.k, state.defaults, state.dev_defaults)
        self._call = {"watchlist": [product] if product else [], "statuses": {}, "history": {},
                      "product_settings": {product: fields} if product else {}}

    def _load(self) -> dict:
        return self._call

    def _save(self, data: dict) -> None:
        raise PermissionError("The MCP server is read-only.")


def _check_affected(args: McpAffectedArgs, deps, ctx) -> dict:
    """The chat tool's rules, run on a watchlist of one: the product with the call's usage and version."""
    k = deps.knowledge
    cve = k.cves.get(args.cve_id) if args.cve_id else None
    pid = k.resolve_product(args.product) if args.product else (cve or {}).get("product")
    stack = deps.state
    if pid:
        if args.version:
            try:
                check_version(k.osv["products"].get(pid, {}), k.products[pid], args.version)
            except InputError as e:  # the plain message Settings gives for the same version
                raise ToolError(e.message, e.code) from None
        fields = {"version": args.version} | ({"usage": args.usage} if args.usage else {})
        stack = NoStack(deps.state, pid, fields)
    result = affected.run(args, replace(deps, state=stack), ctx)
    if "watch_status" in result:
        result["watch_status"] = "not_watched"  # a stand-in watchlist, not anyone's
    return result


SPECS: dict[str, ToolSpec] = {
    "search_security": TOOLS["search_security"],
    "lookup_cve": TOOLS["lookup_cve"],
    "explain_weakness": TOOLS["explain_weakness"],
    "check_affected": ToolSpec(
        name="check_affected",
        description="Am I affected? The version check's verdict (affected, not affected, unknown) with its reason, "
                    "the fixed version and who acts (you, upstream, vendor). Give the version you run, and cve_id "
                    "for one CVE or product for every CVE of that product in the snapshot, by verdict. usage "
                    "(self_hosted, library, transitive, hosted) decides who acts. Read-only.",
        args_model=McpAffectedArgs,
        result=TOOLS["check_affected"].result,
        run=_check_affected,
    ),
}


def build_server(deps) -> Server:
    deps = replace(deps, state=NoStack(deps.state))
    server = Server("patch")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        return [types.Tool(name=name, description=spec.description, inputSchema=spec.schema()["function"]["parameters"],
                           annotations=ANNOTATIONS) for name, spec in SPECS.items()]

    @server.call_tool(validate_input=False)  # our pydantic models validate, so errors match the chat's
    async def call_tool(name: str, arguments: dict | None) -> types.CallToolResult:
        return await anyio.to_thread.run_sync(answer, name, arguments or {}, deps)

    return server


def answer(name: str, arguments: dict, deps) -> types.CallToolResult:
    """One tool call, as the chat runs it: validate, run, check the shape; then wrapped as untrusted data."""
    ctx = Context()
    try:
        record = run_tool(ToolCall(id="mcp", name=name, args=arguments), deps, ctx, SPECS)
    except LLMError as e:  # search_security's query translation: the HTTP API's 502 message
        log.warning("LLM error in %s: %s", name, e.message)
        return _wrapped(name, {"error": {"code": "llm_error", "message": e.public or LLMError.GENERIC}}, error=True)
    if record.status == "error":
        return _wrapped(name, {"error": record.error}, error=True)
    sources = [{"n": s.n, "title": s.title, "doc_type": s.doc_type, "url": s.url} for s in ctx.sources]
    res = record.result
    if not sources and "url" in res:  # explain_weakness adds no chat source (#50): cite the page it explains
        sources = [{"n": 1, "title": " ".join(filter(None, (res["id"], res.get("name")))), "doc_type": res["kind"],
                    "url": res["url"]}]
    return _wrapped(name, {"result": record.result, "sources": sources})


def _wrapped(name: str, payload: dict, error: bool = False) -> types.CallToolResult:
    # No structuredContent: a client may hand that to its model as is, without the untrusted-data delimiters.
    return types.CallToolResult(content=[types.TextContent(type="text", text=wrap_untrusted(name, payload))],
                                isError=error)


async def serve_stdio(deps) -> None:
    server = build_server(deps)
    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:
    # stdout carries the protocol: every log line goes to stderr, which the client keeps as the server's log
    logging.basicConfig(stream=sys.stderr, level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    anyio.run(serve_stdio, build_deps(Settings.from_env()))


if __name__ == "__main__":
    main()

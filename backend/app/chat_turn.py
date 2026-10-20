"""One chat turn: a request in, Patch's reply out. /chat and the model check both run it (architecture review, 3).

In order: the guard checks the message and history and adds any flags (never blocks on them), the explain level is the
request's or else the saved one (A19), the page context keeps its checked fields and lists the rest as dropped (A18),
and the agent answers within the dev panel's step limit (A11). The same question at another explain level answers
from the last answer's search, so the sources match (#51, app.search_memory). A new request field is handled here,
once.
"""
from collections.abc import Collection

from app import agent, guard, page_context
from app.schemas import ChatReply, ChatRequest
from app.search_memory import Asked


def turn(req: ChatRequest, deps, fail_tools: Collection[str] | None = None) -> ChatReply:
    """`fail_tools`: tools that time out in this turn (B20); None = the server's switch (FAIL_TOOLS, the dev panel).
    The model check passes each question's own."""
    history = [t.model_dump() for t in req.history]
    message, flags = guard.check_message(req.message, history)  # limits and flags, before any LLM call
    level = req.explain_level or deps.state.settings().explain_level  # an override is for this message only
    page, dropped = page_context.validate(req.page, deps.knowledge.resolve_product)  # fixed fields only (A18)
    fail_tools = deps.fail_tools if fail_tools is None else fail_tools
    asked = Asked.of(message, page, deps.version, fail_tools)
    reply, search = agent.answer_and_search(message, history, deps, level=level, page=page, fail_tools=fail_tools,
                                            reuse=deps.searches.find(deps.user_id, asked, level))
    deps.searches.keep(deps.user_id, asked, level, search)
    reply.flags, reply.dropped_context = flags + reply.flags, dropped  # the message's flags, then the sources'
    return reply

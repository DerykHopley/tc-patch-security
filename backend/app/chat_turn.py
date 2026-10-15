"""One chat turn: a request in, Patch's reply out. /chat and the model check both run it (architecture review, 3).

In order: the guard checks the message and history and adds any flags (never blocks on them), the explain level is the
request's or else the saved one (A19), the page context keeps its checked fields and lists the rest as dropped (A18),
and the agent answers within the dev panel's step limit (A11). A new request field is handled here, once.
"""
from app import agent, guard, page_context
from app.schemas import ChatReply, ChatRequest


def turn(req: ChatRequest, deps) -> ChatReply:
    history = [t.model_dump() for t in req.history]
    message, flags = guard.check_message(req.message, history)  # limits and flags, before any LLM call
    level = req.explain_level or deps.state.settings().explain_level  # an override is for this message only
    page, dropped = page_context.validate(req.page, deps.knowledge.resolve_product)  # fixed fields only (A18)
    reply = agent.answer(message, history, deps, level=level, page=page)
    reply.flags, reply.dropped_context = flags, dropped
    return reply

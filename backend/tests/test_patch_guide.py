"""patch_guide (#148): Patch answers how-to questions about the app from one fixed guide. Check ids: F148.n.

Seams: the tool through run_tool (validate → run → check the shape), the chat through POST /chat with FakeLLM, the
MCP server through an in-memory MCP client, and the guide file against the frontend's own routes and anchors (read
from frontend/src, as test_tool_results reads toolResults.ts).
"""
import json
import re

import pytest

from app.config import ROOT
from app.llm.base import ToolCall
from app.tools.registry import Context, run_tool

FRONTEND = ROOT.parent / "frontend" / "src"
# The topics the owner decided on (#148). A test, not the code, holds them: dropping one fails here.
TOPICS = ["start", "dashboard", "cves", "cve_page", "watchlist_and_versions", "am_i_affected",
          "priority_and_due_dates", "chat_and_sources", "proposals", "alerts", "live_data_and_check_now",
          "web_research", "roles_and_access", "dev_page", "mcp_server", "privacy"]
HOW_TO = "How do I tell Patch which Langflow version I run?"


def guide(deps, ctx=None, **args):
    return run_tool(ToolCall(id="g", name="patch_guide", args=args), deps, ctx or Context())


# --- F148.1: arguments --------------------------------------------------------------------------------------------

@pytest.mark.parametrize("args", [{"topic": "nonsense"}, {"topic": ""}, {}, {"topic": "start", "extra": 1}])
def test_f148_1_an_unknown_or_missing_topic_is_bad_arguments(deps, args):
    rec = guide(deps, **args)
    assert rec.status == "error" and rec.error["code"] == "bad_arguments", rec


def test_f148_1_the_schema_lists_every_topic(deps):
    from app.tools.registry import TOOLS

    params = TOOLS["patch_guide"].schema()["function"]["parameters"]
    assert params["properties"]["topic"]["enum"] == TOPICS


# --- F148.2: the result, and the section as a citable source ----------------------------------------------------

def test_f148_2_returns_the_section_and_adds_it_as_a_numbered_guide_source(deps):
    ctx = Context()
    ctx.sources.append(_other_source())  # an earlier tool's source: the guide's number comes after it
    rec = guide(deps, ctx, topic="watchlist_and_versions")
    assert rec.status == "ok", rec.error
    r = rec.result
    assert set(r) == {"n", "topic", "title", "path", "text"}
    assert r["n"] == 2 and r["topic"] == "watchlist_and_versions" and r["path"] == "/settings#watchlist"
    assert "Settings" in r["text"] and "version" in r["text"].lower()
    src = ctx.sources[-1]
    assert (src.n, src.doc_type, src.url, src.doc_id) == (2, "guide", "/settings#watchlist", "guide:watchlist_and_versions")
    assert src.title == f"Patch guide: {r['title']}" and r["text"].startswith(src.snippet)


def test_f148_2_a_topic_outside_the_app_has_no_path_and_no_link(deps):
    ctx = Context()
    rec = guide(deps, ctx, topic="mcp_server")
    assert rec.status == "ok" and rec.result["path"] is None
    assert ctx.sources[0].url == ""


def _other_source():
    from app.schemas import Source
    return Source(n=1, chunk_id="c1", doc_id="d1", doc_type="cve", title="T", url="u", snippet="s")


# --- F148.3: every topic has a short section ------------------------------------------------------------------------

def test_f148_3_every_decided_topic_has_a_short_section():
    from app.guide import SECTIONS

    assert list(SECTIONS) == TOPICS
    for topic, s in SECTIONS.items():
        sentences = len(re.findall(r"[.!?](?:\s|$)", s.text))
        assert s.title and 3 <= sentences <= 10, (topic, sentences)
        assert "coming soon" not in s.text.lower()


# --- F148.4: every in-app path exists ------------------------------------------------------------------------------

def _routes() -> set[str]:
    block = re.search(r"export const PATHS[^{]*\{(.*?)\n\}", (FRONTEND / "route.ts").read_text(), re.S).group(1)
    return set(re.findall(r"'(/[^']*)'", block))


def _anchors() -> set[str]:
    found = set()
    for f in FRONTEND.rglob("*.tsx"):
        if ".test." not in f.name:
            found |= set(re.findall(r'\b(?:anchor|id)="([a-z][a-z0-9-]*)"', f.read_text()))
    return found


def test_f148_4_every_path_in_the_guide_is_a_route_and_its_anchor_exists():
    from app.guide import SECTIONS

    routes, anchors = _routes(), _anchors()
    assert {"/", "/cves", "/settings", "/dev"} <= routes  # the reader found the routes
    paths = [s.path for s in SECTIONS.values() if s.path]
    assert len(paths) >= 10
    for path in paths:
        page, _, anchor = path.partition("#")
        assert page in routes, path
        assert not anchor or anchor in anchors, path


# --- F148.5: the chat answers a how-to question from the guide and cites it -----------------------------------------

def test_f148_5_a_how_to_question_calls_patch_guide_and_cites_its_section(client):
    r = client.post("/chat", json={"message": HOW_TO})
    assert r.status_code == 200, r.text
    reply = r.json()
    assert [c["name"] for c in reply["tool_calls"]] == ["patch_guide"]
    assert reply["tool_calls"][0]["args"] == {"topic": "watchlist_and_versions"}
    assert reply["sources"][0]["doc_type"] == "guide" and "[1]" in reply["answer"]
    assert "Settings" in reply["answer"] and not reply["bad_citations"]


@pytest.mark.parametrize("question, topic", [
    ("How do I use Patch?", "start"),
    ("How do I set up alerts?", "alerts"),
    ("Where do I add a product to my watchlist?", "watchlist_and_versions"),
])
def test_f148_5_fakellm_routes_unscripted_how_to_questions_to_the_guide(client, question, topic):
    reply = client.post("/chat", json={"message": question}).json()
    assert [(c["name"], c["args"]) for c in reply["tool_calls"]] == [("patch_guide", {"topic": topic})]
    assert "[1]" in reply["answer"]


def test_f148_5_a_security_how_to_still_searches_the_knowledge_base(client):
    reply = client.post("/chat", json={"message": "How do I stop prompt injection?"}).json()
    assert [c["name"] for c in reply["tool_calls"]] == ["search_security"]


# --- F148.6: the web app's guide, not offered to other assistants ---------------------------------------------------

def test_f148_6_the_mcp_server_does_not_offer_patch_guide(deps):
    from tests.test_mcp_server import call

    r = call(deps, "patch_guide", topic="start")
    assert r.isError or "unknown_tool" in json.dumps([c.model_dump() for c in r.content])


# --- F148.7: the system prompt says when to use it ------------------------------------------------------------------

def test_f148_7_the_system_prompt_names_patch_guide_for_questions_about_patch():
    from app.agent import system_prompt

    assert any("patch_guide" in x and "using Patch itself" in x for x in system_prompt().splitlines())


# --- F148.8: the model-check question --------------------------------------------------------------------------------

def test_f148_8_the_how_to_question_is_in_the_model_check_and_the_examples(client):
    scripts = json.loads((ROOT / "fixtures" / "fake_script.json").read_text())["scripts"]
    q = next(s for s in scripts if s["id"] == "Q-guide")
    assert q["question"] == HOW_TO
    assert q["expect"]["tools"] == ["patch_guide"] and q["expect"]["cites"] is True
    assert "Settings" in q["expect"]["contains_any"]
    assert HOW_TO in [e["question"] for e in client.get("/examples").json()]


# --- F148.9: the guide's facts that the code also holds -------------------------------------------------------------

def test_f148_9_the_watchlist_section_names_the_twelve_tracked_products():
    from app.cve_build import PRODUCTS
    from app.guide import SECTIONS

    text = SECTIONS["watchlist_and_versions"].text
    assert len(PRODUCTS) == 12 and "12" in text
    assert all(name in text for name, _ in PRODUCTS.values()), text


def test_f148_9_the_web_research_section_states_the_default_daily_cap():
    from app.config import Settings
    from app.guide import SECTIONS

    s = Settings()
    assert s.web_research_daily_cap == s.web_research_user_daily_cap == 30
    assert "30 searches a day" in SECTIONS["web_research"].text


def test_f148_9_the_mcp_section_names_the_server_s_tools():
    from app.guide import SECTIONS
    from app.mcp_server import SPECS

    text = SECTIONS["mcp_server"].text
    assert f"{len(SPECS)} read-only tools" in text.replace("four", "4")
    assert all(name in text for name in SPECS)

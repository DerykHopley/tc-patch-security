"""A compensating control on a product the watchlist marks internet-facing carries a warning (B73, #134). Check ids:
B73.n.

Found in the demo rehearsal: "only over the VPN" as the control, on a Langflow the watchlist marks internet-facing,
shown without comment. Nothing is refused and the control's words aren't read: the warning only asks you to check.

Seams: propose_decision through run_tool (as the agent loop runs it, so the model sees the warning), the proposal
API (B21's), a card button's proposal (B24), and the system prompt. The CVE is LangChain's, not in KEV, so B62's
rules for KEV CVEs don't come into it.
"""
import pytest

from app.llm.base import ToolCall
from app.tools.registry import Context, run_tool
from tests.fake_tavily import FakeTavily

CVE = "CVE-2024-8309"  # LangChain: on the default watchlist, not internet-facing by default, not in KEV
REASON = "Only reachable over the VPN [1], so we accept it for now."
CONTROL = "Only reachable over the VPN"
WARNING = "Your watchlist marks LangChain internet-facing. Check this control matches."


@pytest.fixture(scope="module")
def tavily():
    fake = FakeTavily().start()
    yield fake
    fake.stop()


@pytest.fixture
def web_deps(settings, knowledge, index, tavily):
    """propose_decision is offered only with web research on (B22)."""
    from app.deps import build_deps

    settings.tavily_api_key = "tvly-test-0123456789abcdef"
    settings.tavily_mcp_url = f"{tavily.url}/mcp/"
    settings.tavily_api_url = tavily.url
    return build_deps(settings, knowledge=knowledge, index=index)


def client_for(deps):
    from fastapi.testclient import TestClient

    from app.main import create_app

    return TestClient(create_app(deps), raise_server_exceptions=False)


def propose(deps, **args):
    ctx = Context()
    run_tool(ToolCall(id="1", name="lookup_cve", args={"cve_id": CVE}), deps, ctx)
    args = {"cve_id": CVE, "status": "accepted", "reason": REASON, "review_in_days": 30} | args
    rec = run_tool(ToolCall(id="2", name="propose_decision", args=args), deps, ctx)
    assert rec.status == "ok", rec.error
    return rec.result


def internet_facing(deps, on=True):
    deps.state.set_fields("langchain", internet_facing=on)  # as Settings' watchlist saves it


def test_b73_1_a_control_on_an_internet_facing_product_carries_a_warning(web_deps):
    internet_facing(web_deps)
    assert propose(web_deps, compensating_control=CONTROL)["warnings"] == [WARNING]


def test_b73_1_no_warning_without_a_control_or_when_not_internet_facing(web_deps):
    assert propose(web_deps, compensating_control=CONTROL)["warnings"] == []  # the default: not internet-facing
    internet_facing(web_deps)
    assert propose(web_deps)["warnings"] == []  # no control
    assert propose(web_deps, status="fixed", review_in_days=None)["warnings"] == []


def test_b73_2_the_proposal_api_shows_the_warning_from_the_products_fields_now(web_deps):
    client = client_for(web_deps)
    internet_facing(web_deps)
    url = f"/proposals/{propose(web_deps, compensating_control=CONTROL)['proposal_id']}"
    assert client.get(url).json()["warnings"] == [WARNING]
    internet_facing(web_deps, False)  # changed in Settings while the card is open
    assert client.get(url).json()["warnings"] == []
    internet_facing(web_deps)
    accept = {"status": "accepted", "reason": "Only on the VPN", "review_date": "2026-12-01"}
    r = client.patch(url, json=accept)  # your edit (B21) takes the control out
    assert r.status_code == 200 and r.json()["warnings"] == [], r.text
    r = client.patch(url, json=accept | {"compensating_control": "WAF rule 12"})
    assert r.status_code == 200 and r.json()["warnings"] == [WARNING], r.text


def test_b73_2_a_card_buttons_mark_accepted_with_a_control_carries_it_too(web_deps):
    internet_facing(web_deps)
    r = client_for(web_deps).post("/chat/action", json={
        "action": "propose", "change": "set_status", "cve_id": CVE, "status": "accepted",
        "reason": "Behind the VPN", "review_date": "2027-01-11", "compensating_control": "VPN only"})
    assert r.status_code == 200 and r.json()["proposal"]["warnings"] == [WARNING], r.text


def test_b73_3_the_system_prompt_says_to_pass_a_proposals_warnings_on():
    from app import agent

    prompt = " ".join(agent.system_prompt("normal").split())
    assert "If a proposal has warnings, tell the user each one" in prompt

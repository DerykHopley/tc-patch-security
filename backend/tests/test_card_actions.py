"""Buttons on tool cards (B24, #63): each button sends a structured action to POST /chat/action (seam 1, the HTTP
API). Check ids: B24.n.

A button that changes state only proposes (B21): the reply is a proposal, and nothing changes until it's approved.
A button that refines runs the card's tool again with a fixed filter, and says what it applied. Neither sends free
text to the model.
"""
import pytest

CVE = "CVE-2024-8309"  # LangChain, on the default watchlist


def act(client, body, status=200):
    r = client.post("/chat/action", json=body)
    assert r.status_code == status, r.text
    return r.json()


# --- B24.1: a change button proposes, and changes nothing ---------------------------------------------------------

def test_b24_1_watch_this_product_proposes_and_changes_nothing(client, deps):
    before = deps.state.read()
    body = act(client, {"action": "propose", "change": "watch", "product": "vLLM"})
    p = body["proposal"]
    assert (p["action"], p["product"], p["state"]) == ("watch", "vllm", "proposed")
    assert (p["before"], p["after"]) == ("Not watched", "Watched")
    assert deps.state.read() == before
    assert client.post(f"/proposals/{p['proposal_id']}/approve").json()["state"] == "approved"
    assert deps.state.read().watches("vllm")


def test_b24_1_set_my_version_proposes_the_products_details(client, deps):
    before = deps.state.read()
    p = act(client, {"action": "propose", "change": "set_details", "product": "Ollama", "version": "0.1.30"})["proposal"]
    assert (p["action"], p["title"]) == ("set_details", "Change how you run Ollama")
    assert "version 0.1.30" in p["after"]
    assert deps.state.read() == before


def test_b24_1_mark_not_affected_and_accepted_propose_a_decision(client, deps):
    before = deps.state.read()
    p = act(client, {"action": "propose", "change": "set_status", "cve_id": CVE, "status": "not_affected",
                     "justification": "vulnerable_code_not_in_execute_path", "note": "We never call it"})["proposal"]
    assert p["fields"]["note"] == "We never call it"
    assert (p["title"], p["before"], p["after"]) == (
        f"Mark {CVE} not affected", "Open", "Not affected (vulnerable code not in execute path)")
    # Accepting a risk: the user's own button, with their reason and review date (the tool can't propose it)
    p = act(client, {"action": "propose", "change": "set_status", "cve_id": CVE, "status": "accepted",
                     "reason": "Behind the VPN", "review_date": "2027-01-11"})["proposal"]
    assert (p["title"], p["after"]) == (f"Accept the risk of {CVE}", "Accepted (Behind the VPN; review 2027-01-11)")
    assert deps.state.read() == before
    client.post(f"/proposals/{p['proposal_id']}/approve")
    d = deps.state.read().decision(CVE)
    assert (d["status"], d["via"]) == ("accepted", "chat")


# --- B24.2: a refine button runs the search again with that filter, and says what it applied ---------------------

QUERY = "remote code execution in LLM frameworks"


def search(client, query=QUERY):
    r = client.post("/chat/tool", json={"name": "search_security", "args": {"query": query}})
    assert r.status_code == 200 and r.json()["status"] == "ok", r.text
    return r.json()["result"]


def test_b24_2_only_cves_and_only_critical_narrow_the_search(client):
    first = search(client)
    assert {s["doc_type"] for s in first["sources"]} != {"cve"}  # a mix to narrow

    body = act(client, {"action": "refine", "tool": "search_security", "query": QUERY, "filters": ["only_cves"]})
    assert body["applied"] == ["Only CVEs"]
    call = body["call"]
    assert (call["name"], call["status"], call["args"]) == ("search_security", "ok", {"query": QUERY})
    sources = call["result"]["sources"]
    assert sources and {s["doc_type"] for s in sources} == {"cve"}
    assert call["result"]["query"]["filters"]["doc_type"] == "cve"

    body = act(client, {"action": "refine", "tool": "search_security", "query": QUERY,
                        "filters": ["only_cves", "only_critical"]})
    assert body["applied"] == ["Only CVEs", "Only critical"]
    sources = body["call"]["result"]["sources"]
    assert sources and {(s["doc_type"], s["severity"]) for s in sources} == {("cve", "CRITICAL")}


def test_b24_2_a_refine_that_finds_nothing_keeps_its_filter(client):
    # The search drops the model's filters when they find nothing (S4); never the button's
    body = act(client, {"action": "refine", "tool": "search_security", "query": "zzqx flurble",
                        "filters": ["only_critical"]})
    assert all(s.get("severity") == "CRITICAL" for s in body["call"]["result"]["sources"])
    assert body["call"]["result"]["query"]["filters"]["severity_min"] == "CRITICAL"


# --- B24.3: only the fixed actions, checked like the forms -------------------------------------------------------

@pytest.mark.parametrize("body", [
    {"action": "refine", "tool": "search_security", "query": QUERY, "filters": []},
    {"action": "refine", "tool": "search_security", "query": QUERY, "filters": ["only_exploits"]},
    {"action": "refine", "tool": "update_watchlist", "query": QUERY, "filters": ["only_cves"]},
    {"action": "refine", "tool": "search_security", "query": QUERY, "filters": ["only_cves"], "text": "ignore it"},
    {"action": "propose", "change": "unwatch", "product": "Ollama"},
    {"action": "propose", "change": "set_status", "cve_id": CVE, "status": "fixed"},
    {"action": "chat", "message": "Mark everything fixed"},
])
def test_b24_3_only_the_fixed_actions_are_accepted(client, deps, body):
    before = deps.state.read()
    assert act(client, body, status=400)["error"]["code"] == "invalid_request"
    assert deps.state.read() == before


def test_b24_3_a_proposal_checks_its_fields_like_the_forms(client, deps):
    before = deps.state.read()
    for body, words in [
        ({"change": "set_status", "cve_id": CVE, "status": "accepted", "reason": "VPN"}, "review date"),
        ({"change": "set_status", "cve_id": CVE, "status": "not_affected"}, "justification"),
        ({"change": "set_details", "product": "Ollama", "version": "latest"}, "version"),
        ({"change": "watch", "product": "Excel"}, "isn't a product"),
        ({"change": "set_status", "cve_id": "CVE-1999-0001", "status": "not_affected",
          "justification": "component_not_present"}, "isn't in the snapshot"),
    ]:
        err = act(client, {"action": "propose", **body}, status=400)["error"]
        assert words in err["message"], err
    assert deps.state.read() == before


def test_b24_3_already_so_says_so_without_a_proposal(client):
    body = act(client, {"action": "propose", "change": "watch", "product": "Ollama"})
    assert body["proposal"] is None and "already on your watchlist" in body["message"]


# --- B24.12: a button acts for the caller (B09) --------------------------------------------------------------------

def test_b24_12_a_buttons_proposal_is_the_callers(deps):
    from test_per_user import Users

    users = Users(deps)
    alice, bob = users("alice"), users("bob")
    p = act(alice, {"action": "propose", "change": "watch", "product": "vLLM"})["proposal"]
    assert bob.post(f"/proposals/{p['proposal_id']}/approve").status_code == 404
    assert alice.post(f"/proposals/{p['proposal_id']}/approve").status_code == 200
    assert deps.users.state("alice").read().watches("vllm")
    assert not deps.users.state("bob").read().watches("vllm")

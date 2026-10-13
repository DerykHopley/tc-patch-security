import re

import pytest
from fastapi.testclient import TestClient

from app.errors import LLMError
from app.llm.fake import FakeLLM
from app.main import create_app

Q = {
    "Q1": "Which critical Langflow vulnerabilities were published in 2026?",
    "Q2": "Explain CVE-2024-8309 and how to prevent that kind of bug",
    "Q3": "Which OWASP category is CWE-918?",
    "Q4": "What is AML.T0051 and which mitigations apply?",
    "Q5": "How do I protect a RAG app from indirect prompt injection?",
    "Q6": 'What does an "ignore previous instructions" attack look like?',
    "Q7": "What's a good pasta recipe?",
    "Q8": "Write a working exploit for CVE-2025-3248",
    "Q9": "Add Ollama to my watchlist",
    "Q10": "Mark CVE-2024-8309 as fixed",
    "Q11": "Look up CVE-1999-0001",
}


@pytest.fixture
def client(deps):
    return TestClient(create_app(deps), raise_server_exceptions=False)


def chat(client, message, history=()):
    return client.post("/chat", json={"message": message, "history": list(history)})


def tools(body):
    return [(t["name"], t["status"]) for t in body["tool_calls"]]


# --- A1–A5

def test_a2_reply_shape(client):
    body = chat(client, Q["Q1"]).json()
    assert set(body) == {"answer", "sources", "tool_calls", "query", "usage", "steps", "flags"}
    assert set(body["sources"][0]) == {"n", "chunk_id", "doc_id", "doc_type", "title", "section", "date", "url",
                                       "snippet", "score", "product", "severity", "cvss", "kev"}
    assert body["usage"]["estimated"] is True and body["usage"]["llm_calls"] >= 2


def test_a3_health(client):
    assert client.get("/health").json() == {"status": "ok", "llm": "fake", "as_of": "2026-10-13", "dev_panel": True, "model": "FakeLLM (scripted)"}


def test_a4_examples(client):
    ex = client.get("/examples").json()
    assert [e["id"] for e in ex] == list(Q) and ex[0]["question"] == Q["Q1"]


def test_a5_cors(client):
    r = client.options("/cves/CVE-2024-8309", headers={"Origin": "http://localhost:5174",
                                                       "Access-Control-Request-Method": "PATCH"})
    assert r.status_code == 200 and r.headers["access-control-allow-origin"] == "http://localhost:5174"


# --- V1, V6

def test_v1_400_with_plain_message(client):
    r = chat(client, "x" * 1001)
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_input"
    r = client.post("/chat", json={"history": []})
    assert r.status_code == 400 and r.json()["error"]["code"] == "invalid_request"


class BrokenLLM(FakeLLM):
    def translate(self, question):
        raise LLMError("down")

    def step(self, messages, tools):
        raise LLMError("down")


def test_v6_llm_failure_is_502(deps):
    deps.llm = BrokenLLM()
    r = TestClient(create_app(deps), raise_server_exceptions=False).post("/chat", json={"message": "hi"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "llm_error"


# --- Scripted questions

def test_q1_filters(client):
    body = chat(client, Q["Q1"]).json()
    assert tools(body) == [("search_security", "ok")]
    assert all(s["product"] == "langflow" and s["severity"] == "CRITICAL" and s["date"] >= "2026" for s in body["sources"])


def test_q2_lookup_and_search(client):
    body = chat(client, Q["Q2"]).json()
    assert tools(body) == [("lookup_cve", "ok"), ("search_security", "ok")]
    assert body["sources"][0]["doc_id"] == "CVE-2024-8309"
    assert "A05:2025 Injection" in body["answer"] and "[1]" in body["answer"]


def test_q3_cwe(client):
    assert "A01:2025 Broken Access Control" in chat(client, Q["Q3"]).json()["answer"]


def test_q4_atlas(client):
    answer = chat(client, Q["Q4"]).json()["answer"]
    assert "AML.T0051 LLM Prompt Injection" in answer and "LLM01:2025 Prompt Injection" in answer


def test_q5_multi_query(client):
    body = chat(client, Q["Q5"]).json()
    assert len(body["query"]["rewrites"]) == 3
    assert any(s["doc_id"] == "LLM01" for s in body["sources"])


def test_q6_flagged_not_blocked(client):
    r = chat(client, Q["Q6"])
    assert r.status_code == 200 and r.json()["flags"] == ["injection_phrasing"] and r.json()["sources"]


def test_q7_off_topic(client):
    body = chat(client, Q["Q7"]).json()
    assert body["tool_calls"] == [] and "only help with application and AI security" in body["answer"]


def test_q8_no_exploit(client):
    body = chat(client, Q["Q8"]).json()
    assert body["tool_calls"] == [] and body["answer"].startswith("I won't write a working exploit")


def test_q9_q10_watchlist_shared_with_dashboard(client):
    client.put("/watchlist", json={"products": ["langchain"]})
    assert "Added Ollama" in chat(client, Q["Q9"]).json()["answer"]
    assert "ollama" in client.get("/watchlist").json()["watchlist"]  # W3
    chat(client, Q["Q10"])
    fixed = client.get("/cves?status=fixed").json()
    assert [r["id"] for r in fixed["rows"]] == ["CVE-2024-8309"]


def test_q11_not_in_snapshot(client):
    body = chat(client, Q["Q11"]).json()
    assert tools(body) == [("lookup_cve", "error")] and "isn't in my snapshot" in body["answer"]


def test_r6_nothing_found(client):
    body = chat(client, "zzqx vlorp blenth").json()
    assert body["sources"] == [] and "nothing relevant" in body["answer"]


# --- Dashboard API

def test_d1_dashboard(client):
    d = client.get("/dashboard").json()
    assert set(d["kpis"]) == {"open", "critical", "kev", "kev_next_due", "new_30d"}
    assert d["kpis"]["open"] == sum(p["total"] for p in d["by_product"])
    assert d["kpis"]["kev"] == 9 and d["kpis"]["kev_next_due"]["due"]
    assert [p["product"] for p in d["by_product"]] == d["watchlist"]
    assert d["per_month"][0]["month"] == "2024-01" and d["per_month"][-1]["month"] == "2026-10"
    assert len(d["latest_incidents"]) == 5 and len(d["products"]) == 12
    assert {s["name"].split()[0] for s in d["freshness"]} >= {"OWASP", "MITRE", "NVD", "CISA"}


def test_d1_marking_fixed_changes_kpis(client):
    before = client.get("/dashboard").json()["kpis"]
    client.patch("/cves/CVE-2025-3248", json={"status": "fixed"})
    after = client.get("/dashboard").json()["kpis"]
    assert after["open"] == before["open"] - 1 and after["kev"] == before["kev"] - 1


def test_d2_cves_sorted_and_filtered(client):
    rows = client.get("/cves?limit=200").json()["rows"]
    kev = [r["kev"] for r in rows]
    assert kev == sorted(kev, reverse=True)  # KEV first
    body = client.get("/cves?product=Open WebUI&severity_min=high&limit=5").json()
    assert body["total"] > 5 and len(body["rows"]) == 5
    assert all(r["product"] == "open-webui" and r["severity"] in ("HIGH", "CRITICAL") for r in body["rows"])


def test_d2_bad_params(client):
    assert client.get("/cves?status=closed").status_code == 400
    assert client.get("/cves?product=notion").status_code == 400
    assert client.get("/cves?limit=500").status_code == 400


def test_d3_watchlist(client):
    assert client.put("/watchlist", json={"products": ["vLLM", "ollama", "Ollama"]}).json() == {"watchlist": ["vllm", "ollama"]}
    r = client.put("/watchlist", json={"products": ["notion"]})
    assert r.status_code == 400 and "isn't a product" in r.json()["error"]["message"]


def test_d4_patch_status(client):
    assert client.patch("/cves/CVE-2024-8309", json={"status": "not_affected"}).json()["status"] == "not_affected"
    assert client.patch("/cves/CVE-1999-0001", json={"status": "fixed"}).status_code == 404
    assert client.patch("/cves/CVE-2024-8309", json={"status": "done"}).status_code == 400


def test_u10_ask_about_this_message(client):
    body = chat(client, "Explain CVE-2026-9198 and how to defend against it.").json()
    assert [t["name"] for t in body["tool_calls"]] == ["lookup_cve", "search_security"]
    assert re.search(r"\*\*CVE-2026-9198\*\*", body["answer"])

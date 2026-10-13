from app.llm.base import ToolCall
from app.tools.registry import Context, run_tool


def call(deps, name, **args):
    return run_tool(ToolCall(id="t", name=name, args=args), deps, Context())


def test_t2_lookup_cve(deps):
    r = call(deps, "lookup_cve", cve_id="cve-2024-8309")
    assert r.status == "ok"
    res = r.result
    assert (res["id"], res["product"], res["severity"], res["cvss"]) == ("CVE-2024-8309", "LangChain", "CRITICAL", 9.8)
    assert res["owasp"]["code"] == "A05" and res["kev"] is None and res["watch_status"] == "open"


def test_t2_kev_details(deps):
    res = call(deps, "lookup_cve", cve_id="CVE-2025-3248").result
    assert res["kev"]["date_added"] == "2025-05-05" and res["kev"]["due"] == "2025-05-26"


def test_t2_adds_a_numbered_source(deps):
    ctx = Context()
    rec = run_tool(ToolCall(id="t", name="lookup_cve", args={"cve_id": "CVE-2024-8309"}), deps, ctx)
    assert rec.result["n"] == 1 and ctx.sources[0].doc_id == "CVE-2024-8309" and ctx.sources[0].score is None


def test_t2_not_in_snapshot(deps):
    r = call(deps, "lookup_cve", cve_id="CVE-1999-0001")
    assert r.status == "error" and r.error["code"] == "cve_not_in_snapshot"


def test_t3_cwe_to_owasp(deps):
    res = call(deps, "explain_weakness", id="cwe-918").result
    assert res["category"]["code"] == "A01" and res["cves_in_snapshot"] > 0 and len(res["examples"]) == 3


def test_t3_cwe_without_category(deps):
    res = call(deps, "explain_weakness", id="CWE-99999").result
    assert res["category"] is None and res["cves_in_snapshot"] == 0


def test_t3_atlas_rollup(deps):
    res = call(deps, "explain_weakness", id="AML.T0051").result
    assert {s["id"] for s in res["subtechniques"]} >= {"AML.T0051.000", "AML.T0051.001"}
    assert "LLM01" in {c["code"] for c in res["cited_by_llm_top10"]}  # LLM01 cites only the sub-techniques
    assert res["mitigations"]


def test_t3_subtechnique_rolls_up_to_parent(deps):
    res = call(deps, "explain_weakness", id="AML.T0051.001").result
    assert res["parent"] == "AML.T0051" and "LLM01" in {c["code"] for c in res["cited_by_llm_top10"]}


def test_t3_unknown_ids(deps):
    assert call(deps, "explain_weakness", id="AML.T9999").error["code"] == "unknown_id"
    assert call(deps, "explain_weakness", id="XSS").error["code"] == "unknown_id"


def test_t4_watch_unwatch(deps):
    r = call(deps, "update_watchlist", action="watch", product="vLLM").result
    assert "vLLM" in r["watchlist"] and r["message"] == "Added vLLM to your watchlist."
    assert call(deps, "update_watchlist", action="watch", product="vllm").result["message"].endswith("already on your watchlist.")
    r = call(deps, "update_watchlist", action="unwatch", product="vllm").result
    assert "vLLM" not in r["watchlist"]


def test_t4_set_status(deps):
    r = call(deps, "update_watchlist", action="set_status", cve_id="CVE-2024-8309", status="fixed")
    assert r.status == "ok"
    assert call(deps, "lookup_cve", cve_id="CVE-2024-8309").result["watch_status"] == "fixed"


def test_t5_bad_arguments(deps):
    assert call(deps, "lookup_cve", cve_id="not-a-cve").error["code"] == "bad_arguments"
    assert call(deps, "update_watchlist", action="watch").error["code"] == "bad_arguments"
    assert call(deps, "update_watchlist", action="watch", product="Notion").error["code"] == "bad_value"
    assert call(deps, "update_watchlist", action="set_status", cve_id="CVE-1999-0001", status="fixed").error["code"] == "cve_not_in_snapshot"
    assert call(deps, "no_such_tool").error["code"] == "unknown_tool"

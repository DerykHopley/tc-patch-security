"""Retrieval metrics per embedder (seam 4 on fakes): questions whose right sources come from structured fields, hit rate
at 5 and MRR, the misses. Check ids: A12.n, from ticket #14.

The metrics are a pure function, tested on hand-made rankings with worked-out answers. The runs use real Chroma with
the hash embedder (the test fake) and a second fake (a smaller hash embedder) to show two embedders side by side:
the real OpenRouter and Ollama embedders are run by hand (A20).
"""
import pytest

from app.evals.retrieval import metrics, retrieval_questions


def row(qid, expected, ranked):
    return {"id": qid, "kind": "cve", "question": f"question {qid}", "expected": expected, "ranked": ranked}


# --- A12.3: hit rate at 5 and MRR, worked out by hand -----------------------------------------------------------

def test_a12_3_hit_rate_at_5_and_mrr():
    rows = [
        row("r1", ["d1"], ["d1", "x", "y"]),  # rank 1: hit, 1
        row("r2", ["d2"], ["x", "y", "d2"]),  # rank 3: hit, 1/3
        row("r3", ["d3"], ["a", "b", "c", "d", "e", "d3"]),  # rank 6: miss at 5, 1/6
        row("r4", ["d4"], ["a", "b"]),  # not found: miss, 0
    ]
    m = metrics(rows)
    assert m["questions"] == 4 and m["hits"] == 2
    assert m["hit_rate_at_5"] == pytest.approx(0.5)
    assert m["mrr"] == pytest.approx((1 + 1 / 3 + 1 / 6 + 0) / 4)  # 0.375
    assert [x["id"] for x in m["misses"]] == ["r3", "r4"]
    assert m["misses"][0]["got"] == ["a", "b", "c", "d", "e"] and m["misses"][0]["rank"] == 6
    assert m["misses"][1]["rank"] is None


def test_a12_3_any_expected_source_counts_and_only_the_first_one_ranks():
    m = metrics([row("r1", ["d1", "d2"], ["x", "d2", "d1"])])
    assert m["hit_rate_at_5"] == 1 and m["mrr"] == pytest.approx(0.5)


def test_a12_3_no_questions_gives_no_numbers():
    assert metrics([]) == {"questions": 0, "hits": 0, "hit_rate_at_5": None, "mrr": None, "misses": [],
                           "by_kind": {}}


def test_a12_3_metrics_per_kind():
    rows = [row("r1", ["d1"], ["d1"]), {**row("r2", ["d2"], ["x"]), "kind": "cwe"}]
    by_kind = metrics(rows)["by_kind"]
    assert by_kind["cve"] == {"questions": 1, "hit_rate_at_5": 1.0, "mrr": 1.0}
    assert by_kind["cwe"] == {"questions": 1, "hit_rate_at_5": 0.0, "mrr": 0.0}


# --- A12.3: the questions come from structured fields -----------------------------------------------------------

def test_a12_3_questions_take_their_right_sources_from_structured_fields(knowledge):
    qs = retrieval_questions(knowledge)
    assert len({q["id"] for q in qs}) == len(qs) >= 30
    assert {q["kind"] for q in qs} == {"cve", "cwe", "llm_risk", "llm_to_atlas"}
    for q in qs:
        assert q["expected"], q
        if q["kind"] == "cve":  # a CVE id → that CVE
            assert q["expected"] == [q["cve"]] and q["cve"] in q["question"]
            assert knowledge.cves.get(q["cve"])
        if q["kind"] == "cwe":  # a CWE → its OWASP page, from the OWASP CWE map
            assert q["expected"] == [knowledge.owasp["cwe_to_web"][q["cwe"]]] and q["cwe"] in q["question"]
    cve_products = {knowledge.cves.get(q["cve"])["product"] for q in qs if q["kind"] == "cve"}
    assert len(cve_products) == len(knowledge.products)  # one CVE per product
    risk = next(q for q in qs if q["kind"] == "llm_risk" and q["expected"] == ["LLM01"])
    assert "Prompt Injection" in risk["question"] and "LLM01" not in risk["question"]
    atlas = next(q for q in qs if q["kind"] == "llm_to_atlas" and "Prompt Injection" in q["question"])
    assert "AML.T0051.001" in atlas["expected"]  # indirect prompt injection


def test_a12_3_the_question_set_is_the_same_every_time(knowledge):
    assert retrieval_questions(knowledge) == retrieval_questions(knowledge)


# --- A12.3: runs per embedder, through the API --------------------------------------------------------------------

def test_a12_3_a_retrieval_run_on_the_loaded_embedder(client):
    r = client.post("/dev/retrieval-check")
    assert r.status_code == 200, r.text
    run = r.json()
    assert run["embedder"] == "hash-4096" and run["dim"] == 4096 and run["questions"] >= 30
    for mode in ("vector", "hybrid"):
        m = run["modes"][mode]
        assert 0 <= m["hit_rate_at_5"] <= 1 and 0 <= m["mrr"] <= 1
        assert m["questions"] == run["questions"] and len(m["misses"]) == m["questions"] - m["hits"]
    # BM25 keeps ids whole, so hybrid search puts every asked-for CVE in the top 5, whatever the vectors do.
    assert run["modes"]["hybrid"]["by_kind"]["cve"]["hit_rate_at_5"] == 1.0
    listed = client.get("/dev/retrieval-checks").json()["runs"]
    assert listed[0]["id"] == run["id"] and "results" not in listed[0]
    assert listed[0]["modes"]["vector"]["hit_rate_at_5"] == run["modes"]["vector"]["hit_rate_at_5"]
    assert client.get(f"/dev/retrieval-check/{run['id']}").json()["results"] == run["results"]
    assert client.get("/dev/retrieval-check/nope").status_code == 404


def test_a12_3_two_embedders_side_by_side(deps, knowledge, tmp_path):
    from app.evals import retrieval
    from app.rag.chunking import build_chunks
    from app.rag.embed import HashEmbedder
    from app.rag.keyword import BM25Index
    from app.rag.vector import build_index

    small = build_index(build_chunks(knowledge), HashEmbedder(dim=256), tmp_path / "small")  # the second fake
    big = retrieval.run(deps, deps.index, deps.keyword)
    other = retrieval.run(deps, small, BM25Index(small.chunks))
    runs = retrieval.listing(deps)
    assert {r["embedder"] for r in runs} == {"hash-4096", "hash-256"}
    assert {r["id"] for r in runs} == {big["id"], other["id"]}
    # The same questions for both, so the numbers compare. (Chroma's HNSW search is approximate, so the exact scores
    # can move a little between index builds: no test pins them.)
    assert [r["id"] for r in big["results"]] == [r["id"] for r in other["results"]]


# --- A20: the off-topic threshold, seen from both sides ---------------------------------------------------------

def test_a20_a_run_records_top_scores_for_on_and_off_topic_questions_and_the_threshold(deps):
    from app.evals import retrieval

    run = retrieval.run(deps, deps.index, deps.keyword)
    t = run["threshold"]
    assert t["min_score"] == deps.index.min_score
    # Every on-topic question, scored with the threshold ignored: a cosine in [-1, 1]
    assert [x["id"] for x in t["on_topic"]] == [r["id"] for r in run["results"]]
    assert all(-1.0 <= x["score"] <= 1.0 for x in t["on_topic"])
    # The 15 off-topic questions the thresholds were tuned on (2026-10-15), each with a BM25 hit count
    assert len(t["off_topic"]) == 15
    assert t["off_topic"][0]["question"] == "What's a good pasta recipe?"
    assert t["off_topic"][-1]["question"] == "Translate 'good morning' into Spanish"
    for x in t["off_topic"]:
        assert -1.0 <= x["score"] <= 1.0 and isinstance(x["keyword_hits"], int) and x["keyword_hits"] >= 0
    assert retrieval.listing(deps)[0]["threshold"]["min_score"] == t["min_score"]  # the listing keeps it

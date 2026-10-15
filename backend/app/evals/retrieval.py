"""Retrieval metrics per embedder: does search find the right source, and how high?

The questions take their right sources from structured fields in the snapshot, so no one judges by hand:
- cve: "What is CVE-…?" → that CVE (one CVE per product, the lowest id).
- cwe: "Which OWASP Top 10 category covers CWE-…?" → the OWASP web page the OWASP CWE map names (one CWE per
  category, among those the page's text mentions).
- llm_risk: "How do I prevent <risk name>?" → that OWASP LLM Top 10 page (the name without its LLMnn code).
- llm_to_atlas: "Which MITRE ATLAS techniques relate to <risk name>?" → any technique the LLM Top 10 links to it.

Each question runs on two modes: `vector` (the embedder alone: what the comparison is about) and `hybrid` (vector and
BM25 fused by RRF, as the chat searches, without the LLM's rewrites or filters). Rankings are by document: chunks are
mapped to their document and repeats dropped. Hit rate at 5: share of questions with a right document in the top 5.
MRR: the mean of 1 / rank of the first right document, counted to rank 10 (0 below that). The off-topic threshold is
ignored here: this measures the order.

Each run also records what the off-topic threshold (`vector.min_score`) is tuned on (A20): the top-1 vector score of
every question above, threshold ignored; the same for the fixed OFF_TOPIC questions; and the threshold in use. A good
threshold sits between the two groups. For each off-topic question it also counts BM25's matches: keyword search has
no threshold, so this shows what hybrid search lets through.
"""
import re
import time

from app.evals.runs import LISTED, RunStore, new_id, now
from app.rag.chunking import build_chunks
from app.rag.fusion import rrf

KIND = "retrieval"
TOP = 5  # hit rate at 5
DEPTH = 10  # MRR counts ranks up to here
CHUNKS_K = 40  # chunks fetched per retriever: enough for 10 distinct documents
MODES = ("vector", "hybrid")
# The off-topic questions the thresholds in rag/embed.py MIN_SCORES were tuned on (2026-10-15). Fixed: change them
# and old runs no longer compare.
OFF_TOPIC = (
    "What's a good pasta recipe?", "Who won the football world cup in 2022?",
    "What's the weather like in Berlin tomorrow?", "Write me a poem about autumn leaves",
    "How do I bake sourdough bread?", "Recommend a good science fiction novel", "What is the capital of Australia?",
    "How many calories are in a banana?", "Explain how photosynthesis works",
    "What are some tips for learning to play guitar?", "How do I change a flat tyre on a bicycle?",
    "Plan a three-day trip to Rome", "What's the best way to train a puppy?", "How does the stock market work?",
    "Translate 'good morning' into Spanish",
)


def _risk_name(title: str) -> str:
    return title.split(" ", 1)[1] if " " in title else title  # "LLM01:2025 Prompt Injection" → "Prompt Injection"


def retrieval_questions(knowledge) -> list[dict]:
    """The question set, the same every time (sorted, no randomness)."""
    qs: list[dict] = []
    first_cve: dict[str, str] = {}
    for c in sorted(knowledge.cves.all(), key=lambda c: c["id"]):
        first_cve.setdefault(c["product"], c["id"])
    for product, cve in sorted(first_cve.items()):
        qs.append({"id": f"cve-{product}", "kind": "cve", "question": f"What is {cve}?", "expected": [cve],
                   "cve": cve})

    chunks = build_chunks(knowledge)
    mentioned: dict[str, set[str]] = {}
    for c in chunks:
        if c.doc_type == "owasp_web":
            for cwe in re.findall(r"CWE-\d+", c.text):
                mentioned.setdefault(cwe, set()).add(c.doc_id)
    per_category: dict[str, str] = {}
    cwe_map = knowledge.owasp["cwe_to_web"]
    for cwe in sorted(mentioned, key=lambda s: int(s.split("-")[1])):
        if cwe in cwe_map:
            per_category.setdefault(cwe_map[cwe], cwe)
    for category, cwe in sorted(per_category.items()):
        qs.append({"id": f"cwe-{cwe}", "kind": "cwe", "question": f"Which OWASP Top 10 category covers {cwe}?",
                   "expected": [category], "cwe": cwe})

    docs = {c.doc_id for c in chunks}
    categories = knowledge.owasp["categories"]
    for code in sorted(k for k, v in categories.items() if v["kind"] == "owasp_llm"):
        name = _risk_name(categories[code]["title"])
        qs.append({"id": f"risk-{code}", "kind": "llm_risk", "question": f"How do I prevent {name}?",
                   "expected": [code]})
        techniques = [t for t in knowledge.owasp["llm_to_atlas"].get(code, []) if t in docs]
        if techniques:
            qs.append({"id": f"atlas-{code}", "kind": "llm_to_atlas",
                       "question": f"Which MITRE ATLAS techniques relate to {name}?", "expected": techniques})
    return qs


def _first_rank(expected: list[str], ranked: list[str]) -> int | None:
    for i, doc in enumerate(ranked[:DEPTH], start=1):
        if doc in expected:
            return i
    return None


def _round(x: float | None) -> float | None:
    return None if x is None else round(x, 4)


def metrics(rows: list[dict]) -> dict:
    """Hit rate at 5, MRR and the misses over rows of {id, kind, question, expected, ranked (document ids)}. Pure."""
    ranks = [_first_rank(r["expected"], r["ranked"]) for r in rows]
    hits = [rank is not None and rank <= TOP for rank in ranks]
    rr = [1 / rank if rank else 0.0 for rank in ranks]
    by_kind: dict[str, dict] = {}
    for kind in dict.fromkeys(r["kind"] for r in rows):
        idx = [i for i, r in enumerate(rows) if r["kind"] == kind]
        by_kind[kind] = {"questions": len(idx), "hit_rate_at_5": _round(sum(hits[i] for i in idx) / len(idx)),
                         "mrr": _round(sum(rr[i] for i in idx) / len(idx))}
    return {
        "questions": len(rows), "hits": sum(hits),
        "hit_rate_at_5": _round(sum(hits) / len(rows)) if rows else None,
        "mrr": _round(sum(rr) / len(rows)) if rows else None,
        "misses": [{"id": r["id"], "kind": r["kind"], "question": r["question"], "expected": r["expected"],
                    "got": r["ranked"][:TOP], "rank": rank}
                   for r, rank, hit in zip(rows, ranks, hits) if not hit],
        "by_kind": by_kind,
    }


def _documents(chunk_ids: list[str], doc_of: dict[str, str]) -> list[str]:
    return list(dict.fromkeys(doc_of[c] for c in chunk_ids))[:DEPTH]


def rank(question: str, vector, keyword, doc_of: dict[str, str]) -> tuple[dict[str, list[str]], float | None]:
    """Document ids, best first, per mode; and the top-1 vector score, threshold ignored (None: nothing to compare)."""
    hits = vector.search(question, CHUNKS_K, None, min_score=-1.0)
    vec = [h.chunk.chunk_id for h in hits]
    kw = [h.chunk.chunk_id for h in keyword.search(question, CHUNKS_K)]
    fused = [cid for cid, _ in rrf([vec, kw])]
    return {"vector": _documents(vec, doc_of), "hybrid": _documents(fused, doc_of)}, _top(hits)


def _top(hits) -> float | None:
    return round(hits[0].score, 4) if hits else None


def off_topic_scores(vector, keyword) -> list[dict]:
    """Each off-topic question's top-1 vector score (threshold ignored) and how many chunks BM25 matches at all."""
    return [{"question": q, "score": _top(vector.search(q, 1, None, min_score=-1.0)),
             "keyword_hits": len(keyword.search(q, len(keyword.chunks)))} for q in OFF_TOPIC]


def run(deps, vector, keyword) -> dict:
    """Ask every retrieval question of these retrievers (vector: a ChromaIndex), save the run and return it.
    Synchronous: about 60 query embeddings, a few seconds even on a real embedder."""
    started, clock = now(), time.perf_counter()
    doc_of = {c.chunk_id: c.doc_id for c in vector.chunks}
    rows, on_topic = [], []
    for q in retrieval_questions(deps.knowledge):
        ranked, top = rank(q["question"], vector, keyword, doc_of)
        rows.append({k: q[k] for k in ("id", "kind", "question", "expected")} | {"ranked": ranked})
        on_topic.append({"id": q["id"], "score": top})
    modes = {m: metrics([r | {"ranked": r["ranked"][m]} for r in rows]) for m in MODES}
    threshold = {"min_score": vector.min_score, "on_topic": on_topic, "off_topic": off_topic_scores(vector, keyword)}
    result = {"id": new_id(), "kind": "retrieval", "embedder": vector.embedder_name, "dim": vector.dim,
              "chunks": len(vector.chunks), "started": started, "finished": now(),
              "seconds": round(time.perf_counter() - clock, 3), "questions": len(rows), "modes": modes,
              "threshold": threshold, "results": rows}
    RunStore.for_settings(deps.settings).save(KIND, result)
    return result


def get(deps, run_id: str) -> dict | None:
    return RunStore.for_settings(deps.settings).get(KIND, run_id)


def listing(deps) -> list[dict]:
    """Saved runs, newest first, without the per-question rankings."""
    return [{k: v for k, v in r.items() if k != "results"}
            for r in RunStore.for_settings(deps.settings).all(KIND)[:LISTED]]

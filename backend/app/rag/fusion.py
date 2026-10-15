"""Reciprocal rank fusion (Q-T2): score = Σ 1 / (k + rank), rank starting at 1.

`weights` (one per list, default 1) scale a list's terms: hybrid search uses it for the keyword-vs-vector weight.
"""


def rrf(ranked_lists: list[list[str]], k: int = 60, weights: list[float] | None = None) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for i, ranked in enumerate(ranked_lists):
        w = 1.0 if weights is None else weights[i]
        for rank, cid in enumerate(ranked, start=1):
            scores[cid] = scores.get(cid, 0.0) + w / (k + rank)
    # sorted() is stable, so ties keep first-seen order.
    return sorted(scores.items(), key=lambda kv: -kv[1])

"""Reciprocal rank fusion (Q-T2): score = Σ 1 / (k + rank), rank starting at 1."""


def rrf(ranked_lists: list[list[str]], k: int = 60) -> list[tuple[str, float]]:
    scores: dict[str, float] = {}
    for ranked in ranked_lists:
        for rank, cid in enumerate(ranked, start=1):
            scores[cid] = scores.get(cid, 0.0) + 1 / (k + rank)
    # sorted() is stable, so ties keep first-seen order.
    return sorted(scores.items(), key=lambda kv: -kv[1])

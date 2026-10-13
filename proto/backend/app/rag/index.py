"""A tiny in-memory vector index: a numpy matrix plus chunk metadata. No vector database."""
from dataclasses import dataclass

import numpy as np

from app.knowledge import SEVERITY_ORDER
from app.rag.chunking import Chunk
from app.rag.embed import Embedder, tokens

# Hash collisions give unrelated text tiny scores. Below this a hit counts as "no match" (R6).
MIN_SCORE = 0.05


@dataclass(frozen=True)
class Filters:
    doc_type: str | None = None
    product: str | None = None
    severity_min: str | None = None
    owasp: str | None = None
    kev: bool | None = None
    date_from: str | None = None  # ISO dates compare correctly as strings
    date_to: str | None = None

    def matches(self, c: Chunk) -> bool:
        # product, severity_min and kev only make sense for CVEs (S2)
        if (self.product or self.severity_min or self.kev) and c.doc_type != "cve":
            return False
        if (self.date_from or self.date_to) and not c.date:
            return False
        return (
            (self.doc_type is None or c.doc_type == self.doc_type)
            and (self.product is None or c.product == self.product)
            and (self.severity_min is None
                 or SEVERITY_ORDER.get(c.severity or "", 0) >= SEVERITY_ORDER[self.severity_min])
            and (self.owasp is None or c.owasp == self.owasp or c.doc_id == self.owasp)
            and (not self.kev or c.kev)
            and (self.date_from is None or c.date >= self.date_from)
            and (self.date_to is None or c.date[:10] <= self.date_to)
        )

    def is_empty(self) -> bool:
        return self == Filters()


@dataclass(frozen=True)
class Hit:
    chunk: Chunk
    score: float


class VectorIndex:
    def __init__(self, chunks: list[Chunk], embedder: Embedder, word_gate: bool = True):
        self.chunks = chunks
        self.embedder = embedder
        texts = [f"{c.title}\n{c.section or ''}\n{c.text}" for c in chunks]
        self.matrix = embedder.embed(texts)
        # Mock-only: every CVE id is a distinct word, so ~9,000 distinct words share 4,096 hash buckets and a nonsense
        # query always collides with something. The gate keeps R6 literal: a hit must share a real word.
        # With real embeddings, turn it off and use a score threshold instead.
        self.words = [set(tokens(t)) for t in texts] if word_gate else None

    def search(self, query: str, k: int = 10, filters: Filters | None = None) -> list[Hit]:
        # Filter first, then score only what's left (S2).
        rows = [i for i, c in enumerate(self.chunks) if filters is None or filters.matches(c)]
        if self.words is not None:
            q_words = set(tokens(query))
            rows = [i for i in rows if self.words[i] & q_words]
        if not rows:
            return []
        q = self.embedder.embed([query])[0]
        scores = self.matrix[rows] @ q
        order = np.argsort(-scores, kind="stable")[:k]
        return [Hit(self.chunks[rows[i]], float(scores[i])) for i in order if scores[i] >= MIN_SCORE]

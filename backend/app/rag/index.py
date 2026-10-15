"""What every retriever shares: validated filters, hits, and the Retriever seam.

The vector retriever (Chroma, app/rag/vector.py) turns Filters into a Chroma `where`; a keyword retriever
(BM25, A10) applies `Filters.matches` in Python. Both must return only chunks inside the filter.
"""
from dataclasses import dataclass
from typing import Protocol

from app.knowledge import SEVERITY_ORDER
from app.rag.chunking import Chunk


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


class Retriever(Protocol):
    def search(self, query: str, k: int = 10, filters: Filters | None = None) -> list[Hit]:
        """Up to k hits, best first, all inside the filters."""


def day(date: str) -> int:
    """'2026-09-14' or '2026-09-14T10:00:00' → 20260914. Chroma compares numbers only, so dates are stored as ints."""
    return int(date[:10].replace("-", ""))


def where(f: Filters) -> dict | None:
    """Validated filters → a Chroma `where`: single conditions joined by `$and` (Chroma wants 2+ inside an `$and`).

    Same meaning as Filters.matches. A chunk without a date has no `date` key, so a date range excludes it.
    """
    conds: list[dict] = []
    if f.doc_type or f.product or f.severity_min or f.kev:
        conds.append({"doc_type": f.doc_type or "cve"})  # CVE-only filters imply CVEs (S2)
    if f.product:
        conds.append({"product": f.product})
    if f.severity_min:
        conds.append({"severity_rank": {"$gte": SEVERITY_ORDER[f.severity_min]}})
    if f.owasp:
        conds.append({"$or": [{"owasp": f.owasp}, {"doc_id": f.owasp}]})
    if f.kev:
        conds.append({"kev": True})
    if f.date_from:
        conds.append({"date": {"$gte": day(f.date_from)}})
    if f.date_to:
        conds.append({"date": {"$lte": day(f.date_to)}})
    if not conds:
        return None
    return conds[0] if len(conds) == 1 else {"$and": conds}


def metadata(c: Chunk) -> dict:
    """What Chroma stores per chunk for filtering. None values are left out (Chroma doesn't store them)."""
    m: dict = {"doc_id": c.doc_id, "doc_type": c.doc_type}
    if c.date:
        m["date"] = day(c.date)
    if c.doc_type == "cve":
        m["kev"] = c.kev
        m["severity_rank"] = SEVERITY_ORDER.get(c.severity or "", 0)
        for key in ("product", "owasp"):
            if getattr(c, key):
                m[key] = getattr(c, key)
    return m

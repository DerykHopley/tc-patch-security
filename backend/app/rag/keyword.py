"""The keyword retriever: BM25 in-process over the same chunks as Chroma (A10).

Why: a hash or real embedding blurs `CVE-2024-8309` into "some CVE"; BM25 scores the exact token, and a rare
token (an id seen in one chunk) has a high weight. Plain Python, no dependency: 1,680 chunks score in a few ms.
"""
import math
import re
from collections import Counter

from app.rag.chunking import Chunk
from app.rag.index import Filters, Hit

# Runs of letters and digits joined by "-", "." or "_": `cve-2024-8309`, `aml.t0051.001`, `open-webui`, `llama.cpp`.
# A dot or hyphen at the end (end of a sentence) is not part of the token.
_TOKEN = re.compile(r"[a-z0-9]+(?:[.\-_][a-z0-9]+)*")
_PARTS = re.compile(r"[a-z0-9]+")
STOP_WORDS = frozenset(
    "a an and are as at be by can do does for from has have how i in into is it its of on or our so that the "
    "their them then there these this to was were what when which who why will with you your".split())


def tokenize(text: str) -> list[str]:
    """Lowercase tokens, stop words out, plurals folded. A compound with a digit is an id or a version and stays whole only
    (`cve-2024-8309`, never `2024`); other compounds count whole and in parts (`open-webui`, `open`, `webui`)."""
    tokens: list[str] = []
    for tok in _TOKEN.findall(text.lower()):
        if tok in STOP_WORDS:
            continue
        if tok.isalpha():
            tokens.append(_singular(tok))
            continue
        tokens.append(tok)
        if not any(ch.isdigit() for ch in tok):
            tokens += [_singular(p) for p in _PARTS.findall(tok) if p not in STOP_WORDS]
    return tokens


def _singular(word: str) -> str:
    """A light plural fold, the same on both sides: "vulnerabilities" matches "vulnerability". No full stemmer:
    the vector side handles meaning; this only stops a plural from missing its singular."""
    if len(word) > 4 and word.endswith("ies"):
        return word[:-3] + "y"
    if len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def _squash(name: str) -> str:
    return "".join(ch for ch in name.lower() if ch.isalnum())  # "open-webui", "Open WebUI" → "openwebui"


def keyword_text(c: Chunk) -> str:
    """What BM25 reads: the embedded text plus the CVE's product slug and CWE ids, so `CWE-918` finds its CVEs."""
    from app.rag.vector import index_text  # vector imports chromadb; keep this module light

    return " ".join([index_text(c), c.product or "", *c.cwes])


class BM25Index:
    """Okapi BM25 (k1, b as in the usual defaults). Implements the Retriever seam."""

    def __init__(self, chunks: list[Chunk], k1: float = 1.5, b: float = 0.75):
        self.chunks = chunks
        self.k1, self.b = k1, b
        self._tf = [Counter(tokenize(keyword_text(c))) for c in chunks]
        self._len = [sum(tf.values()) for tf in self._tf]
        self._avg = sum(self._len) / len(chunks) if chunks else 0.0
        df = Counter(t for tf in self._tf for t in tf)
        n = len(chunks)
        # The "+1" form: never negative, so a very common word adds a little rather than taking away.
        self._idf = {t: math.log(1 + (n - d + 0.5) / (d + 0.5)) for t, d in df.items()}
        self._products = {_squash(c.product) for c in chunks if c.product}
        self._postings: dict[str, list[int]] = {}
        for i, tf in enumerate(self._tf):
            for t in tf:
                self._postings.setdefault(t, []).append(i)

    def exact_terms(self, query: str) -> list[str]:
        """The ids and product names in the query that the index holds: `cve-2024-8309`, `llm01`, `aml.t0051.001`
        (a token with a letter and a digit), `llamaindex`, "Open WebUI" (a product slug, one word or two). The
        off-topic gate (#53) never closes on these: an id-only question can score low on the vector side."""
        toks = [t for t in _TOKEN.findall(query.lower()) if t not in STOP_WORDS]
        ids = [t for t in toks if t in self._idf and any(ch.isdigit() for ch in t) and any(ch.isalpha() for ch in t)]
        names = toks + [a + b for a, b in zip(toks, toks[1:])]
        return ids + [n for n in names if _squash(n) in self._products]

    def search(self, query: str, k: int = 10, filters: Filters | None = None) -> list[Hit]:
        """Up to k hits, best first; only chunks inside the filters; none that share no word with the query."""
        scores: dict[int, float] = {}
        for t in set(tokenize(query)):
            idf = self._idf.get(t)
            if idf is None:
                continue
            for i in self._postings[t]:
                tf = self._tf[i][t]
                norm = self.k1 * (1 - self.b + self.b * self._len[i] / self._avg)
                scores[i] = scores.get(i, 0.0) + idf * tf * (self.k1 + 1) / (tf + norm)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        hits: list[Hit] = []
        for i, score in ranked:
            if filters is None or filters.matches(self.chunks[i]):
                hits.append(Hit(self.chunks[i], score))
                if len(hits) == k:
                    break
        return hits

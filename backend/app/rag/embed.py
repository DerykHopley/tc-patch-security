"""The Embedder seam, and a fake hash embedder that only matches shared words (R2)."""
import hashlib
import re
from typing import Protocol

import numpy as np

STOP_WORDS = set(
    "a an and are as at be by did do does for from has have how in is it its of on or "
    "say said says that the their them they this to was what when which who why will with "
    "about new s".split()
)


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> np.ndarray:
        """Shape (n, dim), unit-length rows (zero rows for texts with no tokens)."""


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()) if t not in STOP_WORDS]


class HashEmbedder:
    # PLAN.md said dim=512. With ~1,000 distinct words in the fixtures, 512 buckets collide a lot,
    # so unrelated words still score > 0 and R5 ("no shared words → no sources") breaks. 4096 keeps
    # collisions rare; the index also has a minimum score.
    def __init__(self, dim: int = 4096):
        self.dim = dim

    def _bucket(self, token: str) -> int:
        # hashlib, not hash(): Python's hash() is salted per process, so vectors would change between runs.
        return int.from_bytes(hashlib.blake2b(token.encode(), digest_size=8).digest(), "big") % self.dim

    def embed(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for row, text in enumerate(texts):
            for t in tokens(text):
                out[row, self._bucket(t)] += 1.0
            norm = np.linalg.norm(out[row])
            if norm:
                out[row] /= norm
        return out

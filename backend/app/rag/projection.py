"""A 2D map of the index for the dev panel: PCA of the vectors stored in Chroma. Ported from proto (X5).

PCA, not t-SNE or UMAP: it is a linear projection, so a new query is placed by the same formula as the chunks, and
it needs no extra library. The cost: two axes keep only a part of the variation, so nearness on the map is a hint,
not the search's real ranking. The vectors are read from the index, never re-embedded (a real embedder costs money).
"""
from dataclasses import dataclass
from functools import lru_cache

import numpy as np


@dataclass(frozen=True)
class Projection:
    coords: np.ndarray  # (n, 2), in the order of index.chunks
    mean: np.ndarray  # (d,)
    components: np.ndarray  # (d, 2)
    explained: tuple[float, float]  # share of the variation each axis keeps

    def project(self, vectors: np.ndarray) -> np.ndarray:
        return (np.asarray(vectors, dtype=np.float64) - self.mean) @ self.components


def pca_2d(matrix: np.ndarray) -> Projection:
    """Via the n×n Gram matrix: with ~1,700 chunks and up to 4,096 dimensions, that's the smaller problem."""
    x = matrix.astype(np.float64)
    mean = x.mean(axis=0)
    xc = x - mean
    gram = xc @ xc.T
    values, vectors = np.linalg.eigh(gram)
    top = np.argsort(values)[::-1][:2]
    values, vectors = values[top], vectors[:, top]
    sd = np.sqrt(np.maximum(values, 1e-12))
    components = (xc.T @ vectors) / sd
    total = float(np.trace(gram)) or 1.0
    return Projection(coords=vectors * sd, mean=mean, components=components,
                      explained=(float(values[0] / total), float(values[1] / total)))


def stored_vectors(index) -> np.ndarray:
    """Every chunk's vector as Chroma stores it, in the order of index.chunks."""
    got = index.collection.get(include=["embeddings"])
    by_id = dict(zip(got["ids"], got["embeddings"]))
    return np.asarray([by_id[c.chunk_id] for c in index.chunks], dtype=np.float32)


@lru_cache(maxsize=2)
def projection_for(index) -> Projection:
    """Computed once per index, on first use (about a second for the snapshot)."""
    return pca_2d(stored_vectors(index))

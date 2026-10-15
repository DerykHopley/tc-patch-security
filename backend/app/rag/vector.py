"""The vector retriever: Chroma in-process (persistent client, no server).

`build_index` embeds every chunk and writes the collection (run by app/rag/build_index.py); `open_index` loads it
at start-up without embedding anything. The collection records the embedder's name, the vector dimension and a
fingerprint of the chunks, so an index from another model or other data is a plain error, never wrong results.
"""
import hashlib
import pathlib

import chromadb
from chromadb.config import Settings as ChromaSettings

from app.config import ConfigError
from app.rag.chunking import Chunk
from app.rag.embed import Embedder
from app.rag.index import Filters, Hit, metadata, where

COLLECTION = "chunks"
BATCH = 200  # chunks per embedding call and per Chroma add
BUILD_COMMAND = "cd backend && uv run --env-file .env python -m app.rag.build_index"


class IndexMismatch(ConfigError):
    """The index at the path is from another embedder, size or data. `built_with`: the embedder that built it."""

    def __init__(self, message: str, built_with: str | None):
        super().__init__(message)
        self.built_with = built_with


def _client(path: pathlib.Path):
    # Telemetry off: the app makes no network calls of its own (and tests must not).
    return chromadb.PersistentClient(path=str(path), settings=ChromaSettings(anonymized_telemetry=False))


def fingerprint(chunks: list[Chunk]) -> str:
    h = hashlib.sha256()
    for c in chunks:
        h.update(f"{c.chunk_id}\0{c.text}\0".encode())
    return h.hexdigest()[:16]


def index_text(c: Chunk) -> str:
    """What gets embedded: title and section give a short chunk its context."""
    return f"{c.title}\n{c.section or ''}\n{c.text}"


class ChromaIndex:
    def __init__(self, collection, chunks: list[Chunk], embedder: Embedder, min_score: float | None = None):
        self.collection = collection
        self.chunks = chunks
        self.embedder = embedder
        self.embedder_name: str = collection.metadata["embedder"]
        self.dim: int = collection.metadata["dim"]
        self.min_score = embedder.min_score if min_score is None else min_score
        self._by_id = {c.chunk_id: c for c in chunks}

    def search(self, query: str, k: int = 10, filters: Filters | None = None,
               min_score: float | None = None) -> list[Hit]:
        """Up to k hits by cosine similarity, best first; only chunks inside the filters; none below the threshold."""
        q = self.embedder.embed([query])[0]
        if len(q) != self.dim:
            raise ConfigError(f"The embedder returned {len(q)} dimensions; the index has {self.dim}. "
                              f"Rebuild it: {BUILD_COMMAND}")
        if not q.any():  # nothing to compare (e.g. only stop words)
            return []
        res = self.collection.query(query_embeddings=[q.tolist()], n_results=k,
                                    where=where(filters) if filters else None, include=["distances"])
        threshold = self.min_score if min_score is None else min_score
        hits = [Hit(self._by_id[cid], 1.0 - dist) for cid, dist in zip(res["ids"][0], res["distances"][0])]
        return [h for h in hits if h.score >= threshold]


def build_index(chunks: list[Chunk], embedder: Embedder, path: pathlib.Path, progress=None) -> ChromaIndex:
    """Embed every chunk and write a fresh collection at `path` (an old one is replaced)."""
    path = pathlib.Path(path)
    path.mkdir(parents=True, exist_ok=True)
    client = _client(path)
    if COLLECTION in [c.name for c in client.list_collections()]:
        client.delete_collection(COLLECTION)
    collection = None
    for start in range(0, len(chunks), BATCH):
        batch = chunks[start:start + BATCH]
        vectors = embedder.embed([index_text(c) for c in batch])
        if collection is None:  # the dimension is known after the first call
            collection = client.create_collection(
                COLLECTION, embedding_function=None, configuration={"hnsw": {"space": "cosine"}},
                metadata={"embedder": embedder.name, "dim": int(vectors.shape[1]), "chunks": fingerprint(chunks)})
        collection.add(ids=[c.chunk_id for c in batch], embeddings=vectors.tolist(),
                       metadatas=[metadata(c) for c in batch], documents=[c.text for c in batch])
        if progress:
            progress(start + len(batch), len(chunks))
    return ChromaIndex(collection, chunks, embedder)


def open_index(path: pathlib.Path, embedder: Embedder, chunks: list[Chunk],
               min_score: float | None = None) -> ChromaIndex:
    """Load the collection at `path`. Embeds nothing. A missing index is a ConfigError; a mismatched or stale one
    an IndexMismatch (app.deps rebuilds a free hash index on that; a paid one stays an error)."""
    path = pathlib.Path(path)
    collection = None
    if path.exists():
        client = _client(path)
        if COLLECTION in [c.name for c in client.list_collections()]:
            collection = client.get_collection(COLLECTION, embedding_function=None)
    if collection is None:
        raise ConfigError(f"No search index at {path}. Build it first: {BUILD_COMMAND}")
    meta = collection.metadata or {}
    if meta.get("embedder") != embedder.name:
        raise IndexMismatch(f"The search index at {path} was built with {meta.get('embedder')}, but EMBEDDER is "
                            f"{embedder.name}. Queries and chunks must use the same model: rebuild the index "
                            f"({BUILD_COMMAND}) or set EMBEDDER/EMBED_MODEL back.", meta.get("embedder"))
    dim = getattr(embedder, "dim", None)  # known up front for the hash embedder; real ones are checked per query
    if dim is not None and dim != meta.get("dim"):
        raise IndexMismatch(f"The search index at {path} has {meta.get('dim')} dimensions, the embedder {dim}. "
                            f"Rebuild it: {BUILD_COMMAND}", meta.get("embedder"))
    if meta.get("chunks") != fingerprint(chunks):
        raise IndexMismatch(f"The search index at {path} was built from different data than the snapshot. "
                            f"Rebuild it: {BUILD_COMMAND}", meta.get("embedder"))
    return ChromaIndex(collection, chunks, embedder, min_score)

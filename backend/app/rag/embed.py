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
    name: str  # recorded in the index: the same model must embed chunks and queries
    min_score: float  # default cosine threshold below which a hit is "no match" (R6); tunable by SEARCH_MIN_SCORE

    def embed(self, texts: list[str]) -> np.ndarray:
        """Shape (n, dim), unit-length rows (zero rows for texts with no tokens)."""


def tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+(?:-[a-z0-9]+)*", text.lower()) if t not in STOP_WORDS]


class HashEmbedder:
    """The test fake: matches shared words only. Free, offline, deterministic."""

    # 4096 buckets keep collisions rare. The ~9,000 distinct words (every CVE id is one) still collide, so a
    # nonsense query scores a little against some chunk; MIN_SCORE sits above those collisions.
    MIN_SCORE = 0.15

    def __init__(self, dim: int = 4096):
        self.dim = dim
        self.name = f"hash-{dim}"
        self.min_score = self.MIN_SCORE

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


def _unit_rows(m: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    return np.divide(m, norms, out=np.zeros_like(m), where=norms > 0)


class OpenAICompatibleEmbedder:
    """Any OpenAI-compatible /embeddings endpoint, through LangChain's OpenAIEmbeddings: OpenRouter or a local Ollama.

    Token-length checking is off: with it on, LangChain sends tiktoken ids, which only OpenAI itself accepts.
    """

    def __init__(self, provider: str, model: str, base_url: str, api_key: str, min_score: float,
                 http_client=None):
        from langchain_openai import OpenAIEmbeddings  # imported here: the hash-only path doesn't load it

        self.name = f"{provider}/{model}"
        self.min_score = min_score
        self._client = OpenAIEmbeddings(model=model, base_url=base_url, api_key=api_key,
                                        check_embedding_ctx_length=False, http_client=http_client)

    def embed(self, texts: list[str]) -> np.ndarray:
        return _unit_rows(np.asarray(self._client.embed_documents(texts), dtype=np.float32))


# Defaults per embedder: (model, threshold). SEARCH_MIN_SCORE overrides the threshold.
REAL_EMBEDDERS = {
    "openrouter": ("openai/text-embedding-3-small", 0.35),
    "ollama": ("mxbai-embed-large", 0.58),  # A20: tied best hit rate, widest on/off-topic gap
}
# Off-topic thresholds tuned per model (A20, 2026-10-15): about halfway between the highest top-1 cosine of 15
# off-topic questions and the lowest of 47 security ones. Untuned models get their provider's default above.
#   text-embedding-3-small: off-topic at most 0.22, security at least 0.46
#   nomic-embed-text 0.54 / 0.62; qwen3-embedding:0.6b 0.53 / 0.58 (a narrow gap); mxbai-embed-large 0.48 / 0.68
MIN_SCORES = {
    "openrouter/openai/text-embedding-3-small": 0.35,
    "ollama/nomic-embed-text": 0.58,
    "ollama/qwen3-embedding:0.6b": 0.55,
    "ollama/mxbai-embed-large": 0.58,
}
OPENROUTER_URL = "https://openrouter.ai/api/v1"


def make_embedder(settings, http_client=None) -> Embedder:
    """The embedder EMBEDDER names. `http_client` lets tests answer the HTTP calls in memory."""
    if settings.embedder == "hash":
        return HashEmbedder()
    model, min_score = REAL_EMBEDDERS[settings.embedder]
    model = settings.embed_model or model
    tuned = f"{settings.embedder}/{model.removesuffix(':latest')}"  # Ollama's implicit tag names the same model
    min_score = MIN_SCORES.get(tuned, min_score)
    if settings.embedder == "openrouter":
        return OpenAICompatibleEmbedder("openrouter", model, OPENROUTER_URL, settings.openrouter_api_key,
                                        min_score, http_client)
    # Ollama ignores the key, but the OpenAI client needs one.
    return OpenAICompatibleEmbedder("ollama", model, f"{settings.ollama_url}/v1", "ollama", min_score, http_client)

"""Builds the app's parts once. Tests pass their own knowledge, index and settings."""
import datetime as dt
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from app.app_settings import DevSettings, default_dev_settings, default_settings
from app.config import Settings
from app.knowledge import Knowledge, load_knowledge
from app.llm.base import LLM
from app.llm.providers import LLMRouter
from app.notify import Transports
from app.rag.chunking import build_chunks
from app.rag.embed import make_embedder
from app.rag.index import Retriever
from app.rag.keyword import BM25Index
from app.rag.pipeline import SearchOptions
from app.rag.vector import ChromaIndex, IndexMismatch, build_index, open_index
from app.state import State

log = logging.getLogger(__name__)


@dataclass
class Deps:
    settings: Settings
    llm: LLM
    knowledge: Knowledge
    state: State
    index: ChromaIndex  # the vector retriever
    transports: Transports = field(default_factory=Transports)  # how alerts leave the machine; tests pass fakes
    keyword: BM25Index | None = None  # the keyword retriever (A10); built from the index's chunks when not given
    http_client: object = None  # httpx.Client for model servers and model discovery; tests pass an in-memory one
    clock: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC)  # the time; tests pass one they move

    def __post_init__(self):
        if self.keyword is None:
            self.keyword = BM25Index(self.index.chunks)  # the same chunks as Chroma: both search one corpus

    def dev(self) -> DevSettings:
        """The dev panel's saved choices while it's on; the env defaults when it's off (A11)."""
        return self.state.dev_settings() if self.settings.dev_panel else self.state.dev_defaults

    def search_options(self) -> SearchOptions:
        d = self.dev()
        return SearchOptions(top_n=d.top_n, per_query_k=d.per_query_k, per_doc_cap=d.per_doc_cap, rrf_k=d.rrf_k,
                             use_rewrites=d.use_rewrites, use_filters=d.use_filters, keyword_weight=d.keyword_weight)

    @property
    def retrievers(self) -> dict[str, Retriever]:
        """Hybrid search: every query runs on both, fused by RRF."""
        return {"vector": self.index, "keyword": self.keyword}


def load_index(settings: Settings, knowledge: Knowledge) -> ChromaIndex:
    """Open the index at INDEX_PATH. Only the free hash embedder builds one: when it's missing (fresh checkout, CI)
    and when the one there is a stale hash index (a new snapshot, another hash size), with a log line. A real
    embedder costs money, so its index is built on purpose with app/rag/build_index.py, and a mismatch with an
    index a real embedder built stays an error: it's never overwritten here."""
    chunks = build_chunks(knowledge)
    embedder = make_embedder(settings)
    free = settings.embedder == "hash"
    if free and not settings.index_path.exists():
        build_index(chunks, embedder, settings.index_path)
    try:
        return open_index(settings.index_path, embedder, chunks, settings.search_min_score)
    except IndexMismatch as e:
        if not (free and str(e.built_with or "").startswith("hash-")):
            raise IndexMismatch(f"{e} Embedding with a real model costs money, so it isn't rebuilt "
                                "automatically.", e.built_with) from None
        log.warning("Rebuilding the free hash search index at %s: %s", settings.index_path, e)
        build_index(chunks, embedder, settings.index_path)
        return open_index(settings.index_path, embedder, chunks, settings.search_min_score)


def build_deps(settings: Settings, llm: LLM | None = None, knowledge: Knowledge | None = None,
               index: ChromaIndex | None = None, http_client=None) -> Deps:
    """Without `llm`, a router answers: it reads the dev panel's model choice on every call (A11)."""
    settings.check()
    knowledge = knowledge or load_knowledge()
    state = State(settings.state_path, knowledge, default_settings(settings), default_dev_settings(settings))
    deps = Deps(
        settings=settings,
        llm=llm,  # type: ignore[arg-type]  # set just below when not given: the router needs deps.dev
        knowledge=knowledge,
        state=state,
        index=index or load_index(settings, knowledge),
        http_client=http_client,
    )
    if llm is None:
        deps.llm = LLMRouter(settings, deps.dev, http_client)
    return deps

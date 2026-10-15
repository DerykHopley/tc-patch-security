"""Builds the app's parts once. Tests pass their own knowledge, index and settings.

Live mode (B02): `sync()` swaps in a new live version (knowledge, Chroma, BM25 and State's reference together)
before a request, and `as_of` is today by `clock`.
"""
import datetime as dt
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from app.alerts import Alerter
from app.app_settings import DevSettings, default_dev_settings, default_settings
from app.config import Settings
from app.feeds import Feeds
from app.knowledge import Knowledge, load_knowledge
from app.live_data import LiveData
from app.llm.base import LLM
from app.llm.providers import LLMRouter
from app.notify import Transports
from app.rag.chunking import build_chunks
from app.rag.embed import make_embedder
from app.rag.index import Retriever
from app.rag.keyword import BM25Index
from app.rag.pipeline import SearchOptions
from app.rag.vector import ChromaIndex, IndexMismatch, build_index, open_index, sync_index
from app.refresh import Refresher, make_refresher, utc_now
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
    clock: Callable[[], dt.datetime] = utc_now  # the time; tests pass one they move (live mode's today, B02)
    refresher: Refresher | None = None  # live mode only (B02): fetch, build, write a new live version
    version: int | None = None  # the live version loaded; None in snapshot mode
    _sync_lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        if self.keyword is None:
            self.keyword = BM25Index(self.index.chunks)  # the same chunks as Chroma: both search one corpus

    @property
    def live(self) -> bool:
        return self.settings.data_mode == "live"

    @property
    def as_of(self) -> str:
        """The as-of date: the snapshot's (or AS_OF) in snapshot mode, today (UTC) in live mode."""
        return self.clock().astimezone(dt.UTC).date().isoformat() if self.live else self.settings.as_of

    def sync(self) -> None:
        """Live mode: when a refresh (this process or the CLI) wrote a new version, load it before the request.
        The new CVE data, the index with the changed chunks upserted, and a new BM25 are swapped in together."""
        if self.refresher is None:
            return
        with self._sync_lock:
            version = self.refresher.live.version()
            if version == self.version:
                return
            knowledge = load_knowledge(self.refresher.live.folder(version))
            index, embedded = sync_index(self.index, build_chunks(knowledge))
            self.knowledge, self.index, self.keyword = knowledge, index, BM25Index(index.chunks)
            self.state.k = knowledge  # State resolves products and checks versions with it
            self.version = version
            log.info("Loaded live version %d: %d chunks embedded", version, embedded)

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
    """`load_snapshot_index`, and in live mode (B02) an index of the snapshot or of an older live version is brought
    up to the live data by embedding only the chunks that differ (a real embedder's baked index stays usable)."""
    if settings.data_mode != "live":
        return load_snapshot_index(settings, knowledge)
    chunks = build_chunks(knowledge)
    if not settings.index_path.exists():
        return load_snapshot_index(settings, knowledge)
    try:
        return open_index(settings.index_path, make_embedder(settings), chunks, settings.search_min_score)
    except IndexMismatch:
        pass
    try:  # built from the snapshot (or rebuilt below): embed only what the live data changed
        index = open_index(settings.index_path, make_embedder(settings), build_chunks(load_knowledge()),
                           settings.search_min_score)
    except IndexMismatch:
        return load_snapshot_index(settings, knowledge)
    return sync_index(index, chunks)[0]


def load_snapshot_index(settings: Settings, knowledge: Knowledge) -> ChromaIndex:
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
               index: ChromaIndex | None = None, http_client=None, feeds: Feeds | None = None,
               clock: Callable[[], dt.datetime] = utc_now) -> Deps:
    """Without `llm`, a router answers: it reads the dev panel's model choice on every call (A11).
    Live mode loads the current live version (a copy of the snapshot at first); `knowledge` is ignored there."""
    settings.check()
    refresher = version = None
    if settings.data_mode == "live":
        refresher = make_refresher(settings, feeds, clock)
        version = refresher.live.version()
        knowledge = load_knowledge(refresher.live.folder(version))
    knowledge = knowledge or load_knowledge()
    state = State(settings.state_path, knowledge, default_settings(settings), default_dev_settings(settings))
    deps = Deps(
        settings=settings,
        llm=llm,  # type: ignore[arg-type]  # set just below when not given: the router needs deps.dev
        knowledge=knowledge,
        state=state,
        index=index or load_index(settings, knowledge),
        http_client=http_client,
        clock=clock,
        refresher=refresher,
        version=version,
    )
    if llm is None:
        deps.llm = LLMRouter(settings, deps.dev, http_client)
    if refresher is not None:  # step 4 of the refresh (B04): read deps.transports at send time, so tests' fakes apply
        refresher.alerter = Alerter(settings, state, lambda: deps.transports)
    return deps

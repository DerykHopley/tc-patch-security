"""Builds the app's parts once. Tests pass their own knowledge, index and settings.

Live mode (B02): `sync()` swaps in a new live version (knowledge, Chroma, BM25 and State's reference together)
before a request, and `as_of` is today by `clock`.

B26: `settings` are the effective ones: the environment's (`env`) with the owner's saved server settings where the
environment set nothing (app.server_settings). `sync()` applies a change before the request, so switching between
live and snapshot data on Settings needs no restart.
"""
import copy
import datetime as dt
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from app.alerts import Alerter
from app.app_settings import DevSettings, default_dev_settings, default_settings
from app.clerk_people import People, clerk_people
from app.config import DEFAULT_USER, Settings
from app.status import DECIDED_BY
from app.feeds import Feeds, make_feeds
from app.knowledge import Knowledge, load_knowledge
from app.live_data import LiveData, MixedFeeds
from app.llm.base import LLM
from app.llm.providers import LLMRouter
from app.notify import Transports
from app.rag.chunking import build_chunks
from app.rag.embed import make_embedder
from app.rag.index import Retriever
from app.rag.keyword import BM25Index
from app.rag.pipeline import SearchOptions
from app.rag.vector import ChromaIndex, IndexMismatch, build_index, open_index, sync_index
from app.refresh import Refresher, live_data, make_refresher, utc_now
from app.search_memory import SearchMemory
from app.server_settings import effective
from app.state import State
from app.store import MemoryStore, open_bucket
from app.users import Users
from app.web_research import WebResearch

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
    web: WebResearch | None = None  # web research (B08); None without a Tavily key: research_web is off
    clock: Callable[[], dt.datetime] = utc_now  # the time; tests pass one they move (live mode's today, B02)
    refresher: Refresher | None = None  # live mode only (B02): fetch, build, write a new live version
    version: int | None = None  # the live version loaded; None in snapshot mode
    fail_tools: set[str] = field(default_factory=set)  # B20: chat tools that time out in an answer (FAIL_TOOLS, dev)
    users: Users | None = None  # B09: every user's state; `state` is the one this Deps acts for
    user_id: str = DEFAULT_USER  # whose request this is (B09): `state` is theirs
    role: str = "owner"  # B45: the caller's role (for_user); the shared Deps acts for the owner (checks, refresh)
    env: Settings | None = None  # B26: the settings from the environment; `settings` adds the owner's saved ones
    people: People | None = None  # B38: names and emails from Clerk for the Requests card; None without a secret key
    searches: SearchMemory = field(default_factory=SearchMemory)  # #51: each user's last search; shared by for_user
    _feeds: Feeds | None = None  # the feeds a test passed; None: the settings' (made again when the NVD key changes)
    _live_refused: str | None = None  # B28: why live mode couldn't be switched on (logged once)
    _bucket: object = None  # STORE=gcs: the bucket, for a refresher made when live mode is switched on (B26)
    _snapshot: Knowledge | None = None  # the snapshot's knowledge, for switching back from live mode (B26)
    _sync_lock: threading.Lock = field(default_factory=threading.Lock)
    _root: "Deps | None" = field(default=None, repr=False)  # a user's Deps (for_user) points at the shared one

    def __post_init__(self):
        self.env = self.env or self.settings
        if self.keyword is None:
            self.keyword = BM25Index(self.index.chunks)  # the same chunks as Chroma: both search one corpus
        self.fail_tools = self.fail_tools or set(self.settings.fail_tools)
        if self.users is None:  # one user only: the given state (other users' states in memory)
            self.users = Users(MemoryStore(), self.knowledge, self.state.defaults, self.state.dev_defaults,
                               self.settings.owner, default=self.state)
        if self.fail_tools:
            log.warning("FAIL_TOOLS is on: %s time out in every answer (docs/failure-demo.md).",
                        ", ".join(sorted(self.fail_tools)))

    def for_user(self, user_id: str) -> "Deps":
        """The same parts, acting for one user: their state (with their profile, B48) and their id for the tools'
        context. Everything else (the knowledge, the index, the refresh, the model) is shared."""
        mine = copy.copy(self)
        mine.state, mine.user_id, mine._root = self.users.state(user_id), user_id, self._root or self
        # B45: the caller's role, read once per request (a change applies on their next one). A reviewer's chat asks
        # the model their own copy names: the router reads this Deps's `dev`, not the shared one's
        mine.role = self.users.access.role(user_id)
        if mine.role == "reviewer" and isinstance(self.llm, LLMRouter):
            mine.llm = self.llm.reading(mine.dev)
        return mine

    @property
    def decided_by(self) -> str:
        """Who a new decision record names (B48, #77): the display name in the user's profile at this moment, else
        "you". Never the session token's claims. A record keeps what it said when it was made."""
        return self.state.profile_name() or DECIDED_BY

    @property
    def owner_state(self) -> State:
        """The owner's state (OWNER; locally the default user): where the dev panel's server-wide choices live."""
        return self.users.state(self.settings.owner)

    @property
    def live(self) -> bool:
        return self.settings.data_mode == "live"

    @property
    def as_of(self) -> str:
        """The as-of date: the snapshot's (or AS_OF) in snapshot mode, today (UTC) in live mode."""
        return self.clock().astimezone(dt.UTC).date().isoformat() if self.live else self.settings.as_of

    def sync(self) -> None:
        """Before each request. B26: the owner's saved server settings, applied (live or snapshot, the alerts' time
        zone, link and channels). Live mode: when a refresh (this process or the CLI) wrote a new version, load it.
        The new CVE data, the index with the changed chunks upserted, and a new BM25 are swapped in together."""
        if self._root is not None:  # a user's Deps: the shared one loads it, then this copy takes the new parts
            self._root.sync()
            r = self._root
            self.settings, self.refresher = r.settings, r.refresher
            self.knowledge, self.index, self.keyword, self.version = r.knowledge, r.index, r.keyword, r.version
            return
        with self._sync_lock:
            self._apply(effective(self.env, self.owner_state.server_settings()))
            if self.refresher is None:
                return
            version = self.refresher.live.version()
            if version == self.version:
                return
            self._load(load_knowledge(self.refresher.live.folder(version)), version)
            log.info("Loaded live version %d", version)

    def _load(self, knowledge: Knowledge, version: int | None) -> None:
        index, embedded = sync_index(self.index, build_chunks(knowledge))
        self.knowledge, self.index, self.keyword = knowledge, index, BM25Index(index.chunks)
        self.users.set_knowledge(knowledge)  # every user's State resolves products and checks versions with it
        self.state.k = knowledge
        self.version = version
        log.info("Search index brought up to the data: %d chunks embedded", embedded)

    def _apply(self, settings: Settings) -> None:
        """B26: new effective settings. Live mode on: a refresher over LIVE_PATH (the first start copies the snapshot
        in), loaded by `sync`. Off: the snapshot again; the live data stays on disk for the next switch."""
        if settings == self.settings:
            return
        if settings.data_mode == "live" and self.refresher is None:
            try:
                refresher = make_refresher(settings, self._feeds, self.clock, bucket=self._bucket)
            except MixedFeeds as e:  # B28: switched on elsewhere (another instance); Settings refuses it here first
                if str(e) != self._live_refused:  # once, not on every request
                    log.error("Live data not switched on: %s", e)
                self._live_refused = str(e)
                return
        before, self.settings = self.settings, settings
        self.users.set_defaults(default_settings(settings))
        if settings.data_mode == "live" and self.refresher is None:
            self.refresher = refresher
            self.refresher.alerter = Alerter(settings, self.users, lambda: self.transports)
            self.version = None  # `sync` loads the current live version next
            log.info("Live data switched on (Settings)")
        elif settings.data_mode != "live" and self.refresher is not None:
            self.refresher = None
            self._snapshot = self._snapshot or load_knowledge()
            self._load(self._snapshot, None)
            log.info("Back to the snapshot (Settings); the live data stays in %s", settings.live_path)
        if self.refresher is not None:
            if self.refresher.alerter is not None:
                self.refresher.alerter.settings = settings
            if self._feeds is None and settings.nvd_api_key != before.nvd_api_key:
                self.refresher.feeds = make_feeds(settings)

    def check_live_folder(self, settings: Settings) -> None:
        """B28: raise MixedFeeds when `settings` would switch live mode on over live data the other kind of feeds
        wrote. Nothing is fetched or written."""
        if settings.data_mode == "live" and self.refresher is None:
            live_data(settings, self._bucket).check_feeds(self._feeds.kind if self._feeds else settings.feeds)

    def dev(self) -> DevSettings:
        """The dev panel's saved choices while it's on; the env defaults when it's off (A11). B45: the caller's
        effective choices: a reviewer's own copy when they saved one, else the owner's (everyone else's)."""
        if not self.settings.dev_panel:
            return self.state.dev_defaults
        if self.role == "reviewer" and (mine := self.state.dev_copy()) is not None:
            return mine
        return self.owner_state.dev_settings()

    def search_options(self) -> SearchOptions:
        d = self.dev()
        return SearchOptions(top_n=d.top_n, per_query_k=d.per_query_k, per_doc_cap=d.per_doc_cap, rrf_k=d.rrf_k,
                             use_rewrites=d.use_rewrites, use_filters=d.use_filters, keyword_weight=d.keyword_weight)

    @property
    def retrievers(self) -> dict[str, Retriever]:
        """Hybrid search: every query runs on both, fused by RRF."""
        return {"vector": self.index, "keyword": self.keyword}


def load_index(settings: Settings, knowledge: Knowledge, live: LiveData | None = None) -> ChromaIndex:
    """`load_snapshot_index`, and in live mode (B02) an index of an older live version or of the snapshot is brought
    up to the live data by embedding only the chunks that differ (a real embedder's index stays usable).

    B53 (#88): which data the index was built from is found by its fingerprint: the current version first, then the
    older kept live versions newest first (a refresh ran while the backend was off), then the snapshot (a cold start
    on Cloud Run, B13: the image's index is the snapshot's, the live data comes from the bucket)."""
    if settings.data_mode != "live" or not settings.index_path.exists():
        return load_snapshot_index(settings, knowledge)
    embedder, chunks = make_embedder(settings), build_chunks(knowledge)
    try:
        return open_index(settings.index_path, embedder, chunks, settings.search_min_score)
    except IndexMismatch:
        pass
    for source, older in _older_data(live):
        try:
            index = open_index(settings.index_path, embedder, build_chunks(older()), settings.search_min_score)
        except IndexMismatch:
            continue
        began = time.monotonic()
        index, embedded = sync_index(index, chunks)
        log.info("Search index caught up with the live data from %s: %d chunks embedded in %.1f s", source,
                 embedded, time.monotonic() - began)
        return index
    return load_snapshot_index(settings, knowledge)  # none matched: a stale hash index is rebuilt, a paid one raises


def _older_data(live: LiveData | None) -> list[tuple[str, Callable[[], Knowledge]]]:
    """The data an index may have been built from, newest first, each loaded only when tried: the kept live versions
    before the current one, then the snapshot."""
    older: list[tuple[str, Callable[[], Knowledge]]] = []
    if live is not None:
        current = live.version()
        older += [(f"live version {v}", lambda v=v: load_knowledge(live.folder(v)))
                  for v in reversed(live.versions()) if v != current]
    return older + [("the snapshot", load_knowledge)]


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
               clock: Callable[[], dt.datetime] = utc_now, bucket=None) -> Deps:
    """Without `llm`, a router answers: it reads the dev panel's model choice on every call (A11).
    Live mode loads the current live version (a copy of the snapshot at first); `knowledge` is ignored there.
    STORE=gcs (B13): users' state and the live data are in the Cloud Storage bucket; tests pass a fake `bucket`."""
    settings.check()
    env = settings
    bucket = open_bucket(env, bucket)
    users = Users.for_settings(env, knowledge, default_settings(env), default_dev_settings(env), bucket)
    if env.auth:  # B31: before the owner's saved server settings are read, so live mode comes along
        users.adopt_default()
        # B38: sign-up requests. Everyone Patch knew before them was invited, so is approved (once)
        users.access.enabled = True
        users.access.adopt_existing(users.all_ids())
    settings = effective(env, users.state(env.owner).server_settings())  # B26: the owner's saved server settings
    snapshot = knowledge
    refresher = version = None
    if settings.data_mode == "live":
        refresher = make_refresher(settings, feeds, clock, bucket=bucket)
        version = refresher.live.version()
        knowledge = load_knowledge(refresher.live.folder(version))
    knowledge = knowledge or load_knowledge()
    users.set_knowledge(knowledge)
    users.set_defaults(default_settings(settings))
    state = users.state(DEFAULT_USER)
    deps = Deps(
        settings=settings,
        env=env,
        _feeds=feeds,
        _bucket=bucket,
        _snapshot=snapshot if settings.data_mode == "live" else knowledge,
        llm=llm,  # type: ignore[arg-type]  # set just below when not given: the router needs deps.dev
        knowledge=knowledge,
        state=state,
        index=index or load_index(settings, knowledge, refresher.live if refresher else None),
        http_client=http_client,
        web=WebResearch(settings) if settings.tavily_api_key else None,
        clock=clock,
        refresher=refresher,
        version=version,
        users=users,
        people=clerk_people(env.clerk_secret_key) if env.auth else None,
    )
    if llm is None:
        deps.llm = LLMRouter(settings, deps.dev, http_client)
    if refresher is not None:  # step 4 of the refresh (B04): read deps.transports at send time, so tests' fakes apply
        refresher.alerter = Alerter(settings, users, lambda: deps.transports)
    return deps

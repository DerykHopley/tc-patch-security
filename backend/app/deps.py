"""Builds the app's parts once. Tests pass their own knowledge, index and settings."""
from dataclasses import dataclass, field

from app.app_settings import default_settings
from app.config import Settings
from app.knowledge import Knowledge, load_knowledge
from app.llm.base import LLM
from app.llm.providers import make_llm
from app.notify import Transports
from app.rag.chunking import build_chunks
from app.rag.embed import make_embedder
from app.rag.vector import ChromaIndex, build_index, open_index
from app.state import State


@dataclass
class Deps:
    settings: Settings
    llm: LLM
    knowledge: Knowledge
    state: State
    index: ChromaIndex  # the vector retriever; BM25 joins it in A10
    transports: Transports = field(default_factory=Transports)  # how alerts leave the machine; tests pass fakes


def load_index(settings: Settings, knowledge: Knowledge) -> ChromaIndex:
    """Open the index at INDEX_PATH. Only the free hash embedder builds one when it's missing (fresh checkout, CI);
    a real embedder costs money, so its index is built on purpose with app/rag/build_index.py."""
    chunks = build_chunks(knowledge)
    embedder = make_embedder(settings)
    if settings.embedder == "hash" and not settings.index_path.exists():
        build_index(chunks, embedder, settings.index_path)
    return open_index(settings.index_path, embedder, chunks, settings.search_min_score)


def build_deps(settings: Settings, llm: LLM | None = None, knowledge: Knowledge | None = None,
               index: ChromaIndex | None = None) -> Deps:
    settings.check()
    knowledge = knowledge or load_knowledge()
    return Deps(
        settings=settings,
        llm=llm or make_llm(settings),
        knowledge=knowledge,
        state=State(settings.state_path, knowledge, default_settings(settings)),
        index=index or load_index(settings, knowledge),
    )

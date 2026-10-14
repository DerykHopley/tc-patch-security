"""Builds the app's parts once. Tests pass their own knowledge, index and settings."""
from dataclasses import dataclass, field

from app.app_settings import default_settings
from app.config import Settings
from app.knowledge import Knowledge, load_knowledge
from app.llm.base import LLM
from app.llm.providers import make_llm
from app.notify import Transports
from app.rag.chunking import build_chunks
from app.rag.embed import HashEmbedder
from app.rag.index import VectorIndex
from app.state import State


@dataclass
class Deps:
    settings: Settings
    llm: LLM
    knowledge: Knowledge
    state: State
    index: VectorIndex  # the prototype's in-memory index with the hash embedder until Chroma (A09)
    transports: Transports = field(default_factory=Transports)  # how alerts leave the machine; tests pass fakes


def build_deps(settings: Settings, llm: LLM | None = None, knowledge: Knowledge | None = None,
               index: VectorIndex | None = None) -> Deps:
    settings.check()
    knowledge = knowledge or load_knowledge()
    return Deps(
        settings=settings,
        llm=llm or make_llm(settings),
        knowledge=knowledge,
        state=State(settings.state_path, knowledge, default_settings(settings)),
        index=index or VectorIndex(build_chunks(knowledge), HashEmbedder()),
    )

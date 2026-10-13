"""Everything a request needs, built once at start-up. Tests build their own and swap parts."""
from dataclasses import dataclass

from app.config import Settings
from app.knowledge import Knowledge, load_knowledge
from app.llm.base import LLM
from app.rag.chunking import build_chunks
from app.rag.embed import HashEmbedder
from app.rag.index import VectorIndex
from app.schemas import AppSettings, DevSettings
from app.state import State


@dataclass
class Deps:
    settings: Settings
    llm: LLM
    knowledge: Knowledge
    index: VectorIndex
    state: State


def make_llm(settings: Settings, dev) -> LLM:
    """A router: the provider and model come from the dev panel's settings on every call (M1)."""
    settings.check()
    from app.llm.router import LLMRouter

    return LLMRouter(settings, dev)


def build_deps(settings: Settings, llm: LLM | None = None, knowledge: Knowledge | None = None,
               index: VectorIndex | None = None) -> Deps:
    knowledge = knowledge or load_knowledge()
    # Env values are the defaults; the dev panel's saved settings override them (G2).
    defaults = AppSettings(dev=DevSettings(provider=settings.llm_provider, model=settings.openrouter_model,
                                           max_steps=settings.max_steps))
    state = State(settings.state_path, knowledge, defaults)
    return Deps(
        settings=settings,
        llm=llm or make_llm(settings, dev=lambda: state.settings().dev),
        knowledge=knowledge,
        index=index or VectorIndex(build_chunks(knowledge), HashEmbedder()),
        state=state,
    )

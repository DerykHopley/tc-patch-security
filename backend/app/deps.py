"""Builds the app's parts once. Tests pass their own knowledge and settings."""
from dataclasses import dataclass

from app.config import Settings
from app.knowledge import Knowledge, load_knowledge
from app.llm.base import LLM
from app.llm.fake import FakeLLM
from app.state import State


@dataclass
class Deps:
    settings: Settings
    llm: LLM
    knowledge: Knowledge
    state: State


def build_deps(settings: Settings, llm: LLM | None = None, knowledge: Knowledge | None = None) -> Deps:
    settings.check()
    knowledge = knowledge or load_knowledge()
    return Deps(
        settings=settings,
        llm=llm or FakeLLM(),
        knowledge=knowledge,
        state=State(settings.state_path, knowledge),
    )

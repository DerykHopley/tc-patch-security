"""The model seam. Only the part the walking skeleton needs: which model is in use.

The chat methods (translate, step) come back with the chat on FakeLLM (A06) and the real
model behind LangChain (A08, docs/adr/0001-thin-langchain.md).
"""
from typing import Protocol


class LLM(Protocol):
    name: str  # provider id: "fake", later "openrouter", "local"

    def label(self) -> str:
        """The model in use, as shown to the user."""
        ...

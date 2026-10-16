"""One search for all three explain levels (#51): each user's last question and the search it rests on.

The same question at another explain level answers from that search, so every level has the same tools, sources,
numbers and citations, and only the wording changes (A19). The rule, in `find`: the same user, the same question
(case and spaces aside), the same checked page context, the same data version and tool-failure switch, and a level
other than the last answer's. Anything else searches again, and a new question replaces the one remembered. A
search that proposed a change (B21, B22) isn't kept: its card belongs to one answer. In memory only: a restart forgets.
"""
import json
import threading
from collections.abc import Collection
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.agent import Search


@dataclass(frozen=True)
class Asked:
    """What makes two asks the same question."""
    question: str
    page: str
    version: int | None
    fail_tools: frozenset[str]

    @classmethod
    def of(cls, question: str, page: dict, version: int | None, fail_tools: Collection[str]) -> "Asked":
        return cls(" ".join(question.split()).casefold(), json.dumps(page, sort_keys=True), version,
                   frozenset(fail_tools))


class SearchMemory:
    def __init__(self):
        self._last: dict[str, tuple[Asked, str, "Search"]] = {}  # user → (the question, its last level, its search)
        self._lock = threading.Lock()

    def find(self, user: str, asked: Asked, level: str) -> "Search | None":
        with self._lock:
            last = self._last.get(user)
        return last[2] if last and last[0] == asked and last[1] != level else None

    def keep(self, user: str, asked: Asked, level: str, search: "Search") -> None:
        proposed = any(r.result and "proposal_id" in r.result for r in search.records)
        with self._lock:
            if proposed:
                self._last.pop(user, None)
            else:
                self._last[user] = (asked, level, search)

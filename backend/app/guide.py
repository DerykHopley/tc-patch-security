"""The Patch guide (#148): how to use the app, one short section per topic, read from guide.md beside this file.

The patch_guide tool returns a section as a citable source. A Markdown file, not Python strings, so the owner can
read and edit the text as text; backend/tests/test_patch_guide.py checks its topics, paths and facts.
"""
import re
from dataclasses import dataclass
from pathlib import Path

GUIDE = Path(__file__).with_name("guide.md")
SECTION = re.compile(r"(\w+)\nTitle: ([^\n]+)\nWhere: (\S+)\n\n(.+)", re.S)  # one section, after its "## "


@dataclass(frozen=True)
class Section:
    title: str
    path: str | None  # where it is in the app (a path, maybe with a card's anchor); None when it isn't a page
    text: str


def load(text: str) -> dict[str, Section]:
    sections = {}
    for part in re.split(r"^## ", text, flags=re.M)[1:]:  # [0]: the comment before the first section
        m = SECTION.fullmatch(part.strip())
        if m is None:
            raise ValueError(f"guide.md: not '## topic', 'Title:', 'Where:', a blank line, the text: {part[:60]!r}")
        topic, title, where, body = m.groups()
        sections[topic] = Section(title, None if where == "-" else where, " ".join(body.split()))
    return sections


SECTIONS: dict[str, Section] = load(GUIDE.read_text())

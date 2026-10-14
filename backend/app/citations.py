"""The citation check after each answer (A08): real models cite numbers that don't exist.

A citation is `[n]` or a list `[n, m]`, not followed by `(` (that would be a Markdown link). A number with no
matching source is removed from the answer and reported; the user is never sent to a source that doesn't exist.
"""
import re
from dataclasses import dataclass

CITATION = re.compile(r"([ \t]*)\[(\d+(?:\s*,\s*\d+)*)\](?!\()")  # the space before is removed with it


@dataclass
class Checked:
    answer: str
    bad: list[int]  # each removed number once, in the order they first appeared
    cited: bool  # at least one valid citation is left


def check_citations(answer: str, valid: set[int]) -> Checked:
    bad: list[int] = []
    cited = False

    def fix(m: re.Match) -> str:
        nonlocal cited
        ns = [int(n) for n in re.split(r"\s*,\s*", m.group(2))]
        good = [n for n in ns if n in valid]
        for n in ns:
            if n not in valid and n not in bad:
                bad.append(n)
        if not good:
            return ""
        cited = True
        return m.group(1) + " ".join(f"[{n}]" for n in good)

    return Checked(CITATION.sub(fix, answer), bad, cited)

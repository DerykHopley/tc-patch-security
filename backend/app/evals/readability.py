"""Flesch reading ease (A19): how hard an answer is to read. Higher is easier; 60-70 is plain English.

    206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)

Our own code, not a library: the formula is one line, and the only judgement is counting syllables. The usual
libraries (textstat) count them with a dictionary plus a heuristic like this one and bring extra dependencies; for
comparing three answers to the same question by the same model, a heuristic that is the same every run is enough.
Syllables are vowel groups, minus a silent final "e" (but "-le" after a consonant keeps its syllable), at least 1.
"""
import re

_NOISE = [
    re.compile(r"\[(\d+)\](\([^)]*\))?"),  # citations [1] and Markdown links' targets
    re.compile(r"https?://\S+"),
    re.compile(r"`[^`]*`"),  # inline code
]
_WORD = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")
_VOWELS = re.compile(r"[aeiouy]+")


def syllables(word: str) -> int:
    w = word.lower()
    n = len(_VOWELS.findall(w))
    if w.endswith("e") and n > 1 and not re.search(r"[^aeiouy]le$", w):
        n -= 1
    return max(1, n)


def flesch_reading_ease(text: str) -> float | None:
    """None when there are no words to score."""
    for pattern in _NOISE:
        text = pattern.sub(" ", text)
    words = _WORD.findall(text)
    if not words:
        return None
    sentences = max(1, len(_SENTENCE_END.findall(text)))
    syl = sum(syllables(w) for w in words)
    return 206.835 - 1.015 * len(words) / sentences - 84.6 * syl / len(words)

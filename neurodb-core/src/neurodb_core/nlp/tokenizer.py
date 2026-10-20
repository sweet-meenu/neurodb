from __future__ import annotations

import re

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")

STOPWORDS = frozenset(
    """
    a an the and or but if while is are was were be been being
    to of in on at by for with about against between into through
    during before after above below from up down out off over under
    again further then once here there when where why how all any
    both each few more most other some such no nor not only own same
    so than too very s t can will just don should now this that these
    those i me my we our you your he him his she her it its they them
    their what which who whom as
    """.split()
)

# Suffixes checked longest-first so e.g. "-izing" strips before "-ing".
_SUFFIXES = ("izational", "izations", "ational", "ization", "edly", "ing", "ed", "ly", "es", "s")


def stem(word: str) -> str:
    """Lightweight suffix-stripping stemmer (Porter-lite). Not linguistically
    complete, but merges common inflections enough to improve term overlap
    for a from-scratch, non-ML encoder.
    """
    lower = word.lower()
    if len(lower) <= 4:
        return lower
    for suffix in _SUFFIXES:
        if lower.endswith(suffix) and len(lower) - len(suffix) >= 3:
            return lower[: -len(suffix)]
    return lower


def tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def normalize_tokens(
    text: str, *, remove_stopwords: bool = True, apply_stem: bool = True
) -> list[str]:
    tokens = [t.lower() for t in tokenize(text)]
    if remove_stopwords:
        tokens = [t for t in tokens if t not in STOPWORDS]
    if apply_stem:
        tokens = [stem(t) for t in tokens]
    return tokens

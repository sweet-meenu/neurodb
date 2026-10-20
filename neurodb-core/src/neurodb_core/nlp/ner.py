from __future__ import annotations

import re
from dataclasses import dataclass

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)*\.[a-zA-Z]{2,}")
_URL_RE = re.compile(r"https?://[^\s)]+")
_DATE_RE = re.compile(
    r"\b(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sept?|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}|"
    r"\d{4}-\d{2}-\d{2})\b"
)
_NUMBER_RE = re.compile(r"\b\d+(?:\.\d+)?%?\b")

_ORG_SUFFIXES = {
    "inc", "inc.", "corp", "corp.", "llc", "ltd", "ltd.", "co", "co.",
    "university", "institute", "foundation", "association", "company", "corporation",
}

# Small bundled gazetteer of common multi-word entities so the capitalized-
# sequence heuristic below doesn't mislabel e.g. "New York" as a PERSON.
_GAZETTEER: dict[str, str] = {
    "india": "GPE", "united states": "GPE", "usa": "GPE", "china": "GPE",
    "japan": "GPE", "germany": "GPE", "france": "GPE", "canada": "GPE",
    "brazil": "GPE", "russia": "GPE", "australia": "GPE", "mexico": "GPE",
    "italy": "GPE", "spain": "GPE", "netherlands": "GPE", "switzerland": "GPE",
    "singapore": "GPE", "united kingdom": "GPE", "uk": "GPE", "south korea": "GPE",
    "sweden": "GPE", "new york": "GPE", "los angeles": "GPE", "san francisco": "GPE",
    "london": "GPE", "mumbai": "GPE", "delhi": "GPE", "bangalore": "GPE",
    "united nations": "ORG", "world health organization": "ORG", "european union": "ORG",
}

_HONORIFICS = {"mr", "mrs", "ms", "dr", "prof", "sir", "madam"}

_CAPITALIZED_SEQ_RE = re.compile(r"\b[A-Z][a-zA-Z.]*(?:\s+[A-Z][a-zA-Z.]*)*\b")


@dataclass
class Entity:
    text: str
    label: str
    start: int
    end: int


def extract_entities(text: str) -> list[Entity]:
    """Rule-based + gazetteer NER: regex for EMAIL/URL/DATE/NUMBER, a small
    bundled gazetteer for common GPE/ORG multi-word names, and a
    capitalized-sequence heuristic (with honorific/suffix cues) for
    PERSON/ORG otherwise. No statistical model, no pretrained weights.
    """
    entities: list[Entity] = []
    seen_spans: set[tuple[int, int]] = set()

    for regex, label in ((_EMAIL_RE, "EMAIL"), (_URL_RE, "URL"), (_DATE_RE, "DATE")):
        for m in regex.finditer(text):
            entities.append(Entity(m.group(), label, m.start(), m.end()))
            seen_spans.add((m.start(), m.end()))

    for m in _CAPITALIZED_SEQ_RE.finditer(text):
        start, end = m.start(), m.end()
        if (start, end) in seen_spans:
            continue
        phrase = m.group()
        lowered = phrase.lower().strip(".")
        words = phrase.split()

        if lowered in _GAZETTEER:
            entities.append(Entity(phrase, _GAZETTEER[lowered], start, end))
            seen_spans.add((start, end))
            continue

        if any(w.lower().strip(".") in _ORG_SUFFIXES for w in words):
            entities.append(Entity(phrase, "ORG", start, end))
            seen_spans.add((start, end))
            continue

        first_word = words[0].lower().strip(".")
        if first_word in _HONORIFICS or len(words) >= 2:
            entities.append(Entity(phrase, "PERSON", start, end))
            seen_spans.add((start, end))

    for m in _NUMBER_RE.finditer(text):
        if (m.start(), m.end()) not in seen_spans:
            entities.append(Entity(m.group(), "NUMBER", m.start(), m.end()))

    return entities

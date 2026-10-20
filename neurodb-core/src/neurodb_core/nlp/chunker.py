from __future__ import annotations

import re
from dataclasses import dataclass

from neurodb_core.nlp.tokenizer import tokenize

_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "vs", "etc",
    "e.g", "i.e", "u.s", "u.k", "inc", "ltd", "co", "st", "no",
}
_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")


@dataclass
class Chunk:
    text: str
    start_sentence: int
    end_sentence: int


def split_sentences(text: str) -> list[str]:
    """Regex-based sentence splitter that backs off on common abbreviations
    (Mr., Dr., etc.) so it doesn't split mid-title.
    """
    text = text.strip()
    if not text:
        return []
    raw_pieces = _SENTENCE_BOUNDARY_RE.split(text)
    sentences: list[str] = []
    buffer = ""
    for piece in raw_pieces:
        buffer = f"{buffer} {piece}".strip() if buffer else piece
        words = buffer.strip().split()
        last_word = words[-1].rstrip(".!?").lower() if words else ""
        if last_word in _ABBREVIATIONS:
            continue  # false boundary right after an abbreviation; keep accumulating
        sentences.append(buffer)
        buffer = ""
    if buffer:
        sentences.append(buffer)
    return [s for s in sentences if s.strip()]


def chunk_text(text: str, *, target_tokens: int = 110, overlap_sentences: int = 1) -> list[Chunk]:
    """Groups sentences into token-budgeted, overlapping chunks — a topic-
    boundary heuristic that keeps sentences intact rather than cutting at a
    fixed character window.
    """
    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[Chunk] = []
    start_idx = 0
    idx = 0
    current: list[str] = []
    current_tokens = 0

    while idx < len(sentences):
        sentence = sentences[idx]
        sentence_len = len(tokenize(sentence))
        if current and current_tokens + sentence_len > target_tokens:
            chunks.append(
                Chunk(text=" ".join(current), start_sentence=start_idx, end_sentence=idx - 1)
            )
            overlap_start = max(idx - overlap_sentences, start_idx + 1)
            start_idx = overlap_start
            current = sentences[overlap_start:idx]
            current_tokens = sum(len(tokenize(s)) for s in current)
            continue
        current.append(sentence)
        current_tokens += sentence_len
        idx += 1

    if current:
        chunks.append(
            Chunk(text=" ".join(current), start_sentence=start_idx, end_sentence=len(sentences) - 1)
        )
    return chunks

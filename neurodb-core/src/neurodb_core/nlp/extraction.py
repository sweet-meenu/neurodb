from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from pypdf import PdfReader

_SCRIPT_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINES_RE = re.compile(r"\n\s*\n+")

# Text-like formats: extracted to a string and run through the existing
# sentence/chunk pipeline. Image/audio are a different shape entirely (one
# object per file, a hand-written feature-vector encoder instead of the text
# encoder) — see nlp/pipeline.py's process_bytes for the dispatch.
TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".html", ".htm", ".pdf", ".csv"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
AUDIO_EXTENSIONS = {".wav"}  # decoded via stdlib `wave` — zero extra dependency, always available
# Compressed audio: decoding needs a real codec, not something hand-written
# code can do — ingestion only works if NEURODB_TRANSCRIBE_BACKEND=whisper is
# configured (see nlp/transcription.py). Kept as a separate set from
# AUDIO_EXTENSIONS so callers can tell "always works" apart from "opt-in."
COMPRESSED_AUDIO_EXTENSIONS = {".mp3"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | COMPRESSED_AUDIO_EXTENSIONS


def extract_html(html: str) -> str:
    """Hand-written HTML-to-text: strips script/style blocks then tags,
    collapses whitespace. No external HTML parsing library."""
    text = _SCRIPT_STYLE_RE.sub(" ", html)
    text = _TAG_RE.sub(" ", text)
    text = _WHITESPACE_RE.sub(" ", text)
    text = _BLANK_LINES_RE.sub("\n\n", text)
    return text.strip()


def extract_pdf_bytes(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages).strip()


def extract_csv_bytes(data: bytes) -> str:
    """Hand-written CSV-to-text: renders each row as a 'column: value.'
    sentence so it's chunked and embedded through the existing text
    pipeline unchanged — no separate tabular embedding path needed. Python's
    stdlib `csv` module handles only the RFC 4180 parsing (quoting/escaping,
    general-purpose plumbing, same as the pypdf/Pillow exception), not the
    text framing, which is hand-written here.
    """
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return ""
    header, *data_rows = rows
    paragraphs = []
    for row in data_rows:
        pairs = [f"{h.strip()}: {v.strip()}" for h, v in zip(header, row) if v.strip()]
        if pairs:
            paragraphs.append(". ".join(pairs) + ".")
    return "\n\n".join(paragraphs)


def extract_from_bytes(data: bytes, *, filename: str) -> str:
    """Text-like formats only — see TEXT_EXTENSIONS. Image/audio bytes are
    never routed here; nlp/pipeline.py dispatches them to their own
    feature-vector encoders instead."""
    suffix = Path(filename).suffix.lower()
    if suffix not in TEXT_EXTENSIONS:
        raise ValueError(f"unsupported text extension: {suffix}")
    if suffix in {".txt", ".md", ".markdown"}:
        return data.decode("utf-8", errors="replace")
    if suffix in {".html", ".htm"}:
        return extract_html(data.decode("utf-8", errors="replace"))
    if suffix == ".csv":
        return extract_csv_bytes(data)
    return extract_pdf_bytes(data)  # .pdf


def extract_text(path: Path | str) -> str:
    path = Path(path)
    return extract_from_bytes(path.read_bytes(), filename=path.name)

from __future__ import annotations

import mimetypes
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from neurodb_core.nlp.captioning import CaptionFn
from neurodb_core.nlp.chunker import chunk_text
from neurodb_core.nlp.classifier import NaiveBayesClassifier
from neurodb_core.nlp.embedding import EncodedVector, encode
from neurodb_core.nlp.extraction import (
    AUDIO_EXTENSIONS,
    COMPRESSED_AUDIO_EXTENSIONS,
    IMAGE_EXTENSIONS,
    extract_from_bytes,
)
from neurodb_core.nlp.keyphrase import extract_keyphrases
from neurodb_core.nlp.ner import Entity, extract_entities
from neurodb_core.nlp.transcription import TranscribeFn


@dataclass
class ProcessedChunk:
    text: str
    chunk_index: int
    entities: list[Entity]
    keyphrases: list[tuple[str, float]]
    embedding: EncodedVector
    classification: tuple[str | None, dict[str, float]] | None = None
    source_metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProcessedMedia:
    """One image/audio file -> one object with a hand-written feature-vector
    embedding, plus (only if a caption_fn is configured) a real text
    description/transcript chunked and embedded the normal way — see
    nlp/captioning.py."""

    modality: str  # "image" | "audio"
    embedding: EncodedVector
    content_type: str
    caption: str | None = None
    caption_chunks: list[ProcessedChunk] = field(default_factory=list)
    source_metadata: dict[str, Any] = field(default_factory=dict)


class DocumentPipeline:
    """Orchestrates the full NLP ingestion pipeline. Text-like formats
    (.txt/.md/.html/.pdf/.csv) go through extraction -> semantic chunking ->
    NER/keyphrases/classification -> embedding, producing ProcessedChunk
    records. Image/audio go through a hand-written feature-vector encoder
    instead, producing a single ProcessedMedia — optionally enriched with a
    real caption/transcript if caption_fn is supplied (opt-in, see
    nlp/captioning.py; None by default, meaning zero external calls).
    """

    def __init__(
        self,
        *,
        target_tokens: int = 110,
        classifier: NaiveBayesClassifier | None = None,
        caption_fn: CaptionFn | None = None,
        transcribe_fn: TranscribeFn | None = None,
    ):
        self.target_tokens = target_tokens
        self.classifier = classifier
        self.caption_fn = caption_fn
        self.transcribe_fn = transcribe_fn

    def process_text(
        self, text: str, *, source_metadata: dict[str, Any] | None = None
    ) -> list[ProcessedChunk]:
        chunks = chunk_text(text, target_tokens=self.target_tokens)
        processed: list[ProcessedChunk] = []
        for i, chunk in enumerate(chunks):
            classification = self.classifier.predict(chunk.text) if self.classifier else None
            processed.append(
                ProcessedChunk(
                    text=chunk.text,
                    chunk_index=i,
                    entities=extract_entities(chunk.text),
                    keyphrases=extract_keyphrases(chunk.text),
                    embedding=encode(chunk.text),
                    classification=classification,
                    source_metadata=source_metadata or {},
                )
            )
        return processed

    def _process_media_bytes(
        self, data: bytes, *, filename: str, modality: str, source_metadata: dict[str, Any] | None = None
    ) -> ProcessedMedia:
        content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        meta = {"filename": filename, **(source_metadata or {})}
        suffix = Path(filename).suffix.lower()

        caption: str | None = None
        caption_chunks: list[ProcessedChunk] = []

        if modality == "image":
            from neurodb_core.nlp.image_features import encode_image

            embedding = encode_image(data)
            if self.caption_fn:
                caption = self.caption_fn(data, content_type) or None
        elif suffix in COMPRESSED_AUDIO_EXTENSIONS:
            # Can't even decode this without the Whisper backend switched on
            # — there's no hand-written fallback for a compressed audio codec.
            if not self.transcribe_fn:
                raise ValueError(
                    f"{suffix} audio requires NEURODB_TRANSCRIBE_BACKEND=whisper — .wav works with no extra setup"
                )
            from neurodb_core.nlp.audio_features import encode_audio_samples

            samples, framerate, transcript = self.transcribe_fn(data)
            embedding = encode_audio_samples(samples, framerate)
            caption = transcript or None
        else:
            from neurodb_core.nlp.audio_features import encode_audio

            embedding = encode_audio(data)
            if self.caption_fn:
                caption = self.caption_fn(data, content_type) or None

        if caption:
            caption_chunks = self.process_text(caption, source_metadata=meta)

        return ProcessedMedia(
            modality=modality,
            embedding=embedding,
            content_type=content_type,
            caption=caption,
            caption_chunks=caption_chunks,
            source_metadata=meta,
        )

    def process_file(
        self, path: Path | str, *, source_metadata: dict[str, Any] | None = None
    ) -> list[ProcessedChunk] | ProcessedMedia:
        path = Path(path)
        return self.process_bytes(path.read_bytes(), filename=path.name, source_metadata=source_metadata)

    def process_bytes(
        self,
        data: bytes,
        *,
        filename: str,
        source_metadata: dict[str, Any] | None = None,
    ) -> list[ProcessedChunk] | ProcessedMedia:
        suffix = Path(filename).suffix.lower()
        if suffix in IMAGE_EXTENSIONS:
            return self._process_media_bytes(data, filename=filename, modality="image", source_metadata=source_metadata)
        if suffix in AUDIO_EXTENSIONS or suffix in COMPRESSED_AUDIO_EXTENSIONS:
            return self._process_media_bytes(data, filename=filename, modality="audio", source_metadata=source_metadata)
        text = extract_from_bytes(data, filename=filename)  # raises ValueError for an unsupported extension
        meta = {"filename": filename, **(source_metadata or {})}
        return self.process_text(text, source_metadata=meta)

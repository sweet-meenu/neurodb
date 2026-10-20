"""Optional, pluggable image-description / audio-transcription enrichment.

neurodb-core's own embeddings are 100% hand-written (nlp/image_features.py,
nlp/audio_features.py) and NEVER require this module or any external API —
that default is unconditional. Hand-written color-histogram / signal-
statistics embeddings only capture visual/acoustic *similarity* though, not
*what the image shows or what the audio says*: there is no honest
from-scratch way to get real image captioning or speech-to-text without
either pretrained weights or a research-scale training effort, neither of
which fit this project's scope (see docs/roadmap.md).

So this is opt-in, off unless explicitly configured: if NEURODB_CAPTION_API_KEY
is set, ingested images and audio ALSO get a real text description/
transcript from an external model, stored as their own "text" modality +
embedding on the same object — searchable through the exact same
SEMANTIC SIMILAR TO machinery as everything else. If unset (the default),
ingestion behaves exactly as it does without this module: hand-written
feature vectors only, zero external calls. `google-genai` is a core
dependency (always installed), but its client is only constructed on first
actual use of this feature, so it stays a zero-cost, zero-import no-op
until NEURODB_CAPTION_API_KEY is set.
"""

from __future__ import annotations

import os
from typing import Callable

CaptionFn = Callable[[bytes, str], str]  # (data, mime_type) -> description/transcript text

_IMAGE_PROMPT = (
    "Describe this image in detail for a search index: the main subject, setting, visible "
    "text, and colors. Plain text only, no markdown, no preamble."
)
_AUDIO_PROMPT = (
    "Transcribe this audio clip verbatim. If it isn't speech, describe what is audible "
    "instead. Plain text only, no markdown, no preamble."
)


def _gemini_caption_fn(*, api_key: str, model: str) -> CaptionFn:
    # google-genai is only imported on first actual use (not here at
    # startup) so a genuinely broken install fails one ingest request with a
    # clear, actionable error instead of crashing the whole process at boot
    # — same defensive shape as nlp/transcription.py's build_transcribe_fn.
    client = None

    def caption(data: bytes, mime_type: str) -> str:
        nonlocal client
        if client is None:
            try:
                from google import genai
            except ImportError as exc:
                raise RuntimeError(
                    "NEURODB_CAPTION_API_KEY is set but google-genai isn't installed "
                    "(it's a core dependency — run: uv sync)"
                ) from exc
            client = genai.Client(api_key=api_key)

        from google.genai import types

        prompt = _IMAGE_PROMPT if mime_type.startswith("image/") else _AUDIO_PROMPT
        response = client.models.generate_content(
            model=model,
            contents=[types.Part.from_bytes(data=data, mime_type=mime_type), prompt],
        )
        return (response.text or "").strip()

    return caption


def build_caption_fn() -> CaptionFn | None:
    """Reads NEURODB_CAPTION_API_KEY / NEURODB_CAPTION_MODEL from the
    environment. Returns None — pure hand-written mode, no behavior change
    — if the key isn't set."""
    api_key = os.environ.get("NEURODB_CAPTION_API_KEY")
    if not api_key:
        return None
    model = os.environ.get("NEURODB_CAPTION_MODEL", "gemini-flash-lite-latest")
    return _gemini_caption_fn(api_key=api_key, model=model)

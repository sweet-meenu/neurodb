"""Optional, pluggable local speech-to-text — the only way MP3 (or any
compressed audio) gets ingested at all: there is no honest hand-written way
to decode a compressed audio codec, let alone transcribe speech, without
either pretrained weights or a research-scale training effort (same
reasoning as nlp/captioning.py's image description, see docs/roadmap.md).

Backed by faster-whisper (CTranslate2, not PyTorch) rather than the
original openai-whisper package: much lighter, and its PyAV-based audio
decoding bundles its own codecs, so a separate system `ffmpeg` install
usually isn't needed. faster-whisper/av are always installed (core
dependencies), but this path itself stays off unless
NEURODB_TRANSCRIBE_BACKEND=whisper is set — the model is only loaded once
that switch is flipped.

.wav ingestion never touches this module — nlp/audio_features.py decodes it
via the stdlib `wave` module with zero extra dependency, exactly as before.
"""

from __future__ import annotations

import functools
import io
import os
from typing import Callable

import numpy as np

TranscribeFn = Callable[[bytes], tuple[np.ndarray, int, str]]  # data -> (samples, framerate, transcript)

_DEFAULT_MODEL_SIZE = "tiny"  # smallest/fastest Whisper variant


@functools.lru_cache(maxsize=1)
def _load_model(model_size: str):
    from faster_whisper import WhisperModel

    return WhisperModel(model_size, device="cpu", compute_type="int8")


def _decode_and_transcribe(data: bytes, *, model_size: str) -> tuple[np.ndarray, int, str]:
    import av

    # Decoded once here (native sample rate) purely to feed our own
    # hand-written feature vector (nlp/audio_features.py) — faster-whisper
    # does its own separate internal decode + resample to 16kHz below.
    container = av.open(io.BytesIO(data))
    stream = container.streams.audio[0]
    framerate = stream.rate
    chunks = [frame.to_ndarray() for frame in container.decode(stream)]
    container.close()

    if chunks:
        samples = np.concatenate(chunks, axis=-1).astype(np.float32)
        if samples.ndim > 1:
            samples = samples.mean(axis=0)  # downmix to mono
        peak = float(np.abs(samples).max())
        if peak > 1.0:  # integer-encoded samples, not already float in [-1, 1]
            samples = samples / peak
    else:
        samples = np.zeros(0, dtype=np.float32)

    model = _load_model(model_size)
    segments, _info = model.transcribe(io.BytesIO(data), beam_size=1)
    transcript = " ".join(segment.text.strip() for segment in segments).strip()

    return samples, framerate, transcript


def build_transcribe_fn() -> TranscribeFn | None:
    """Reads NEURODB_TRANSCRIBE_BACKEND / NEURODB_WHISPER_MODEL from the
    environment. Returns None — MP3 ingestion stays disabled, .wav
    unaffected — unless the backend is explicitly set to "whisper"."""
    if os.environ.get("NEURODB_TRANSCRIBE_BACKEND", "").strip().lower() != "whisper":
        return None
    model_size = os.environ.get("NEURODB_WHISPER_MODEL", _DEFAULT_MODEL_SIZE)

    def transcribe(data: bytes) -> tuple[np.ndarray, int, str]:
        try:
            return _decode_and_transcribe(data, model_size=model_size)
        except ImportError as exc:
            raise RuntimeError(
                "NEURODB_TRANSCRIBE_BACKEND=whisper is set but faster-whisper/av aren't installed "
                "(they're core dependencies — run: uv sync)"
            ) from exc

    return transcribe

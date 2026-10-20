from __future__ import annotations

import io
import math
import wave

import numpy as np

from neurodb_core.nlp.embedding import EncodedVector

MODEL_NAME = "neurodb-lite-audio-encoder"
MODEL_VERSION = 1

_N_FRAMES = 20  # the clip is split into N equal time frames
_HIST_BINS = 8  # coarse overall spectral-energy histogram (timbre signature)
_RAW_DIM = _N_FRAMES * 3 + _HIST_BINS  # per-frame (RMS, zero-crossing rate, spectral centroid) + histogram
_OUTPUT_DIM = 256
_PROJECTION_SEED = 7331

_SAMPLE_DTYPES = {1: np.uint8, 2: np.int16, 4: np.int32}


def _projection_matrix(seed: int, in_dim: int, out_dim: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(loc=0.0, scale=1.0 / math.sqrt(out_dim), size=(in_dim, out_dim))


_PROJECTION = _projection_matrix(_PROJECTION_SEED, _RAW_DIM, _OUTPUT_DIM)


def _read_wav_samples(data: bytes) -> tuple[np.ndarray, int]:
    with wave.open(io.BytesIO(data), "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        framerate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    dtype = _SAMPLE_DTYPES.get(sampwidth)
    if dtype is None:
        raise ValueError(f"unsupported WAV sample width: {sampwidth} bytes")
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float64)
    if sampwidth == 1:
        samples -= 128  # 8-bit WAV is unsigned, offset-encoded around 128
    samples /= float(2 ** (sampwidth * 8 - 1))

    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)  # downmix to mono
    return samples, framerate


def _raw_audio_features(samples: np.ndarray, framerate: int) -> np.ndarray:
    """Hand-written, pre-deep-learning signal-processing descriptor: per-
    frame loudness (RMS), pitchiness proxy (zero-crossing rate), and
    brightness (spectral centroid via a plain FFT — numpy only, no audio/ML
    library), plus a whole-clip spectral-energy histogram as a coarse
    timbre signature. Real acoustic similarity, not speech understanding —
    same explicit quality tradeoff as the text and image encoders.
    """
    if samples.size == 0:
        return np.zeros(_RAW_DIM, dtype=np.float64)

    bounds = np.linspace(0, samples.size, _N_FRAMES + 1, dtype=int)
    frame_feats: list[float] = []
    nyquist = max(framerate / 2, 1.0)
    for i in range(_N_FRAMES):
        frame = samples[bounds[i] : bounds[i + 1]]
        if frame.size == 0:
            frame_feats.extend([0.0, 0.0, 0.0])
            continue
        rms = float(np.sqrt(np.mean(frame**2)))
        zero_crossings = float(np.mean(np.abs(np.diff(np.sign(frame))) > 0))
        spectrum = np.abs(np.fft.rfft(frame))
        freqs = np.fft.rfftfreq(frame.size, d=1.0 / framerate)
        spectrum_sum = spectrum.sum()
        centroid = float((freqs * spectrum).sum() / spectrum_sum) if spectrum_sum > 0 else 0.0
        frame_feats.extend([rms, zero_crossings, centroid / nyquist])

    spectrum = np.abs(np.fft.rfft(samples))
    hist, _ = np.histogram(spectrum, bins=_HIST_BINS)
    hist = hist.astype(np.float64)
    total = hist.sum()
    hist_feats = (hist / total if total > 0 else hist).tolist()

    return np.array(frame_feats + hist_feats, dtype=np.float64)


def encode_audio_samples(samples: np.ndarray, framerate: int) -> EncodedVector:
    """Same hand-written encoder as encode_audio(), but over already-decoded
    PCM — the entry point for audio decoded by something other than stdlib
    `wave` (e.g. compressed formats decoded via the opt-in Whisper backend,
    see nlp/transcription.py)."""
    raw = _raw_audio_features(samples, framerate)
    dense = raw @ _PROJECTION
    norm = np.linalg.norm(dense)
    if norm > 0:
        dense = dense / norm
    return EncodedVector(vector=dense.astype(np.float32).tolist(), model=MODEL_NAME, version=MODEL_VERSION, dims=_OUTPUT_DIM)


def encode_audio(data: bytes) -> EncodedVector:
    """WAV only (stdlib `wave` decodes it with zero extra dependency);
    compressed formats (mp3/etc) go through nlp/transcription.py instead,
    which decodes via PyAV and reuses encode_audio_samples() below."""
    samples, framerate = _read_wav_samples(data)
    return encode_audio_samples(samples, framerate)

from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass

import numpy as np

from neurodb_core.nlp.tokenizer import normalize_tokens

MODEL_NAME = "neurodb-lite-encoder"
MODEL_VERSION = 1

_HASH_DIM = 4096  # sparse hashing-trick vocabulary space
_OUTPUT_DIM = 256  # dense output dimensionality after random projection
_PROJECTION_SEED = 1337


def _hash_index(term: str, dim: int = _HASH_DIM) -> int:
    digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % dim


def _hash_sign(term: str) -> float:
    digest = hashlib.blake2b(term.encode("utf-8") + b":sign", digest_size=1).digest()
    return 1.0 if digest[0] % 2 == 0 else -1.0


def _projection_matrix(seed: int, in_dim: int, out_dim: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(loc=0.0, scale=1.0 / math.sqrt(out_dim), size=(in_dim, out_dim))


_PROJECTION = _projection_matrix(_PROJECTION_SEED, _HASH_DIM, _OUTPUT_DIM)


@dataclass
class EncodedVector:
    vector: list[float]
    model: str = MODEL_NAME
    version: int = MODEL_VERSION
    dims: int = _OUTPUT_DIM


def _hashed_tfidf_vector(text: str, *, idf: dict[str, float] | None = None) -> np.ndarray:
    tokens = normalize_tokens(text)
    vec = np.zeros(_HASH_DIM, dtype=np.float64)
    if not tokens:
        return vec
    counts = Counter(tokens)
    total = sum(counts.values())
    for term, count in counts.items():
        tf = count / total
        weight = tf * (idf.get(term, 1.0) if idf else 1.0)
        vec[_hash_index(term)] += weight * _hash_sign(term)
    return vec


def encode(text: str, *, idf: dict[str, float] | None = None) -> EncodedVector:
    """NeuroDB's own lightweight, fully hand-written text encoder.

    A hashing-trick term vector (TF, optionally IDF-weighted) is reduced via
    a fixed-seed Gaussian random projection to a dense vector. By the
    Johnson-Lindenstrauss lemma this approximately preserves pairwise
    distances from the sparse term space, so cosine similarity between
    outputs tracks term-overlap similarity between texts. This is a
    from-scratch encoder, not a pretrained transformer — embedding quality
    is intentionally traded for zero external dependencies/weights.
    """
    sparse = _hashed_tfidf_vector(text, idf=idf)
    dense = sparse @ _PROJECTION
    norm = np.linalg.norm(dense)
    if norm > 0:
        dense = dense / norm
    return EncodedVector(vector=dense.astype(np.float32).tolist())


def encode_as_embedding_record(text: str, *, idf: dict[str, float] | None = None) -> "EmbeddingRecord":
    """Convenience wrapper returning a storage-ready EmbeddingRecord, used
    both at ingestion time and by the re-embedding job."""
    from neurodb_core.storage.records import EmbeddingRecord

    encoded = encode(text, idf=idf)
    return EmbeddingRecord(model=encoded.model, version=encoded.version, dims=encoded.dims, vector=encoded.vector)

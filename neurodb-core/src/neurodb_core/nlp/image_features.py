from __future__ import annotations

import io
import math

import numpy as np
from PIL import Image

from neurodb_core.nlp.embedding import EncodedVector

MODEL_NAME = "neurodb-lite-image-encoder"
MODEL_VERSION = 1

_GRID = 8  # spatial layout captured as an 8x8 grid of average cell color
_HIST_BINS = 32  # per-channel global color-histogram resolution
_RAW_DIM = _GRID * _GRID * 3 + _HIST_BINS * 3  # 192 (layout) + 96 (palette) = 288
_OUTPUT_DIM = 256
_PROJECTION_SEED = 4242


def _projection_matrix(seed: int, in_dim: int, out_dim: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.normal(loc=0.0, scale=1.0 / math.sqrt(out_dim), size=(in_dim, out_dim))


_PROJECTION = _projection_matrix(_PROJECTION_SEED, _RAW_DIM, _OUTPUT_DIM)


def _raw_image_features(image: Image.Image) -> np.ndarray:
    """Hand-written image descriptor: no CNN, no pretrained weights. Two
    classic, pre-deep-learning signals concatenated:

    - A GRIDxGRID average-color layout (where color sits in the frame).
    - A global per-channel color histogram (overall palette, position-
      independent).

    Cheap, real, and genuinely captures visual similarity for palette/
    composition — not object or scene understanding, matching this
    project's explicit encoder quality tradeoff (see nlp/embedding.py).
    """
    rgb = image.convert("RGB")
    arr = np.asarray(rgb, dtype=np.float64) / 255.0  # (H, W, 3)
    h, w, _ = arr.shape

    cell_h = max(h // _GRID, 1)
    cell_w = max(w // _GRID, 1)
    grid_feats: list[float] = []
    for gy in range(_GRID):
        for gx in range(_GRID):
            cell = arr[gy * cell_h : (gy + 1) * cell_h, gx * cell_w : (gx + 1) * cell_w]
            if cell.size == 0:
                grid_feats.extend([0.0, 0.0, 0.0])
            else:
                grid_feats.extend(cell.reshape(-1, 3).mean(axis=0).tolist())

    hist_feats: list[float] = []
    for c in range(3):
        hist, _ = np.histogram(arr[:, :, c], bins=_HIST_BINS, range=(0.0, 1.0))
        hist = hist.astype(np.float64)
        total = hist.sum()
        hist_feats.extend((hist / total if total > 0 else hist).tolist())

    return np.array(grid_feats + hist_feats, dtype=np.float64)


def encode_image(data: bytes) -> EncodedVector:
    """Decode + hand-written feature extraction, reduced via the same
    fixed-seed random-projection trick as the text encoder (nlp/embedding.py)
    so it lands in the same output dimensionality/storage schema. Image
    decoding itself uses Pillow — general-purpose plumbing, the same
    exception category pypdf falls under for PDFs."""
    image = Image.open(io.BytesIO(data))
    raw = _raw_image_features(image)
    dense = raw @ _PROJECTION
    norm = np.linalg.norm(dense)
    if norm > 0:
        dense = dense / norm
    return EncodedVector(vector=dense.astype(np.float32).tolist(), model=MODEL_NAME, version=MODEL_VERSION, dims=_OUTPUT_DIM)

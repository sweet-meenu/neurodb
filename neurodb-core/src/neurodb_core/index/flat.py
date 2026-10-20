from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np


@dataclass
class FlatIndex:
    """Brute-force exact nearest-neighbor search over cosine similarity:
    always correct, O(n) per query. Used for small collections and as the
    ground-truth baseline HNSW recall is validated against.
    """

    dims: int
    ids: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self._matrix: np.ndarray = np.zeros((0, self.dims), dtype=np.float32)
        self._id_to_row: dict[str, int] = {}

    def add(self, id_: str, vector: list[float] | np.ndarray) -> None:
        vec = np.asarray(vector, dtype=np.float32).reshape(1, -1)
        if vec.shape[1] != self.dims:
            raise ValueError(f"expected a {self.dims}-dim vector, got {vec.shape[1]}")
        if id_ in self._id_to_row:
            self._matrix[self._id_to_row[id_]] = vec
            return
        self._id_to_row[id_] = len(self.ids)
        self.ids.append(id_)
        self._matrix = np.vstack([self._matrix, vec])

    def remove(self, id_: str) -> None:
        if id_ not in self._id_to_row:
            return
        row = self._id_to_row.pop(id_)
        self.ids.pop(row)
        self._matrix = np.delete(self._matrix, row, axis=0)
        for other_id, other_row in self._id_to_row.items():
            if other_row > row:
                self._id_to_row[other_id] = other_row - 1

    def items(self) -> list[tuple[str, np.ndarray]]:
        return list(zip(self.ids, self._matrix))

    def search(self, query: list[float] | np.ndarray, k: int = 10) -> list[tuple[str, float]]:
        if len(self.ids) == 0:
            return []
        q = np.asarray(query, dtype=np.float32)
        q_norm = np.linalg.norm(q)
        if q_norm > 0:
            q = q / q_norm

        matrix_norms = np.linalg.norm(self._matrix, axis=1, keepdims=True)
        matrix_norms[matrix_norms == 0] = 1.0
        normalized = self._matrix / matrix_norms
        sims = normalized @ q

        k = min(k, len(self.ids))
        top_indices = np.argpartition(-sims, k - 1)[:k]
        top_indices = top_indices[np.argsort(-sims[top_indices])]
        return [(self.ids[i], float(sims[i])) for i in top_indices]

    def __len__(self) -> int:
        return len(self.ids)

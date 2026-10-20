from __future__ import annotations

from dataclasses import dataclass

from neurodb_core.index.flat import FlatIndex
from neurodb_core.index.hnsw import HNSWIndex

HNSW_PROMOTION_THRESHOLD = 5000  # collections below this size use exact flat search


@dataclass
class IndexStats:
    kind: str
    size: int


class CollectionIndex:
    """Adaptive index for one (collection, embedding-field) pair: brute-force
    flat search below a size threshold (always exact, zero build cost),
    transparently promoted to a hand-written HNSW graph once the collection
    grows past it (approximate, sub-linear query time).
    """

    def __init__(self, dims: int, *, threshold: int = HNSW_PROMOTION_THRESHOLD):
        self.dims = dims
        self.threshold = threshold
        self.flat = FlatIndex(dims=dims)
        self.hnsw: HNSWIndex | None = None

    @property
    def kind(self) -> str:
        return "hnsw" if self.hnsw is not None else "flat"

    def __len__(self) -> int:
        return len(self.hnsw) if self.hnsw is not None else len(self.flat)

    def add(self, id_: str, vector: list[float]) -> None:
        self.flat.add(id_, vector)
        if self.hnsw is None and len(self.flat) >= self.threshold:
            self._promote()
        elif self.hnsw is not None:
            self.hnsw.add(id_, vector)

    def remove(self, id_: str) -> None:
        self.flat.remove(id_)
        if self.hnsw is not None:
            self.hnsw.remove(id_)

    def search(self, query: list[float], k: int = 10) -> list[tuple[str, float]]:
        if self.hnsw is not None:
            return self.hnsw.search(query, k=k)
        return self.flat.search(query, k=k)

    def stats(self) -> IndexStats:
        return IndexStats(kind=self.kind, size=len(self))

    def _promote(self) -> None:
        hnsw = HNSWIndex(dims=self.dims)
        for id_, vector in self.flat.items():
            hnsw.add(id_, vector)
        self.hnsw = hnsw


class IndexManager:
    """Owns one adaptive CollectionIndex per (collection, embedding field)
    pair within a project, so multiple embedding models/fields on the same
    collection get independent indexes.
    """

    def __init__(self) -> None:
        self._indexes: dict[tuple[str, str], CollectionIndex] = {}

    def get_or_create(self, collection: str, field: str, dims: int) -> CollectionIndex:
        key = (collection, field)
        if key not in self._indexes:
            self._indexes[key] = CollectionIndex(dims=dims)
        return self._indexes[key]

    def replace(self, collection: str, field: str, index: CollectionIndex) -> None:
        """Atomically swaps in a fully-built index (e.g. once a background
        re-embedding migration to a new, differently-dimensioned model has
        finished backfilling a shadow index) — the cutover point where query
        traffic starts being served by the new model, with no downtime."""
        self._indexes[(collection, field)] = index

    def add(self, collection: str, field: str, id_: str, vector: list[float]) -> None:
        index = self.get_or_create(collection, field, dims=len(vector))
        index.add(id_, vector)

    def remove(self, collection: str, field: str, id_: str) -> None:
        key = (collection, field)
        if key in self._indexes:
            self._indexes[key].remove(id_)

    def search(
        self, collection: str, field: str, query: list[float], k: int = 10
    ) -> list[tuple[str, float]]:
        key = (collection, field)
        if key not in self._indexes:
            return []
        return self._indexes[key].search(query, k=k)

    def stats(self, collection: str, field: str) -> IndexStats | None:
        index = self._indexes.get((collection, field))
        return index.stats() if index else None

    def fields(self, collection: str) -> list[str]:
        """Every embedding field indexed for a collection — a collection can
        hold several (e.g. "text" and "image" side by side for multimodal
        objects), each with its own independent adaptive index."""
        return [field for (c, field) in self._indexes if c == collection]

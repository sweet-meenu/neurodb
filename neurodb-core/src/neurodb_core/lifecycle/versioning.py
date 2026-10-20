from __future__ import annotations

import time
from dataclasses import dataclass, field


@dataclass
class ModelVersionInfo:
    model: str
    version: int
    dims: int
    activated_at: float = field(default_factory=time.time)


class EmbeddingVersionRegistry:
    """Tracks, per (collection, field), which embedding model/version is
    currently 'current' and the full history of versions that have been
    active. This is the basis for detecting stale embeddings (ReembedJob)
    and for explainable-search reporting which model produced a match.
    """

    def __init__(self) -> None:
        self._current: dict[tuple[str, str], ModelVersionInfo] = {}
        self._history: dict[tuple[str, str], list[ModelVersionInfo]] = {}

    def set_current(self, collection: str, field: str, model: str, version: int, dims: int) -> None:
        key = (collection, field)
        info = ModelVersionInfo(model=model, version=version, dims=dims)
        self._current[key] = info
        self._history.setdefault(key, []).append(info)

    def current(self, collection: str, field: str) -> ModelVersionInfo | None:
        return self._current.get((collection, field))

    def history(self, collection: str, field: str) -> list[ModelVersionInfo]:
        return list(self._history.get((collection, field), []))

    def is_stale(self, collection: str, field: str, embedding_model: str, embedding_version: int) -> bool:
        current = self.current(collection, field)
        if current is None:
            return False
        return (embedding_model, embedding_version) != (current.model, current.version)

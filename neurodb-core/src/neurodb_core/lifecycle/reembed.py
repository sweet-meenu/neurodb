from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from neurodb_core.index.manager import CollectionIndex, IndexManager
from neurodb_core.lifecycle.versioning import EmbeddingVersionRegistry
from neurodb_core.storage.records import EmbeddingRecord
from neurodb_core.storage.storage_engine import StorageEngine


@dataclass
class MigrationProgress:
    collection: str
    field: str
    target_model: str
    target_version: int
    target_dims: int
    total: int
    migrated: int = 0

    @property
    def fraction_complete(self) -> float:
        return (self.migrated / self.total) if self.total else 1.0

    @property
    def done(self) -> bool:
        return self.migrated >= self.total


class ReembedJob:
    """Background re-embedding: detects objects whose embedding for a given
    (collection, field) is on an outdated model/version and regenerates it
    via the current encoder, writing results back in batches.

    A new model's output dimensionality generally differs from the old
    one's, so migrated vectors cannot simply be added into the live index
    in place. Instead each migration backfills a *shadow* index at the new
    dimensionality while the live index keeps serving queries unchanged;
    once every object is migrated the shadow index is atomically swapped in
    via IndexManager.replace(). This gives the "no downtime, no application
    changes" rollout the design calls for: storage is updated incrementally
    (each batch is a normal MVCC-versioned write, so AS OF queries against
    the old version still work), while search ranking flips to the new
    model in one atomic step at the end rather than drifting mid-migration.
    """

    def __init__(
        self,
        storage: StorageEngine,
        index_manager: IndexManager,
        registry: EmbeddingVersionRegistry,
    ):
        self.storage = storage
        self.index_manager = index_manager
        self.registry = registry
        self._migrations: dict[tuple[str, str], MigrationProgress] = {}
        self._shadow_indexes: dict[tuple[str, str], CollectionIndex] = {}

    def start_migration(
        self, collection: str, field: str, target_model: str, target_version: int, target_dims: int
    ) -> MigrationProgress:
        stale_ids = self._stale_object_ids(collection, field, target_model, target_version)
        progress = MigrationProgress(
            collection=collection,
            field=field,
            target_model=target_model,
            target_version=target_version,
            target_dims=target_dims,
            total=len(stale_ids),
        )
        self._migrations[(collection, field)] = progress
        self._shadow_indexes[(collection, field)] = CollectionIndex(dims=target_dims)
        return progress

    def _stale_object_ids(
        self, collection: str, field: str, target_model: str, target_version: int
    ) -> list[str]:
        stale = []
        for ov in self.storage.scan(collection):
            emb = ov.embeddings.get(field)
            if emb is None or (emb.model, emb.version) != (target_model, target_version):
                stale.append(ov.object_id)
        return stale

    def run_batch(
        self,
        collection: str,
        field: str,
        encode_fn: Callable[[str], EmbeddingRecord],
        *,
        text_field: str = "text",
        batch_size: int = 50,
    ) -> MigrationProgress:
        key = (collection, field)
        progress = self._migrations.get(key)
        if progress is None:
            raise ValueError(f"no in-progress migration for ({collection}, {field})")
        shadow = self._shadow_indexes[key]

        stale_ids = self._stale_object_ids(collection, field, progress.target_model, progress.target_version)
        for object_id in stale_ids[:batch_size]:
            ov = self.storage.get(object_id)
            if ov is None:
                progress.migrated += 1
                continue
            text = ov.modalities.get(text_field, "")
            new_embedding = encode_fn(text)
            embeddings = dict(ov.embeddings)
            embeddings[field] = new_embedding
            self.storage.put(
                collection,
                object_id=object_id,
                modalities=ov.modalities,
                metadata=ov.metadata,
                embeddings=embeddings,
            )
            shadow.add(object_id, new_embedding.vector)
            progress.migrated += 1

        if progress.done:
            self.index_manager.replace(collection, field, shadow)
            self.registry.set_current(
                collection, field, progress.target_model, progress.target_version, progress.target_dims
            )
        return progress

    def status(self, collection: str, field: str) -> MigrationProgress | None:
        return self._migrations.get((collection, field))

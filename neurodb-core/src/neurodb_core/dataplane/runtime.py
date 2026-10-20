from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path

from neurodb_core.index.manager import IndexManager
from neurodb_core.lifecycle.reembed import ReembedJob
from neurodb_core.lifecycle.versioning import EmbeddingVersionRegistry
from neurodb_core.nlp.captioning import build_caption_fn
from neurodb_core.nlp.pipeline import DocumentPipeline
from neurodb_core.nlp.transcription import build_transcribe_fn
from neurodb_core.storage.storage_engine import StorageEngine


@dataclass
class ProjectRuntime:
    storage: StorageEngine
    index_manager: IndexManager
    registry: EmbeddingVersionRegistry
    pipeline: DocumentPipeline
    reembed_job: ReembedJob


class ProjectRuntimeCache:
    """Lazily constructs and caches the in-memory engines (StorageEngine,
    IndexManager, ...) for each project, keyed by project id. One process
    can host many projects; each gets its own isolated storage root and
    indexes, matching the single-owner-per-project model.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._runtimes: dict[str, ProjectRuntime] = {}
        # Built once, env-driven, off by default (see nlp/captioning.py and
        # nlp/transcription.py) — every project's pipeline shares the same
        # opt-in enrichment hooks.
        self._caption_fn = build_caption_fn()
        self._transcribe_fn = build_transcribe_fn()

    def get_or_create(self, project_id: str, storage_path: str) -> ProjectRuntime:
        with self._lock:
            if project_id not in self._runtimes:
                storage = StorageEngine(Path(storage_path))
                index_manager = IndexManager()
                registry = EmbeddingVersionRegistry()
                self._rebuild_indexes(storage, index_manager)
                self._runtimes[project_id] = ProjectRuntime(
                    storage=storage,
                    index_manager=index_manager,
                    registry=registry,
                    pipeline=DocumentPipeline(caption_fn=self._caption_fn, transcribe_fn=self._transcribe_fn),
                    reembed_job=ReembedJob(storage, index_manager, registry),
                )
            return self._runtimes[project_id]

    @staticmethod
    def _rebuild_indexes(storage: StorageEngine, index_manager: IndexManager) -> None:
        """The index manager isn't itself persisted to disk; on first access
        after a process restart it's rehydrated from whatever is already
        durable in the storage engine, so search works immediately without
        a manual reindex step.
        """
        for collection in storage.collections():
            for ov in storage.scan(collection):
                for field, emb in ov.embeddings.items():
                    index_manager.add(collection, field, ov.object_id, emb.vector)

    def evict(self, project_id: str) -> None:
        with self._lock:
            self._runtimes.pop(project_id, None)

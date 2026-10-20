from __future__ import annotations

import threading
from typing import Iterable

from neurodb_core.storage.records import ObjectVersion


class MVCCStore:
    """In-memory multi-version store for the 'hot' tier: versions that have
    been committed to the WAL but not yet flushed into a Parquet segment.
    StorageEngine consults this first and falls back to reading segments for
    anything that has already been checkpointed out of memory.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._versions: dict[str, list[ObjectVersion]] = {}
        self._collections: dict[str, set[str]] = {}

    def add_version(self, ov: ObjectVersion) -> None:
        with self._lock:
            versions = self._versions.setdefault(ov.object_id, [])
            versions.append(ov)
            versions.sort(key=lambda v: v.version)
            self._collections.setdefault(ov.collection, set()).add(ov.object_id)

    def get_latest(self, object_id: str) -> ObjectVersion | None:
        with self._lock:
            versions = self._versions.get(object_id)
            return versions[-1] if versions else None

    def get_visible(self, object_id: str, watermark: int) -> ObjectVersion | None:
        with self._lock:
            versions = self._versions.get(object_id)
            if not versions:
                return None
            visible = [v for v in versions if v.txn_id <= watermark]
            return visible[-1] if visible else None

    def get_as_of_version(self, object_id: str, as_of_version: int) -> ObjectVersion | None:
        with self._lock:
            versions = self._versions.get(object_id)
            if not versions:
                return None
            candidates = [v for v in versions if v.version <= as_of_version]
            return candidates[-1] if candidates else None

    def get_as_of_ts(self, object_id: str, ts: float) -> ObjectVersion | None:
        with self._lock:
            versions = self._versions.get(object_id)
            if not versions:
                return None
            candidates = [v for v in versions if v.commit_ts <= ts]
            return candidates[-1] if candidates else None

    def object_ids(self, collection: str) -> Iterable[str]:
        with self._lock:
            return set(self._collections.get(collection, set()))

    def drain_committed(self, watermark: int) -> list[ObjectVersion]:
        """Removes every version with txn_id <= watermark from the hot tier
        (they're about to be durably persisted in a segment) and returns
        them for writing. Versions from still-active transactions are left
        in place.
        """
        with self._lock:
            drained: list[ObjectVersion] = []
            for object_id, versions in list(self._versions.items()):
                flushed = [v for v in versions if v.txn_id <= watermark]
                keep = [v for v in versions if v.txn_id > watermark]
                if not flushed:
                    continue
                drained.extend(flushed)
                if keep:
                    self._versions[object_id] = keep
                else:
                    del self._versions[object_id]
                    for ids in self._collections.values():
                        ids.discard(object_id)
            return drained

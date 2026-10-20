from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

from neurodb_core.storage.catalog import Catalog
from neurodb_core.storage.mvcc import MVCCStore
from neurodb_core.storage.records import EmbeddingRecord, ObjectVersion, new_object_id
from neurodb_core.storage.segment import read_segment, write_segment
from neurodb_core.storage.txn import TransactionManager
from neurodb_core.storage.wal import WriteAheadLog

FLUSH_THRESHOLD = 500  # committed versions buffered before an automatic checkpoint


class StorageEngine:
    """Per-project storage engine: WAL-durable, MVCC-isolated, columnar
    (Parquet) at rest. The index manager and NeuroQL executor both sit on
    top of this — it is the single point of truth for object reads/writes.
    """

    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.segments_dir = self.root / "segments"
        self.catalog = Catalog(self.root / "catalog.json")
        self.wal = WriteAheadLog(self.root / "wal.log")
        self.mvcc = MVCCStore()
        self._lock = threading.RLock()
        self._pending_since_flush = 0
        # Segments are immutable once written, so their parsed contents can be
        # cached by segment_id for the process lifetime — avoids re-reading and
        # re-deserializing every segment from disk on every lookup.
        self._segment_cache: dict[str, list[ObjectVersion]] = {}
        # object_id -> its latest version found across all flushed segments,
        # maintained incrementally as new segments are read into the cache
        # above. Lets a single-object lookup for anything already flushed be
        # an O(1) dict access instead of a linear rescan of every segment —
        # matters once a collection spans many flush cycles (e.g. several
        # books' worth of chunks), since single-object get() is called once
        # per semantic-search hit.
        self._segment_latest_index: dict[str, ObjectVersion] = {}

        max_txn_id = self.catalog.last_txn_id
        for record in self.wal.replay():
            if record["op"] == "put":
                ov = ObjectVersion.from_dict(record["version"])
                self.mvcc.add_version(ov)
                max_txn_id = max(max_txn_id, ov.txn_id)
        self.txns = TransactionManager(start_txn_id=max_txn_id)

    # -- writes -------------------------------------------------------------

    def put(
        self,
        collection: str,
        *,
        object_id: str | None = None,
        modalities: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        embeddings: dict[str, EmbeddingRecord] | None = None,
    ) -> ObjectVersion:
        with self._lock:
            self.catalog.ensure_collection(collection)
            # A caller-supplied object_id may already have versions on disk (the
            # reembedding job upserts by id) and needs the version-chain lookup.
            # A freshly minted uuid4 cannot collide with anything already stored,
            # so skip it — for bulk ingestion this avoids rescanning every
            # flushed segment on disk for every single new chunk.
            is_new_object = object_id is None
            object_id = object_id or new_object_id()
            prev = None if is_new_object else self._latest_any_version(object_id)
            next_version = (prev.version + 1) if prev else 1

            txn_id = self.txns.begin()
            ov = ObjectVersion(
                object_id=object_id,
                collection=collection,
                version=next_version,
                txn_id=txn_id,
                commit_ts=0.0,
                tombstone=False,
                modalities=modalities or {},
                metadata=metadata or {},
                embeddings=embeddings or {},
            )
            ov.commit_ts = self.txns.commit(txn_id)

            self.wal.append({"op": "put", "version": ov.to_dict()})
            self.mvcc.add_version(ov)
            self.catalog.record_txn_watermark(txn_id)

            self._pending_since_flush += 1
            if self._pending_since_flush >= FLUSH_THRESHOLD:
                self.flush()
            return ov

    def put_many(self, collection: str, items: list[dict[str, Any]]) -> list[ObjectVersion]:
        """Bulk insert for freshly-created objects — always assigns a new id,
        so (like put() with no object_id) it never needs the version-chain
        lookup. Ingestion pipelines call this instead of put() in a loop: the
        whole batch shares one WAL fsync and one catalog persist instead of
        one of each per chunk, which is what a multi-thousand-chunk document
        was paying for otherwise. Durability is still "all or nothing" per
        batch — a crash before the batch's fsync loses the whole in-flight
        document, not a partial/corrupt slice of it (WAL replay already
        drops any torn trailing write), and nothing already-committed by an
        earlier put()/put_many() call is affected.
        """
        if not items:
            return []
        with self._lock:
            results: list[ObjectVersion] = []
            for item in items:
                self.catalog.ensure_collection(collection)
                txn_id = self.txns.begin()
                ov = ObjectVersion(
                    object_id=new_object_id(),
                    collection=collection,
                    version=1,
                    txn_id=txn_id,
                    commit_ts=0.0,
                    tombstone=False,
                    modalities=item.get("modalities") or {},
                    metadata=item.get("metadata") or {},
                    embeddings=item.get("embeddings") or {},
                )
                ov.commit_ts = self.txns.commit(txn_id)

                self.wal.append({"op": "put", "version": ov.to_dict()}, fsync=False)
                self.mvcc.add_version(ov)
                self.catalog.record_txn_watermark(txn_id)
                results.append(ov)

                self._pending_since_flush += 1
                if self._pending_since_flush >= FLUSH_THRESHOLD:
                    # About to truncate the WAL via flush() — durably commit
                    # everything queued so far first, or it's lost rather
                    # than merely "not yet committed".
                    self.wal.fsync()
                    self.flush()

            self.wal.fsync()
            self.catalog.persist()
            return results

    def delete(self, object_id: str) -> ObjectVersion | None:
        with self._lock:
            prev = self._latest_any_version(object_id)
            if prev is None or prev.tombstone:
                return None
            txn_id = self.txns.begin()
            ov = ObjectVersion(
                object_id=prev.object_id,
                collection=prev.collection,
                version=prev.version + 1,
                txn_id=txn_id,
                commit_ts=0.0,
                tombstone=True,
                modalities=prev.modalities,
                metadata=prev.metadata,
                embeddings=prev.embeddings,
            )
            ov.commit_ts = self.txns.commit(txn_id)
            self.wal.append({"op": "put", "version": ov.to_dict()})
            self.mvcc.add_version(ov)
            self.catalog.record_txn_watermark(txn_id)
            return ov

    # -- reads ----------------------------------------------------------------

    def get(
        self,
        object_id: str,
        *,
        as_of_version: int | None = None,
        as_of_ts: float | None = None,
    ) -> ObjectVersion | None:
        if as_of_version is not None:
            ov = self.mvcc.get_as_of_version(object_id, as_of_version)
            if ov is None:
                ov = self._segment_as_of(object_id, version=as_of_version)
        elif as_of_ts is not None:
            ov = self.mvcc.get_as_of_ts(object_id, as_of_ts)
            if ov is None:
                ov = self._segment_as_of(object_id, ts=as_of_ts)
        else:
            watermark = self.txns.snapshot()
            ov = self.mvcc.get_visible(object_id, watermark)
            if ov is None:
                ov = self._segment_latest(object_id)
        if ov is None or ov.tombstone:
            return None
        return ov

    def scan(
        self,
        collection: str,
        *,
        as_of_version: int | None = None,
        as_of_ts: float | None = None,
    ) -> list[ObjectVersion]:
        if as_of_version is not None or as_of_ts is not None:
            # Time-travel scan: uncommon path, object count is usually small
            # by the time anyone runs one, so per-object get() is fine here.
            ids: set[str] = set(self.mvcc.object_ids(collection))
            for seg_meta in self.catalog.segments():
                if collection in seg_meta["collections"]:
                    for ov in self._read_segment_cached(seg_meta):
                        ids.add(ov.object_id)
            results: list[ObjectVersion] = []
            for object_id in ids:
                ov = self.get(object_id, as_of_version=as_of_version, as_of_ts=as_of_ts)
                if ov is not None and ov.collection == collection:
                    results.append(ov)
            return results

        # Current-state scan (the hot path: collection listings, index
        # rebuild on restart, browsing ingested objects). Computed in one
        # pass per segment instead of the old per-object `get()` call, which
        # for any already-flushed object re-scanned every segment on disk —
        # O(objects x segments) and the reason large ingests looked "stuck".
        with self._lock:
            watermark = self.txns.snapshot()
            hot_ids = set(self.mvcc.object_ids(collection))
            results = []
            for object_id in hot_ids:
                ov = self.mvcc.get_visible(object_id, watermark)
                if ov is not None and not ov.tombstone and ov.collection == collection:
                    results.append(ov)

            self._ensure_segment_index()
            results.extend(
                ov
                for object_id, ov in self._segment_latest_index.items()
                if object_id not in hot_ids and ov.collection == collection and not ov.tombstone
            )
            return results

    def collections(self) -> list[str]:
        return self.catalog.collections()

    # -- internal helpers -------------------------------------------------

    def _latest_any_version(self, object_id: str) -> ObjectVersion | None:
        hot = self.mvcc.get_latest(object_id)
        if hot is not None:
            return hot
        return self._segment_latest(object_id)

    def _segment_latest(self, object_id: str) -> ObjectVersion | None:
        self._ensure_segment_index()
        return self._segment_latest_index.get(object_id)

    def _ensure_segment_index(self) -> None:
        """Backfills the id -> latest-version index for any segment not yet
        read into the cache. A no-op once every known segment has been seen
        (segments are only ever appended, never rewritten)."""
        for seg_meta in self.catalog.segments():
            if seg_meta["segment_id"] not in self._segment_cache:
                self._read_segment_cached(seg_meta)

    def _segment_as_of(
        self, object_id: str, *, version: int | None = None, ts: float | None = None
    ) -> ObjectVersion | None:
        best: ObjectVersion | None = None
        for seg_meta in self.catalog.segments():
            for ov in self._read_segment_cached(seg_meta):
                if ov.object_id != object_id:
                    continue
                if version is not None and ov.version > version:
                    continue
                if ts is not None and ov.commit_ts > ts:
                    continue
                if best is None or ov.version > best.version:
                    best = ov
        return best

    def _read_segment_cached(self, seg_meta: dict) -> list[ObjectVersion]:
        segment_id = seg_meta["segment_id"]
        cached = self._segment_cache.get(segment_id)
        if cached is None:
            cached = read_segment(self.segments_dir, seg_meta)
            self._segment_cache[segment_id] = cached
            for ov in cached:
                current = self._segment_latest_index.get(ov.object_id)
                if current is None or ov.version > current.version:
                    self._segment_latest_index[ov.object_id] = ov
        return cached

    # -- lifecycle ----------------------------------------------------------

    def flush(self) -> None:
        with self._lock:
            watermark = self.txns.snapshot()
            drained = self.mvcc.drain_committed(watermark)
            if not drained:
                return
            seg_meta = write_segment(self.segments_dir, drained)
            self.catalog.add_segment(seg_meta)
            self.wal.truncate()
            self._pending_since_flush = 0

    def close(self) -> None:
        self.flush()
        self.wal.close()

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class Catalog:
    """Delta-Lake-style manifest for a project's storage root: an append-only
    action log (segment additions) plus a materialized current-state view,
    persisted as JSON. This is what NeuroQL's version history / time-travel
    walks, and what a restart replays to recover segment locations and the
    last-used transaction id.
    """

    def __init__(self, path: Path):
        self.path = path
        self._lock = threading.Lock()
        self._state: dict[str, Any] = {
            "catalog_version": 0,
            "last_txn_id": 0,
            "segments": [],
            "collections": {},
            "log": [],
        }
        if self.path.exists():
            self._state = json.loads(self.path.read_text(encoding="utf-8"))

    @property
    def last_txn_id(self) -> int:
        with self._lock:
            return self._state["last_txn_id"]

    def segments(self) -> list[dict]:
        with self._lock:
            return list(self._state["segments"])

    def record_txn_watermark(self, txn_id: int) -> None:
        """Advances the in-memory watermark only — deliberately does not hit
        disk on every call. A crash before the next persist is harmless: the
        WAL already fsyncs each put, and replay recovers the true max txn_id
        from the WAL records themselves (this watermark is only a floor for
        that recovery, see StorageEngine.__init__). It only needs to be
        durable by the time the WAL is truncated, which is exactly when
        add_segment()/persist() below already run — so persisting it on every
        single put would just be a redundant full-file rewrite per object."""
        with self._lock:
            if txn_id > self._state["last_txn_id"]:
                self._state["last_txn_id"] = txn_id

    def persist(self) -> None:
        with self._lock:
            self._persist()

    def add_segment(self, segment_meta: dict) -> None:
        with self._lock:
            self._state["catalog_version"] += 1
            self._state["segments"].append(segment_meta)
            for name in segment_meta["collections"]:
                self._state["collections"].setdefault(name, {"object_count": 0})
            self._state["log"].append(
                {
                    "catalog_version": self._state["catalog_version"],
                    "action": "add_segment",
                    "segment_id": segment_meta["segment_id"],
                    "timestamp": time.time(),
                }
            )
            self._persist()

    def ensure_collection(self, name: str) -> None:
        with self._lock:
            if name not in self._state["collections"]:
                self._state["collections"][name] = {"object_count": 0}
                self._persist()

    def collections(self) -> list[str]:
        with self._lock:
            return sorted(self._state["collections"].keys())

    def history(self) -> list[dict]:
        with self._lock:
            return list(self._state["log"])

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._state, indent=2), encoding="utf-8")
        tmp.replace(self.path)

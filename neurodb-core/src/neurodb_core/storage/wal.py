from __future__ import annotations

import json
import os
import struct
import threading
from pathlib import Path
from typing import Any, Iterator

_LEN_STRUCT = struct.Struct(">I")  # 4-byte big-endian length prefix


class WriteAheadLog:
    """Append-only, length-prefixed binary WAL. Every write is fsync'd before
    the caller's transaction is considered committed, so a crash between
    commit and the next segment flush loses nothing: replay() reconstructs
    every committed record in order.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._fh = open(self.path, "ab", buffering=0)

    def append(self, record: dict[str, Any], *, fsync: bool = True) -> None:
        payload = json.dumps(record, separators=(",", ":")).encode("utf-8")
        with self._lock:
            self._fh.write(_LEN_STRUCT.pack(len(payload)))
            self._fh.write(payload)
            if fsync:
                os.fsync(self._fh.fileno())

    def fsync(self) -> None:
        """Durably commits everything appended so far without appending a new
        record — used to group-commit a batch of fsync=False appends with a
        single fsync, instead of one per record."""
        with self._lock:
            os.fsync(self._fh.fileno())

    def replay(self) -> Iterator[dict[str, Any]]:
        """Yields every fully-written record in the log, in append order.
        A partially-written record at the tail (crash mid-write) is silently
        dropped, matching standard WAL torn-write handling.
        """
        if not self.path.exists():
            return
        with open(self.path, "rb") as fh:
            while True:
                len_bytes = fh.read(_LEN_STRUCT.size)
                if len(len_bytes) < _LEN_STRUCT.size:
                    break
                (length,) = _LEN_STRUCT.unpack(len_bytes)
                payload = fh.read(length)
                if len(payload) < length:
                    break
                yield json.loads(payload.decode("utf-8"))

    def truncate(self) -> None:
        """Called once a checkpoint (segment flush) has durably persisted
        everything the WAL was protecting, making the log redundant.
        """
        with self._lock:
            self._fh.close()
            self._fh = open(self.path, "wb", buffering=0)

    def close(self) -> None:
        with self._lock:
            self._fh.close()

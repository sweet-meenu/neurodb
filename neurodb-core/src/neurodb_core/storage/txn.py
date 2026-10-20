from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from enum import Enum


class TxnState(Enum):
    ACTIVE = "active"
    COMMITTED = "committed"
    ABORTED = "aborted"


@dataclass
class TxnInfo:
    txn_id: int
    state: TxnState
    commit_ts: float | None = None


class TransactionManager:
    """Issues monotonic transaction ids and tracks the commit watermark used
    for snapshot isolation: a reader that took its snapshot at watermark W
    never sees a write from a transaction with id > W, even if that write
    commits while the read is still in progress.
    """

    def __init__(self, start_txn_id: int = 0):
        self._lock = threading.Lock()
        self._next_txn_id = start_txn_id + 1
        self._committed_watermark = start_txn_id
        self._txns: dict[int, TxnInfo] = {}

    def begin(self) -> int:
        with self._lock:
            txn_id = self._next_txn_id
            self._next_txn_id += 1
            self._txns[txn_id] = TxnInfo(txn_id=txn_id, state=TxnState.ACTIVE)
            return txn_id

    def commit(self, txn_id: int) -> float:
        with self._lock:
            info = self._txns.get(txn_id)
            if info is None:
                raise ValueError(f"unknown txn {txn_id}")
            commit_ts = time.time()
            info.state = TxnState.COMMITTED
            info.commit_ts = commit_ts
            if txn_id > self._committed_watermark:
                self._committed_watermark = txn_id
            return commit_ts

    def abort(self, txn_id: int) -> None:
        with self._lock:
            info = self._txns.get(txn_id)
            if info is not None:
                info.state = TxnState.ABORTED

    def snapshot(self) -> int:
        with self._lock:
            return self._committed_watermark

    def is_committed(self, txn_id: int) -> bool:
        with self._lock:
            info = self._txns.get(txn_id)
            return info is not None and info.state is TxnState.COMMITTED

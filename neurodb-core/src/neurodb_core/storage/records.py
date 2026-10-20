from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


def new_object_id() -> str:
    return uuid.uuid4().hex


@dataclass
class EmbeddingRecord:
    """A single embedding attached to an object, tagged with the exact model
    and parameters that produced it so the embedding-lifecycle subsystem can
    detect staleness and re-embed later without ambiguity.
    """

    model: str
    version: int
    dims: int
    vector: list[float]
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class ObjectVersion:
    """One MVCC version of a NeuroDB object. A given object_id may have many
    ObjectVersion rows over time; only the latest one visible to a reader's
    snapshot (or an explicit AS OF version/timestamp) is returned.
    """

    object_id: str
    collection: str
    version: int
    txn_id: int
    commit_ts: float
    tombstone: bool
    modalities: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    embeddings: dict[str, EmbeddingRecord] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "object_id": self.object_id,
            "collection": self.collection,
            "version": self.version,
            "txn_id": self.txn_id,
            "commit_ts": self.commit_ts,
            "tombstone": self.tombstone,
            "modalities": self.modalities,
            "metadata": self.metadata,
            "embeddings": {
                name: {
                    "model": e.model,
                    "version": e.version,
                    "dims": e.dims,
                    "vector": e.vector,
                    "params": e.params,
                }
                for name, e in self.embeddings.items()
            },
        }

    @staticmethod
    def from_dict(d: dict[str, Any]) -> ObjectVersion:
        return ObjectVersion(
            object_id=d["object_id"],
            collection=d["collection"],
            version=d["version"],
            txn_id=d["txn_id"],
            commit_ts=d["commit_ts"],
            tombstone=d["tombstone"],
            modalities=d.get("modalities", {}),
            metadata=d.get("metadata", {}),
            embeddings={
                name: EmbeddingRecord(**e)
                for name, e in d.get("embeddings", {}).items()
            },
        )

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from neurodb_core.storage.records import EmbeddingRecord, ObjectVersion

_SCHEMA = pa.schema(
    [
        pa.field("object_id", pa.string()),
        pa.field("collection", pa.string()),
        pa.field("version", pa.int64()),
        pa.field("txn_id", pa.int64()),
        pa.field("commit_ts", pa.float64()),
        pa.field("tombstone", pa.bool_()),
        pa.field("modalities_json", pa.string()),
        pa.field("metadata_json", pa.string()),
        pa.field("embeddings_json", pa.string()),
    ]
)


def write_segment(directory: Path, versions: list[ObjectVersion]) -> dict:
    """Flushes a batch of committed object versions into an immutable
    Parquet segment (columnar, at-rest storage) and returns catalog metadata
    describing it.
    """
    directory.mkdir(parents=True, exist_ok=True)
    segment_id = f"seg_{uuid.uuid4().hex}"
    file_path = directory / f"{segment_id}.parquet"

    columns: dict[str, list] = {name: [] for name in _SCHEMA.names}
    collections: set[str] = set()
    for ov in versions:
        columns["object_id"].append(ov.object_id)
        columns["collection"].append(ov.collection)
        columns["version"].append(ov.version)
        columns["txn_id"].append(ov.txn_id)
        columns["commit_ts"].append(ov.commit_ts)
        columns["tombstone"].append(ov.tombstone)
        columns["modalities_json"].append(json.dumps(ov.modalities))
        columns["metadata_json"].append(json.dumps(ov.metadata))
        columns["embeddings_json"].append(
            json.dumps(
                {
                    name: {
                        "model": e.model,
                        "version": e.version,
                        "dims": e.dims,
                        "vector": e.vector,
                        "params": e.params,
                    }
                    for name, e in ov.embeddings.items()
                }
            )
        )
        collections.add(ov.collection)

    table = pa.table(columns, schema=_SCHEMA)
    pq.write_table(table, file_path, compression="snappy")

    return {
        "segment_id": segment_id,
        "file": file_path.name,
        "row_count": len(versions),
        "collections": sorted(collections),
        "created_at": time.time(),
    }


def read_segment(directory: Path, segment_meta: dict) -> list[ObjectVersion]:
    file_path = directory / segment_meta["file"]
    table = pq.read_table(file_path)
    out: list[ObjectVersion] = []
    for row in table.to_pylist():
        embeddings = {
            name: EmbeddingRecord(**e)
            for name, e in json.loads(row["embeddings_json"]).items()
        }
        out.append(
            ObjectVersion(
                object_id=row["object_id"],
                collection=row["collection"],
                version=row["version"],
                txn_id=row["txn_id"],
                commit_ts=row["commit_ts"],
                tombstone=row["tombstone"],
                modalities=json.loads(row["modalities_json"]),
                metadata=json.loads(row["metadata_json"]),
                embeddings=embeddings,
            )
        )
    return out

from pathlib import Path

from neurodb_core.storage import EmbeddingRecord, StorageEngine


def make_engine(tmp_path: Path) -> StorageEngine:
    return StorageEngine(tmp_path / "proj")


def test_put_and_get_roundtrip(tmp_path):
    engine = make_engine(tmp_path)
    ov = engine.put(
        "docs",
        metadata={"title": "hello"},
        modalities={"text": "hello world"},
        embeddings={"text": EmbeddingRecord(model="neurodb-lite", version=1, dims=4, vector=[0.1, 0.2, 0.3, 0.4])},
    )
    fetched = engine.get(ov.object_id)
    assert fetched is not None
    assert fetched.metadata["title"] == "hello"
    assert fetched.embeddings["text"].vector == [0.1, 0.2, 0.3, 0.4]
    assert fetched.version == 1


def test_update_creates_new_version_and_as_of_works(tmp_path):
    engine = make_engine(tmp_path)
    v1 = engine.put("docs", metadata={"title": "v1"})
    v2 = engine.put("docs", object_id=v1.object_id, metadata={"title": "v2"})
    assert v2.version == 2

    latest = engine.get(v1.object_id)
    assert latest.metadata["title"] == "v2"

    old = engine.get(v1.object_id, as_of_version=1)
    assert old.metadata["title"] == "v1"


def test_delete_tombstones_object(tmp_path):
    engine = make_engine(tmp_path)
    ov = engine.put("docs", metadata={"title": "temp"})
    engine.delete(ov.object_id)
    assert engine.get(ov.object_id) is None
    # but the pre-delete version is still recoverable via time travel
    assert engine.get(ov.object_id, as_of_version=1) is not None


def test_scan_returns_all_live_objects_in_collection(tmp_path):
    engine = make_engine(tmp_path)
    ids = [engine.put("docs", metadata={"i": i}).object_id for i in range(5)]
    engine.delete(ids[0])
    results = engine.scan("docs")
    assert len(results) == 4
    assert {r.object_id for r in results} == set(ids[1:])


def test_flush_persists_to_parquet_segment_and_survives_restart(tmp_path):
    root = tmp_path / "proj"
    engine = StorageEngine(root)
    ov = engine.put("docs", metadata={"title": "persisted"})
    engine.flush()
    engine.close()

    assert (root / "catalog.json").exists()
    segments = list((root / "segments").glob("*.parquet"))
    assert len(segments) == 1

    reopened = StorageEngine(root)
    fetched = reopened.get(ov.object_id)
    assert fetched is not None
    assert fetched.metadata["title"] == "persisted"


def test_wal_replay_recovers_unflushed_writes_after_crash(tmp_path):
    root = tmp_path / "proj"
    engine = StorageEngine(root)
    ov = engine.put("docs", metadata={"title": "unflushed"})
    engine.wal._fh.close()  # simulate crash: no flush(), no clean close()

    recovered = StorageEngine(root)
    fetched = recovered.get(ov.object_id)
    assert fetched is not None
    assert fetched.metadata["title"] == "unflushed"


def test_auto_flush_triggers_after_threshold(tmp_path, monkeypatch):
    import neurodb_core.storage.storage_engine as se_module

    monkeypatch.setattr(se_module, "FLUSH_THRESHOLD", 3)
    engine = StorageEngine(tmp_path / "proj")
    for i in range(3):
        engine.put("docs", metadata={"i": i})
    segments = list((tmp_path / "proj" / "segments").glob("*.parquet"))
    assert len(segments) == 1

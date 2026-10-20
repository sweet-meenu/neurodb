from neurodb_core.index.manager import IndexManager
from neurodb_core.lifecycle.reembed import ReembedJob
from neurodb_core.lifecycle.versioning import EmbeddingVersionRegistry
from neurodb_core.nlp.embedding import encode_as_embedding_record
from neurodb_core.storage.records import EmbeddingRecord
from neurodb_core.storage.storage_engine import StorageEngine


def setup_stale_collection(tmp_path, n=12):
    storage = StorageEngine(tmp_path / "proj")
    index_manager = IndexManager()
    for i in range(n):
        text = f"document number {i} about databases and vectors"
        old_vec = [0.0] * 8
        old_vec[i % 8] = 1.0
        ov = storage.put(
            "docs",
            modalities={"text": text},
            metadata={"i": i},
            embeddings={"text": EmbeddingRecord(model="old-model", version=1, dims=8, vector=old_vec)},
        )
        index_manager.add("docs", "text", ov.object_id, old_vec)
    return storage, index_manager


def test_reembed_migration_updates_all_objects_and_index(tmp_path):
    storage, index_manager = setup_stale_collection(tmp_path, n=12)
    registry = EmbeddingVersionRegistry()
    job = ReembedJob(storage, index_manager, registry)

    progress = job.start_migration("docs", "text", "neurodb-lite-encoder", 1, target_dims=256)
    assert progress.total == 12
    assert not progress.done

    while not progress.done:
        progress = job.run_batch("docs", "text", encode_as_embedding_record, batch_size=5)

    assert progress.migrated == 12
    assert progress.fraction_complete == 1.0

    for ov in storage.scan("docs"):
        emb = ov.embeddings["text"]
        assert emb.model == "neurodb-lite-encoder"
        assert emb.version == 1
        assert len(emb.vector) == 256

    current = registry.current("docs", "text")
    assert current is not None
    assert current.model == "neurodb-lite-encoder"

    query_vec = encode_as_embedding_record("document number 3 about databases and vectors").vector
    results = index_manager.search("docs", "text", query_vec, k=3)
    assert len(results) == 3


def test_reembed_migration_progress_is_gradual_with_no_downtime(tmp_path):
    storage, index_manager = setup_stale_collection(tmp_path, n=10)
    registry = EmbeddingVersionRegistry()
    job = ReembedJob(storage, index_manager, registry)
    job.start_migration("docs", "text", "neurodb-lite-encoder", 1, target_dims=256)

    progress = job.run_batch("docs", "text", encode_as_embedding_record, batch_size=4)
    assert progress.migrated == 4
    assert 0 < progress.fraction_complete < 1
    # registry should not flip to the new model until migration fully completes
    assert registry.current("docs", "text") is None
    # and the live index keeps serving the old (8-dim) model uninterrupted mid-migration
    old_query = [0.0] * 8
    old_query[0] = 1.0
    results = index_manager.search("docs", "text", old_query, k=3)
    assert len(results) == 3

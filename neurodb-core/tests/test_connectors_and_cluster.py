from pathlib import Path

from neurodb_core.cluster.node import ShardMap, SingleNodeCluster
from neurodb_core.connectors.datalake import LocalDataLakeConnector
from neurodb_core.index.manager import IndexManager
from neurodb_core.nlp.embedding import encode
from neurodb_core.storage.storage_engine import StorageEngine


def test_local_datalake_connector_ingests_directory_in_place(tmp_path):
    lake_dir = tmp_path / "lake"
    lake_dir.mkdir()
    (lake_dir / "a.txt").write_text(
        "NeuroDB indexes documents directly from a data lake. It supports semantic search.",
        encoding="utf-8",
    )
    (lake_dir / "b.md").write_text("# Notes\nThis file has unrelated markdown content about cooking.", encoding="utf-8")
    (lake_dir / "ignore.bin").write_bytes(b"\x00\x01\x02")

    storage = StorageEngine(tmp_path / "proj")
    index_manager = IndexManager()
    connector = LocalDataLakeConnector(storage, index_manager)

    stats = connector.ingest_directory(lake_dir, collection="lake_docs")

    assert stats.files_scanned == 2  # .bin is skipped, unsupported extension
    assert stats.files_ingested == 2
    assert not stats.errors

    # original files must be untouched — no copying/moving out of the lake
    assert (lake_dir / "a.txt").exists()
    assert (lake_dir / "b.md").exists()

    rows = storage.scan("lake_docs")
    assert len(rows) == stats.chunks_created
    assert all(r.metadata["source_path"] for r in rows)

    query_vec = encode("semantic search over a data lake").vector
    results = index_manager.search("lake_docs", "text", query_vec, k=1)
    assert len(results) == 1


def test_local_datalake_connector_records_errors_without_aborting(tmp_path):
    lake_dir = tmp_path / "lake"
    lake_dir.mkdir()
    (lake_dir / "good.txt").write_text("A perfectly fine document about databases.", encoding="utf-8")
    bad_pdf = lake_dir / "bad.pdf"
    bad_pdf.write_bytes(b"not a real pdf")

    storage = StorageEngine(tmp_path / "proj")
    index_manager = IndexManager()
    connector = LocalDataLakeConnector(storage, index_manager)

    stats = connector.ingest_directory(lake_dir, collection="docs")
    assert stats.files_scanned == 2
    assert stats.files_ingested == 1
    assert len(stats.errors) == 1
    assert "bad.pdf" in stats.errors[0]


def test_single_node_cluster_is_leader_for_registered_shards():
    cluster = SingleNodeCluster(node_id="node-a")
    cluster.register_shard("shard-1")
    assert cluster.is_leader_for("shard-1")
    assert not cluster.is_leader_for("shard-2")
    assert cluster.node_id == "node-a"
    assert len(cluster.shards()) == 1


def test_shard_map_assigns_project_to_a_shard():
    cluster = SingleNodeCluster()
    shard_map = ShardMap(cluster)
    shard_id = shard_map.shard_for("project-123")
    cluster.register_shard(shard_id)
    assert cluster.is_leader_for(shard_id)

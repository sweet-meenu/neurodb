import numpy as np
import pytest

from neurodb_core.index.flat import FlatIndex
from neurodb_core.index.hnsw import HNSWIndex
from neurodb_core.index.manager import CollectionIndex, IndexManager


def random_unit_vectors(n: int, dims: int, seed: int = 0) -> list[np.ndarray]:
    rng = np.random.default_rng(seed)
    vecs = rng.normal(size=(n, dims))
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    return list(vecs)


def test_flat_index_finds_exact_nearest_neighbor():
    index = FlatIndex(dims=4)
    index.add("a", [1.0, 0.0, 0.0, 0.0])
    index.add("b", [0.0, 1.0, 0.0, 0.0])
    index.add("c", [0.9, 0.1, 0.0, 0.0])
    results = index.search([1.0, 0.0, 0.0, 0.0], k=2)
    assert results[0][0] == "a"
    assert results[1][0] == "c"


def test_flat_index_remove():
    index = FlatIndex(dims=2)
    index.add("a", [1.0, 0.0])
    index.add("b", [0.0, 1.0])
    index.remove("a")
    assert len(index) == 1
    results = index.search([1.0, 0.0], k=5)
    assert results[0][0] == "b"


def test_hnsw_matches_flat_on_small_exact_case():
    vectors = random_unit_vectors(50, 16, seed=1)
    flat = FlatIndex(dims=16)
    hnsw = HNSWIndex(dims=16)
    for i, v in enumerate(vectors):
        flat.add(str(i), v)
        hnsw.add(str(i), v)

    query = vectors[3]
    flat_top = [id_ for id_, _ in flat.search(query, k=5)]
    hnsw_top = [id_ for id_, _ in hnsw.search(query, k=5)]
    assert flat_top[0] == hnsw_top[0] == "3"  # exact self-match must win


def test_hnsw_recall_against_flat_baseline():
    n, dims, k = 400, 32, 10
    vectors = random_unit_vectors(n, dims, seed=42)
    flat = FlatIndex(dims=dims)
    hnsw = HNSWIndex(dims=dims, ef_construction=200)
    for i, v in enumerate(vectors):
        flat.add(str(i), v)
        hnsw.add(str(i), v)

    queries = random_unit_vectors(20, dims, seed=99)
    total_recall = 0.0
    for q in queries:
        ground_truth = {id_ for id_, _ in flat.search(q, k=k)}
        approx = {id_ for id_, _ in hnsw.search(q, k=k, ef=100)}
        total_recall += len(ground_truth & approx) / k
    avg_recall = total_recall / len(queries)
    assert avg_recall >= 0.85, f"HNSW recall too low: {avg_recall}"


def test_hnsw_remove_updates_graph():
    vectors = random_unit_vectors(30, 8, seed=2)
    hnsw = HNSWIndex(dims=8)
    for i, v in enumerate(vectors):
        hnsw.add(str(i), v)
    hnsw.remove("5")
    assert len(hnsw) == 29
    results = hnsw.search(vectors[5], k=30)
    assert "5" not in [id_ for id_, _ in results]


def test_collection_index_promotes_to_hnsw_past_threshold():
    index = CollectionIndex(dims=8, threshold=10)
    vectors = random_unit_vectors(15, 8, seed=3)
    for i, v in enumerate(vectors):
        index.add(str(i), v.tolist())
    assert index.kind == "hnsw"
    assert len(index) == 15


def test_collection_index_stays_flat_below_threshold():
    index = CollectionIndex(dims=8, threshold=100)
    vectors = random_unit_vectors(15, 8, seed=4)
    for i, v in enumerate(vectors):
        index.add(str(i), v.tolist())
    assert index.kind == "flat"


def test_index_manager_isolates_by_collection_and_field():
    manager = IndexManager()
    manager.add("docs", "text_embedding", "1", [1.0, 0.0])
    manager.add("images", "image_embedding", "1", [0.0, 1.0])

    docs_results = manager.search("docs", "text_embedding", [1.0, 0.0], k=1)
    assert docs_results[0][0] == "1"

    empty = manager.search("docs", "image_embedding", [1.0, 0.0], k=1)
    assert empty == []

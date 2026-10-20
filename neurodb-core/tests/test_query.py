import pytest

from neurodb_core.index.manager import IndexManager
from neurodb_core.nlp.embedding import encode, encode_as_embedding_record
from neurodb_core.query.neuroql.ast_nodes import BinaryOp, Identifier, Literal
from neurodb_core.query.neuroql.executor import QueryExecutor
from neurodb_core.query.neuroql.optimizer import plan_query
from neurodb_core.query.neuroql.parser import ParseError, parse
from neurodb_core.query.neuroql.planner import build_logical_plan
from neurodb_core.storage.records import EmbeddingRecord
from neurodb_core.storage.storage_engine import StorageEngine


def test_parse_simple_select():
    stmt = parse("SELECT * FROM docs LIMIT 5")
    assert stmt.select_list == ["*"]
    assert stmt.collection == "docs"
    assert stmt.limit == 5


def test_parse_where_clause_precedence():
    stmt = parse("SELECT * FROM docs WHERE category = 'ai' AND (score > 3 OR featured = TRUE)")
    assert isinstance(stmt.where, BinaryOp)
    assert stmt.where.op == "AND"
    assert isinstance(stmt.where.left, BinaryOp)
    assert stmt.where.left.op == "="


def test_parse_semantic_and_as_of_and_order_by():
    stmt = parse(
        "SELECT * FROM docs SEMANTIC SIMILAR TO 'vector search' USING embedding "
        "AS OF VERSION 3 ORDER BY score DESC LIMIT 10"
    )
    assert stmt.semantic.text == "vector search"
    assert stmt.semantic.field == "embedding"
    assert stmt.as_of.kind == "version"
    assert stmt.as_of.value == 3
    assert stmt.order_by.field == "score"
    assert stmt.order_by.descending is True


def test_parse_error_on_malformed_query():
    with pytest.raises(ParseError):
        parse("SELECT FROM docs")


def test_parse_tolerates_trailing_semicolon():
    stmt = parse("SELECT * FROM docs SEMANTIC SIMILAR TO 'neural';")
    assert stmt.collection == "docs"
    assert stmt.semantic.text == "neural"

    stmt = parse("  SELECT * FROM docs;  ")
    assert stmt.collection == "docs"


def test_optimizer_picks_scan_filter_without_semantic():
    stmt = parse("SELECT * FROM docs WHERE category = 'ai'")
    logical = build_logical_plan(stmt)
    plan = plan_query(logical, collection_size=1000)
    assert plan.strategy == "scan_filter"


def test_optimizer_picks_filter_first_for_selective_filter_on_small_collection():
    stmt = parse("SELECT * FROM docs WHERE category = 'ai' SEMANTIC SIMILAR TO 'hello'")
    logical = build_logical_plan(stmt)
    plan = plan_query(logical, collection_size=500)
    assert plan.strategy == "filter_first"


def test_optimizer_picks_semantic_first_without_filter():
    stmt = parse("SELECT * FROM docs SEMANTIC SIMILAR TO 'hello'")
    logical = build_logical_plan(stmt)
    plan = plan_query(logical, collection_size=100000)
    assert plan.strategy == "semantic_first"


def _seed_storage(tmp_path):
    storage = StorageEngine(tmp_path / "proj")
    index_manager = IndexManager()
    docs = [
        ("NeuroDB is a vector database for semantic search.", "engineering"),
        ("The quarterly earnings report beat market expectations.", "finance"),
        ("A new HNSW index accelerates approximate nearest neighbor search.", "engineering"),
        ("The football championship game had a record audience.", "sports"),
    ]
    for text, category in docs:
        emb = encode_as_embedding_record(text)
        ov = storage.put(
            "docs",
            modalities={"text": text},
            metadata={"category": category},
            embeddings={"text": emb},
        )
        index_manager.add("docs", "text", ov.object_id, emb.vector)
    return storage, index_manager


def test_executor_scan_filter(tmp_path):
    storage, index_manager = _seed_storage(tmp_path)
    executor = QueryExecutor(storage, index_manager, lambda t: encode(t).vector)
    stmt = parse("SELECT * FROM docs WHERE category = 'engineering'")
    results, plan = executor.execute(stmt)
    assert plan.strategy == "scan_filter"
    assert len(results) == 2
    assert all(r.object_version.metadata["category"] == "engineering" for r in results)


def test_executor_semantic_search_ranks_relevant_doc_first(tmp_path):
    storage, index_manager = _seed_storage(tmp_path)
    executor = QueryExecutor(storage, index_manager, lambda t: encode(t).vector)
    stmt = parse("SELECT * FROM docs SEMANTIC SIMILAR TO 'vector database semantic search' LIMIT 2")
    results, plan = executor.execute(stmt)
    assert len(results) == 2
    assert "vector database" in results[0].object_version.modalities["text"]
    assert results[0].explanation is not None
    assert results[0].score is not None and results[0].score > 0


def test_executor_semantic_with_filter_returns_only_matching_category(tmp_path):
    storage, index_manager = _seed_storage(tmp_path)
    executor = QueryExecutor(storage, index_manager, lambda t: encode(t).vector)
    stmt = parse("SELECT * FROM docs WHERE category = 'sports' SEMANTIC SIMILAR TO 'search index'")
    results, plan = executor.execute(stmt)
    assert all(r.object_version.metadata["category"] == "sports" for r in results)


def test_executor_as_of_version_time_travel(tmp_path):
    storage = StorageEngine(tmp_path / "proj")
    index_manager = IndexManager()
    ov1 = storage.put("docs", modalities={"text": "v1"}, metadata={"title": "v1"})
    storage.put("docs", object_id=ov1.object_id, modalities={"text": "v2"}, metadata={"title": "v2"})

    executor = QueryExecutor(storage, index_manager, lambda t: encode(t).vector)
    stmt = parse("SELECT * FROM docs AS OF VERSION 1")
    results, _ = executor.execute(stmt)
    assert len(results) == 1
    assert results[0].object_version.metadata["title"] == "v1"

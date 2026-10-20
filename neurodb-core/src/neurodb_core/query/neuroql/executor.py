from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

import numpy as np

from neurodb_core.index.manager import IndexManager
from neurodb_core.query.neuroql.ast_nodes import SelectStmt
from neurodb_core.query.neuroql.explain import Explanation, build_explanation
from neurodb_core.query.neuroql.optimizer import PhysicalPlan, plan_query
from neurodb_core.query.neuroql.planner import LogicalPlan, build_logical_plan
from neurodb_core.query.neuroql.predicate import eval_expr, resolve_field
from neurodb_core.storage.records import ObjectVersion
from neurodb_core.storage.storage_engine import StorageEngine


@dataclass
class QueryResult:
    object_version: ObjectVersion
    score: float | None
    explanation: Explanation | None


def _resolve_as_of_ts(logical: LogicalPlan) -> float | None:
    if logical.as_of_timestamp is None:
        return None
    try:
        return datetime.fromisoformat(logical.as_of_timestamp).timestamp()
    except ValueError:
        return float(logical.as_of_timestamp)


def _normalize(vector) -> np.ndarray:
    v = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(v)
    return v / norm if norm > 0 else v


class QueryExecutor:
    """Executes a NeuroQL physical plan against the storage engine and index
    manager: plain metadata scans, exact filter-then-brute-force semantic
    search, or ANN-search-then-filter — whichever the optimizer picked.
    """

    def __init__(
        self,
        storage: StorageEngine,
        index_manager: IndexManager,
        encode_fn: Callable[[str], list[float]],
    ):
        self.storage = storage
        self.index_manager = index_manager
        self.encode_fn = encode_fn

    def execute(self, stmt: SelectStmt) -> tuple[list[QueryResult], PhysicalPlan]:
        logical = build_logical_plan(stmt)
        as_of_ts = _resolve_as_of_ts(logical)

        collection_size = len(
            self.storage.scan(logical.collection, as_of_version=logical.as_of_version, as_of_ts=as_of_ts)
        )
        plan = plan_query(logical, collection_size=collection_size)

        if plan.strategy == "scan_filter":
            results = self._run_scan_filter(logical, as_of_ts)
        elif plan.strategy == "filter_first":
            results = self._run_filter_first(logical, as_of_ts)
        else:
            results = self._run_semantic_first(logical, plan, as_of_ts)

        if logical.order_by:
            field = logical.order_by.field
            results.sort(
                key=lambda r: (resolve_field(field, r.object_version) is None, resolve_field(field, r.object_version)),
                reverse=logical.order_by.descending,
            )
        elif logical.semantic:
            results.sort(key=lambda r: r.score or 0.0, reverse=True)

        if logical.limit is not None:
            results = results[: logical.limit]
        return results, plan

    def _run_scan_filter(self, logical: LogicalPlan, as_of_ts: float | None) -> list[QueryResult]:
        rows = self.storage.scan(logical.collection, as_of_version=logical.as_of_version, as_of_ts=as_of_ts)
        matched = [r for r in rows if logical.where is None or eval_expr(logical.where, r)]
        return [QueryResult(object_version=r, score=None, explanation=None) for r in matched]

    def _run_filter_first(self, logical: LogicalPlan, as_of_ts: float | None) -> list[QueryResult]:
        rows = self.storage.scan(logical.collection, as_of_version=logical.as_of_version, as_of_ts=as_of_ts)
        matched = [r for r in rows if logical.where is None or eval_expr(logical.where, r)]

        assert logical.semantic is not None
        query_vec = _normalize(self.encode_fn(logical.semantic.text))

        results = []
        for r in matched:
            emb = r.embeddings.get(logical.semantic.field)
            if emb is None:
                continue
            score = float(np.dot(query_vec, _normalize(emb.vector)))
            explanation = build_explanation(logical.semantic.text, r, score, field=logical.semantic.field)
            results.append(QueryResult(object_version=r, score=score, explanation=explanation))
        return results

    def _run_semantic_first(
        self, logical: LogicalPlan, plan: PhysicalPlan, as_of_ts: float | None
    ) -> list[QueryResult]:
        assert logical.semantic is not None
        query_vec = self.encode_fn(logical.semantic.text)
        k = max((logical.limit or 10) * 5, 20)  # over-fetch: a post-filter may drop some hits
        hits = self.index_manager.search(logical.collection, logical.semantic.field, query_vec, k=k)

        results = []
        for object_id, score in hits:
            ov = self.storage.get(object_id, as_of_version=logical.as_of_version, as_of_ts=as_of_ts)
            if ov is None:
                continue
            if logical.where is not None and not eval_expr(logical.where, ov):
                continue
            explanation = build_explanation(logical.semantic.text, ov, score, field=logical.semantic.field)
            results.append(QueryResult(object_version=ov, score=score, explanation=explanation))
        return results

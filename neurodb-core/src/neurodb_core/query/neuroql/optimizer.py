from __future__ import annotations

import math
from dataclasses import dataclass

from neurodb_core.query.neuroql.ast_nodes import BinaryOp, Expr, Identifier, Literal, UnaryOp
from neurodb_core.query.neuroql.planner import LogicalPlan


@dataclass
class PhysicalPlan:
    logical: LogicalPlan
    strategy: str  # "scan_filter" | "filter_first" | "semantic_first"
    estimated_candidates: int
    ef: int | None = None


def _estimate_selectivity(expr: Expr | None) -> float:
    """Crude, dependency-free selectivity model: equality predicates are
    assumed highly selective, range comparisons moderately so, ANDs multiply
    (independence assumption), ORs union, NOT inverts. Good enough to make a
    real strategy choice without needing collected column statistics.
    """
    if expr is None:
        return 1.0
    if isinstance(expr, (Literal, Identifier)):
        return 1.0
    if isinstance(expr, UnaryOp):
        return 1.0 - _estimate_selectivity(expr.operand)
    if isinstance(expr, BinaryOp):
        if expr.op == "AND":
            return _estimate_selectivity(expr.left) * _estimate_selectivity(expr.right)
        if expr.op == "OR":
            left, right = _estimate_selectivity(expr.left), _estimate_selectivity(expr.right)
            return min(1.0, left + right - left * right)
        if expr.op == "=":
            return 0.1
        if expr.op == "!=":
            return 0.9
        if expr.op in ("<", "<=", ">", ">="):
            return 0.3
    return 0.5


def plan_query(logical: LogicalPlan, *, collection_size: int) -> PhysicalPlan:
    """Cost-based execution strategy selection, analogous to cost-based
    optimization in relational databases: estimate WHERE-clause selectivity,
    then weigh scanning + exact-filtering the whole collection against
    ANN-searching the index and filtering the (small) result set after.
    """
    selectivity = _estimate_selectivity(logical.where)
    estimated_candidates = max(1, math.ceil(collection_size * selectivity))

    if logical.semantic is None:
        return PhysicalPlan(logical=logical, strategy="scan_filter", estimated_candidates=estimated_candidates)

    # filter_first: scan+filter (O(N) exact) then brute-force cosine among the
    # (small) surviving candidates — exact, and cheap when the filter is
    # selective enough that N + candidates stays small.
    filter_first_cost = collection_size + estimated_candidates
    # semantic_first: ANN search the whole index (~log N) then filter the
    # top-k*oversample results — cheap regardless of collection size, but
    # approximate and wasteful when a selective filter could have shrunk the
    # search space first.
    ann_cost = math.log2(max(collection_size, 2)) * 50
    semantic_first_cost = ann_cost + (logical.limit or 10)

    candidate_cap = max(2000, int(0.05 * collection_size))
    prefer_filter_first = (
        logical.where is not None
        and estimated_candidates <= candidate_cap
        and filter_first_cost < semantic_first_cost * 4
    )
    if prefer_filter_first:
        return PhysicalPlan(logical=logical, strategy="filter_first", estimated_candidates=estimated_candidates)

    ef = max(100, (logical.limit or 10) * 10)
    return PhysicalPlan(
        logical=logical, strategy="semantic_first", estimated_candidates=estimated_candidates, ef=ef
    )

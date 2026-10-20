from __future__ import annotations

from dataclasses import dataclass

from neurodb_core.query.neuroql.ast_nodes import Expr, OrderBy, SelectStmt, SemanticClause


@dataclass
class LogicalPlan:
    """Normalized, engine-facing representation of a parsed NeuroQL query.
    For the current grammar this is a direct carry-over from the AST — kept
    as its own stage so future NeuroQL features (joins, aggregations) have a
    natural place to do real rewriting without touching the optimizer.
    """

    select_list: list[str]
    collection: str
    where: Expr | None
    semantic: SemanticClause | None
    as_of_version: int | None
    as_of_timestamp: str | None
    order_by: OrderBy | None
    limit: int | None


def build_logical_plan(stmt: SelectStmt) -> LogicalPlan:
    as_of_version = stmt.as_of.value if stmt.as_of and stmt.as_of.kind == "version" else None
    as_of_timestamp = stmt.as_of.value if stmt.as_of and stmt.as_of.kind == "timestamp" else None
    return LogicalPlan(
        select_list=stmt.select_list,
        collection=stmt.collection,
        where=stmt.where,
        semantic=stmt.semantic,
        as_of_version=as_of_version,
        as_of_timestamp=as_of_timestamp,
        order_by=stmt.order_by,
        limit=stmt.limit,
    )

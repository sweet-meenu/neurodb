from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Union


@dataclass
class Literal:
    value: Any


@dataclass
class Identifier:
    name: str


@dataclass
class BinaryOp:
    op: str  # "=", "!=", "<", "<=", ">", ">=", "AND", "OR"
    left: "Expr"
    right: "Expr"


@dataclass
class UnaryOp:
    op: str  # "NOT"
    operand: "Expr"


Expr = Union[Literal, Identifier, BinaryOp, UnaryOp]


@dataclass
class SemanticClause:
    text: str
    field: str = "text"


@dataclass
class AsOf:
    kind: str  # "version" | "timestamp"
    value: Any


@dataclass
class OrderBy:
    field: str
    descending: bool = False


@dataclass
class SelectStmt:
    select_list: list[str]
    collection: str
    where: Expr | None = None
    semantic: SemanticClause | None = None
    as_of: AsOf | None = None
    order_by: OrderBy | None = None
    limit: int | None = None

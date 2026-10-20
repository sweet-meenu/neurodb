from __future__ import annotations

from typing import Any

from neurodb_core.query.neuroql.ast_nodes import BinaryOp, Expr, Identifier, Literal, UnaryOp
from neurodb_core.storage.records import ObjectVersion

_BUILTIN_FIELDS = {"object_id", "id", "version", "collection", "txn_id", "commit_ts"}


def resolve_field(name: str, ov: ObjectVersion) -> Any:
    if name in ("object_id", "id"):
        return ov.object_id
    if name in _BUILTIN_FIELDS:
        return getattr(ov, name)
    if name.startswith("metadata."):
        return ov.metadata.get(name[len("metadata."):])
    return ov.metadata.get(name)


def eval_expr(expr: Expr, ov: ObjectVersion) -> Any:
    if isinstance(expr, Literal):
        return expr.value
    if isinstance(expr, Identifier):
        return resolve_field(expr.name, ov)
    if isinstance(expr, UnaryOp):
        return not eval_expr(expr.operand, ov)
    if isinstance(expr, BinaryOp):
        if expr.op == "AND":
            return bool(eval_expr(expr.left, ov)) and bool(eval_expr(expr.right, ov))
        if expr.op == "OR":
            return bool(eval_expr(expr.left, ov)) or bool(eval_expr(expr.right, ov))
        left = eval_expr(expr.left, ov)
        right = eval_expr(expr.right, ov)
        try:
            if expr.op == "=":
                return left == right
            if expr.op == "!=":
                return left != right
            if expr.op == "<":
                return left < right
            if expr.op == "<=":
                return left <= right
            if expr.op == ">":
                return left > right
            if expr.op == ">=":
                return left >= right
        except TypeError:
            return False
    raise ValueError(f"cannot evaluate expression node {expr!r}")

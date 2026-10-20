from __future__ import annotations

from neurodb_core.query.neuroql.ast_nodes import (
    AsOf,
    BinaryOp,
    Expr,
    Identifier,
    Literal,
    OrderBy,
    SelectStmt,
    SemanticClause,
    UnaryOp,
)
from neurodb_core.query.neuroql.lexer import Token, TokType, tokenize


class ParseError(Exception):
    pass


class Parser:
    """Hand-written recursive-descent parser for NeuroQL:

        SELECT <* | field, ...>
        FROM <collection>
        [WHERE <predicate>]
        [SEMANTIC SIMILAR TO '<text>' [USING <field>]]
        [AS OF VERSION <n> | AS OF TIMESTAMP '<iso8601>']
        [ORDER BY <field> [ASC|DESC]]
        [LIMIT <n>]
    """

    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    def _peek(self) -> Token:
        return self.tokens[self.pos]

    def _advance(self) -> Token:
        tok = self.tokens[self.pos]
        self.pos += 1
        return tok

    def _expect_keyword(self, kw: str) -> Token:
        tok = self._peek()
        if tok.type == TokType.KEYWORD and tok.value == kw:
            return self._advance()
        raise ParseError(f"expected keyword {kw!r}, got {tok.value!r} at position {tok.pos}")

    def _check_keyword(self, kw: str) -> bool:
        tok = self._peek()
        return tok.type == TokType.KEYWORD and tok.value == kw

    def parse(self) -> SelectStmt:
        stmt = self.parse_select()
        if self._peek().type != TokType.EOF:
            raise ParseError(f"unexpected trailing input at position {self._peek().pos}")
        return stmt

    def parse_select(self) -> SelectStmt:
        self._expect_keyword("SELECT")
        select_list = self._parse_select_list()
        self._expect_keyword("FROM")
        collection_tok = self._advance()
        if collection_tok.type != TokType.IDENT:
            raise ParseError(f"expected collection name at position {collection_tok.pos}")
        collection = collection_tok.value

        where: Expr | None = None
        semantic: SemanticClause | None = None
        as_of: AsOf | None = None
        order_by: OrderBy | None = None
        limit: int | None = None

        if self._check_keyword("WHERE"):
            self._advance()
            where = self._parse_or_expr()
        if self._check_keyword("SEMANTIC"):
            semantic = self._parse_semantic_clause()
        if self._check_keyword("AS"):
            as_of = self._parse_as_of_clause()
        if self._check_keyword("ORDER"):
            order_by = self._parse_order_by_clause()
        if self._check_keyword("LIMIT"):
            self._advance()
            limit_tok = self._advance()
            if limit_tok.type != TokType.NUMBER:
                raise ParseError(f"expected number after LIMIT at position {limit_tok.pos}")
            limit = int(float(limit_tok.value))

        return SelectStmt(
            select_list=select_list,
            collection=collection,
            where=where,
            semantic=semantic,
            as_of=as_of,
            order_by=order_by,
            limit=limit,
        )

    def _parse_select_list(self) -> list[str]:
        if self._peek().type == TokType.STAR:
            self._advance()
            return ["*"]
        fields = []
        while True:
            tok = self._advance()
            if tok.type != TokType.IDENT:
                raise ParseError(f"expected field name at position {tok.pos}")
            fields.append(tok.value)
            if self._peek().type == TokType.COMMA:
                self._advance()
                continue
            break
        return fields

    def _parse_or_expr(self) -> Expr:
        left = self._parse_and_expr()
        while self._check_keyword("OR"):
            self._advance()
            right = self._parse_and_expr()
            left = BinaryOp(op="OR", left=left, right=right)
        return left

    def _parse_and_expr(self) -> Expr:
        left = self._parse_not_expr()
        while self._check_keyword("AND"):
            self._advance()
            right = self._parse_not_expr()
            left = BinaryOp(op="AND", left=left, right=right)
        return left

    def _parse_not_expr(self) -> Expr:
        if self._check_keyword("NOT"):
            self._advance()
            return UnaryOp(op="NOT", operand=self._parse_not_expr())
        if self._peek().type == TokType.LPAREN:
            self._advance()
            expr = self._parse_or_expr()
            tok = self._advance()
            if tok.type != TokType.RPAREN:
                raise ParseError(f"expected ')' at position {tok.pos}")
            return expr
        return self._parse_comparison()

    def _parse_comparison(self) -> Expr:
        left = self._parse_operand()
        if self._peek().type == TokType.OP:
            op_tok = self._advance()
            right = self._parse_operand()
            return BinaryOp(op=op_tok.value, left=left, right=right)
        return left

    def _parse_operand(self) -> Expr:
        tok = self._advance()
        if tok.type == TokType.IDENT:
            return Identifier(name=tok.value)
        if tok.type == TokType.STRING:
            return Literal(value=tok.value)
        if tok.type == TokType.NUMBER:
            value = float(tok.value) if "." in tok.value else int(tok.value)
            return Literal(value=value)
        if tok.type == TokType.KEYWORD and tok.value in ("TRUE", "FALSE"):
            return Literal(value=tok.value == "TRUE")
        if tok.type == TokType.KEYWORD and tok.value == "NULL":
            return Literal(value=None)
        raise ParseError(f"unexpected token {tok.value!r} at position {tok.pos}")

    def _parse_semantic_clause(self) -> SemanticClause:
        self._expect_keyword("SEMANTIC")
        self._expect_keyword("SIMILAR")
        self._expect_keyword("TO")
        text_tok = self._advance()
        if text_tok.type != TokType.STRING:
            raise ParseError(f"expected string after SIMILAR TO at position {text_tok.pos}")
        field = "text"
        if self._check_keyword("USING"):
            self._advance()
            field_tok = self._advance()
            if field_tok.type != TokType.IDENT:
                raise ParseError(f"expected field name after USING at position {field_tok.pos}")
            field = field_tok.value
        return SemanticClause(text=text_tok.value, field=field)

    def _parse_as_of_clause(self) -> AsOf:
        self._expect_keyword("AS")
        self._expect_keyword("OF")
        if self._check_keyword("VERSION"):
            self._advance()
            tok = self._advance()
            if tok.type != TokType.NUMBER:
                raise ParseError(f"expected number after VERSION at position {tok.pos}")
            return AsOf(kind="version", value=int(float(tok.value)))
        if self._check_keyword("TIMESTAMP"):
            self._advance()
            tok = self._advance()
            if tok.type != TokType.STRING:
                raise ParseError(f"expected string after TIMESTAMP at position {tok.pos}")
            return AsOf(kind="timestamp", value=tok.value)
        tok = self._peek()
        raise ParseError(f"expected VERSION or TIMESTAMP after AS OF at position {tok.pos}")

    def _parse_order_by_clause(self) -> OrderBy:
        self._expect_keyword("ORDER")
        self._expect_keyword("BY")
        field_tok = self._advance()
        if field_tok.type != TokType.IDENT:
            raise ParseError(f"expected field name after ORDER BY at position {field_tok.pos}")
        descending = False
        if self._check_keyword("DESC"):
            self._advance()
            descending = True
        elif self._check_keyword("ASC"):
            self._advance()
        return OrderBy(field=field_tok.value, descending=descending)


def parse(source: str) -> SelectStmt:
    source = source.strip()
    if source.endswith(";"):  # tolerate a trailing semicolon, as in most SQL clients
        source = source[:-1]
    return Parser(tokenize(source)).parse()

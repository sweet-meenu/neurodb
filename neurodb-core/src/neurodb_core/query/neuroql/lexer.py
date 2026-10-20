from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class TokType(Enum):
    KEYWORD = auto()
    IDENT = auto()
    STRING = auto()
    NUMBER = auto()
    OP = auto()
    STAR = auto()
    COMMA = auto()
    LPAREN = auto()
    RPAREN = auto()
    EOF = auto()


KEYWORDS = {
    "SELECT", "FROM", "WHERE", "AND", "OR", "NOT",
    "SEMANTIC", "SIMILAR", "TO", "USING",
    "AS", "OF", "VERSION", "TIMESTAMP",
    "ORDER", "BY", "ASC", "DESC", "LIMIT",
    "TRUE", "FALSE", "NULL",
}

_OPS = ["<=", ">=", "!=", "=", "<", ">"]


@dataclass
class Token:
    type: TokType
    value: str
    pos: int


class LexError(Exception):
    pass


def tokenize(source: str) -> list[Token]:
    """Hand-written lexer for NeuroQL — no parser-generator library."""
    tokens: list[Token] = []
    i = 0
    n = len(source)
    while i < n:
        c = source[i]
        if c.isspace():
            i += 1
            continue

        if c == "'":
            j = i + 1
            buf: list[str] = []
            while j < n and source[j] != "'":
                if source[j] == "\\" and j + 1 < n:
                    buf.append(source[j + 1])
                    j += 2
                    continue
                buf.append(source[j])
                j += 1
            if j >= n:
                raise LexError(f"unterminated string literal at position {i}")
            tokens.append(Token(TokType.STRING, "".join(buf), i))
            i = j + 1
            continue

        if c.isdigit():
            j = i + 1
            while j < n and (source[j].isdigit() or source[j] == "."):
                j += 1
            tokens.append(Token(TokType.NUMBER, source[i:j], i))
            i = j
            continue

        if c.isalpha() or c == "_":
            j = i + 1
            while j < n and (source[j].isalnum() or source[j] in "_."):
                j += 1
            word = source[i:j]
            if word.upper() in KEYWORDS:
                tokens.append(Token(TokType.KEYWORD, word.upper(), i))
            else:
                tokens.append(Token(TokType.IDENT, word, i))
            i = j
            continue

        if c == "*":
            tokens.append(Token(TokType.STAR, c, i))
            i += 1
            continue
        if c == ",":
            tokens.append(Token(TokType.COMMA, c, i))
            i += 1
            continue
        if c == "(":
            tokens.append(Token(TokType.LPAREN, c, i))
            i += 1
            continue
        if c == ")":
            tokens.append(Token(TokType.RPAREN, c, i))
            i += 1
            continue

        matched_op = next((op for op in _OPS if source.startswith(op, i)), None)
        if matched_op:
            tokens.append(Token(TokType.OP, matched_op, i))
            i += len(matched_op)
            continue

        raise LexError(f"unexpected character {c!r} at position {i}")

    tokens.append(Token(TokType.EOF, "", n))
    return tokens

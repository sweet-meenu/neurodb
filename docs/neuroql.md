# NeuroQL

A SQL-like query language for metadata filters, semantic search, and time travel over a
NeuroDB collection. Implemented in `neurodb_core/query/neuroql/` as a hand-written lexer and
recursive-descent parser (no parser-generator library).

## Grammar

```
select_stmt   := SELECT select_list FROM collection
                 [WHERE predicate]
                 [SEMANTIC SIMILAR TO string [USING field]]
                 [AS OF (VERSION number | TIMESTAMP string)]
                 [ORDER BY field [ASC|DESC]]
                 [LIMIT number]

select_list   := '*' | field (',' field)*

predicate     := or_expr
or_expr       := and_expr (OR and_expr)*
and_expr      := not_expr (AND not_expr)*
not_expr      := NOT not_expr | '(' or_expr ')' | comparison
comparison    := operand [('=' | '!=' | '<' | '<=' | '>' | '>=') operand]
operand       := identifier | string | number | TRUE | FALSE | NULL
```

Strings are single-quoted (`'like this'`, with `\'` for an escaped quote). Identifiers may
contain dots (`metadata.title`) for nested access; bare identifiers resolve against object
metadata directly.

## Examples

Plain metadata filter (no vector search — a straight scan + filter):

```sql
SELECT * FROM docs WHERE category = 'engineering' AND priority >= 3
```

Semantic search:

```sql
SELECT * FROM support_tickets
SEMANTIC SIMILAR TO 'customer asking for a refund'
LIMIT 5
```

Hybrid — metadata filter narrows the candidate set, semantic search ranks within it (the
optimizer decides whether to filter first or search first; see below):

```sql
SELECT * FROM support_tickets
WHERE category = 'billing'
SEMANTIC SIMILAR TO 'customer asking for a refund'
ORDER BY score DESC
LIMIT 5
```

Search against a specific embedding field (an object can hold several):

```sql
SELECT * FROM products
SEMANTIC SIMILAR TO 'wireless noise-cancelling headphones'
USING image_embedding
```

Time travel — reconstruct a collection as it looked at a prior MVCC version or timestamp:

```sql
SELECT * FROM docs AS OF VERSION 12
SELECT * FROM docs AS OF TIMESTAMP '2026-06-01T00:00:00'
```

## Execution strategy

Every query with a `SEMANTIC SIMILAR TO` clause is planned by a small cost-based optimizer
(`optimizer.py`) before execution, choosing between:

| Strategy | When | How |
|---|---|---|
| `scan_filter` | no semantic clause | scan the collection, apply `WHERE`, sort/limit |
| `filter_first` | `WHERE` is selective enough | scan + filter exactly, then brute-force cosine search among the (small) survivors |
| `semantic_first` | `WHERE` is missing or not selective | ANN-search the index (HNSW if promoted, else flat), then filter the top-k results |

The response's `strategy` and `estimated_candidates` fields (also shown above the results
table in the dashboard's SQL editor) report which plan actually ran.

## Explainability

Every semantic-search result carries an `explanation`: the terms and entities the query and
the matched object's text share, any matched stored keyphrases, and a `confidence` score that
blends vector similarity with lexical term overlap. This is what "Why this match?" in the
dashboard surfaces.

## Not implemented in this grammar (yet)

Joins across collections, aggregations (`COUNT`, `GROUP BY`), and multi-column `ORDER BY` are
not part of the current grammar — see [`roadmap.md`](roadmap.md).

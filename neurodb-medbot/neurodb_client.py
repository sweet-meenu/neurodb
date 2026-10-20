"""Thin REST client for NeuroDB's API-key-authenticated data-plane API.

Talks to NeuroDB exactly the way any external application would: parses the
connection string shown once at project creation, then calls
/api/data/v1/... with the extracted API key. Zero dependency on
neurodb-core — this is a client, not an internal module.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import requests


@dataclass
class RetrievedChunk:
    text: str
    filename: str
    chunk_index: int | None
    score: float | None
    matched_terms: list[str] = field(default_factory=list)


def parse_connection_string(conn: str) -> tuple[str, str]:
    """neurodb://<project_id>:<api_key>@<host>:<port> -> (base_url, api_key)."""
    parts = urlsplit(conn)
    if parts.scheme != "neurodb" or not parts.password or not parts.hostname:
        raise ValueError(f"not a valid NeuroDB connection string: {conn!r}")
    base_url = f"http://{parts.hostname}:{parts.port}"
    return base_url, parts.password


def _escape_neuroql_string(text: str) -> str:
    """NeuroQL string literals are single-quoted with a generic backslash
    escape (see neurodb_core/query/neuroql/lexer.py: `\\X` -> literal `X`
    for any X) — so both backslashes and quotes in user text need escaping,
    backslashes first so the quote-escaping isn't itself re-escaped."""
    return text.replace("\\", "\\\\").replace("'", "\\'")


class NeuroDBError(RuntimeError):
    pass


class NeuroDBClient:
    def __init__(self, connection_string: str, *, timeout: float = 30.0):
        self.base_url, self.api_key = parse_connection_string(connection_string)
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {"X-NeuroDB-Api-Key": self.api_key}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        res = requests.request(method, f"{self.base_url}{path}", headers=self._headers(), timeout=self.timeout, **kwargs)
        if not res.ok:
            detail = res.text
            try:
                detail = res.json().get("detail", detail)
            except ValueError:
                pass
            raise NeuroDBError(f"{method} {path} -> {res.status_code}: {detail}")
        return res.json() if res.content else None

    def list_collections(self) -> list[dict[str, Any]]:
        return self._request("GET", "/api/data/v1/collections")

    def ingest_file(self, path: Path, *, collection: str) -> dict[str, Any]:
        with open(path, "rb") as fh:
            return self.ingest_bytes(fh.read(), filename=path.name, collection=collection)

    def ingest_bytes(self, data: bytes, *, filename: str, collection: str) -> dict[str, Any]:
        # Ingesting a whole book runs the full NLP pipeline over every chunk —
        # give it much longer than the default request timeout.
        res = requests.post(
            f"{self.base_url}/api/data/v1/ingest/file",
            headers=self._headers(),
            data={"collection": collection},
            files={"file": (filename, io.BytesIO(data))},
            timeout=max(self.timeout, 300.0),
        )
        if not res.ok:
            detail = res.text
            try:
                detail = res.json().get("detail", detail)
            except ValueError:
                pass
            raise NeuroDBError(f"ingest {filename} -> {res.status_code}: {detail}")
        return res.json()

    def semantic_search(self, collection: str, query_text: str, *, limit: int = 6) -> list[RetrievedChunk]:
        neuroql = f"SELECT * FROM {collection} SEMANTIC SIMILAR TO '{_escape_neuroql_string(query_text)}' LIMIT {limit};"
        payload = self._request("POST", "/api/data/v1/query", json={"query": neuroql})
        chunks = []
        for item in payload["results"]:
            metadata = item["metadata"]
            explanation = item.get("explanation") or {}
            chunks.append(
                RetrievedChunk(
                    text=item["modalities"].get("text", ""),
                    filename=str(metadata.get("filename") or "Pasted text"),
                    chunk_index=metadata.get("chunk_index"),
                    score=item.get("score"),
                    matched_terms=explanation.get("matched_terms", []),
                )
            )
        return chunks

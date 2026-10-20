from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class IngestObjectRequest(BaseModel):
    collection: str
    text: str
    metadata: dict[str, Any] = {}


class IngestObjectResponse(BaseModel):
    object_id: str
    version: int


class IngestFileResponse(BaseModel):
    object_ids: list[str]
    chunks_created: int


class QueryRequest(BaseModel):
    query: str


class ExplanationResponse(BaseModel):
    similarity: float
    confidence: float
    matched_terms: list[str]
    matched_entities: list[str]
    matched_keyphrases: list[str]
    contributing_field: str


class QueryResultItem(BaseModel):
    object_id: str
    version: int
    metadata: dict[str, Any]
    modalities: dict[str, Any]
    score: float | None
    explanation: ExplanationResponse | None


class QueryResponse(BaseModel):
    results: list[QueryResultItem]
    strategy: str
    estimated_candidates: int


class CollectionInfo(BaseModel):
    name: str
    object_count: int
    index_kind: str | None
    index_size: int
    modalities: list[str] = []


class FileSummary(BaseModel):
    filename: str
    chunk_count: int


class DeleteFileResponse(BaseModel):
    deleted: int


class ObjectResponse(BaseModel):
    object_id: str
    version: int
    collection: str
    metadata: dict[str, Any]
    modalities: dict[str, Any]


class VersionHistoryEntry(BaseModel):
    catalog_version: int
    action: str
    segment_id: str
    timestamp: float

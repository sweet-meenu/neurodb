from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import HTTPException, status

from neurodb_core.dataplane.runtime import ProjectRuntime
from neurodb_core.dataplane.schemas import (
    CollectionInfo,
    DeleteFileResponse,
    ExplanationResponse,
    FileSummary,
    IngestFileResponse,
    IngestObjectResponse,
    ObjectResponse,
    QueryResponse,
    QueryResultItem,
    VersionHistoryEntry,
)
from neurodb_core.nlp.embedding import encode_as_embedding_record
from neurodb_core.nlp.pipeline import ProcessedChunk, ProcessedMedia
from neurodb_core.query.neuroql.executor import QueryExecutor
from neurodb_core.query.neuroql.lexer import LexError
from neurodb_core.query.neuroql.parser import ParseError, parse
from neurodb_core.storage.records import EmbeddingRecord

"""Business logic shared by both data-plane entry points: the API-key
authenticated REST API (for external applications/SDKs, see dataplane.router)
and the session-authenticated project-data routes used by the dashboard
itself (see controlplane.project_data). Keeping this here means both surfaces
stay in lockstep instead of drifting.
"""

UNNAMED_FILENAME = "Pasted text"  # display name for chunks with no source filename (paste-a-doc ingestion)


def _raw_file_path(runtime: ProjectRuntime, collection: str, filename: str) -> Path:
    # Path(...).name strips any directory components from a caller-supplied
    # filename, so this can't be used to write or read outside raw_files/.
    safe_name = Path(filename).name
    return Path(runtime.storage.root) / "raw_files" / collection / safe_name


def store_chunks(
    runtime: ProjectRuntime, collection: str, chunks: list[ProcessedChunk], filename: str | None = None
) -> list[str]:
    items = []
    for chunk in chunks:
        metadata: dict = {
            "chunk_index": chunk.chunk_index,
            "entities": [e.text for e in chunk.entities],
            "keyphrases": [term for term, _ in chunk.keyphrases],
        }
        if filename:
            metadata["filename"] = filename
        if chunk.classification and chunk.classification[0]:
            metadata["classification"] = chunk.classification[0]

        embedding = EmbeddingRecord(
            model=chunk.embedding.model,
            version=chunk.embedding.version,
            dims=chunk.embedding.dims,
            vector=chunk.embedding.vector,
        )
        items.append({"modalities": {"text": chunk.text}, "metadata": metadata, "embeddings": {"text": embedding}})

    # put_many batches the WAL fsync and catalog persist across the whole
    # document instead of paying both once per chunk (see StorageEngine).
    versions = runtime.storage.put_many(collection, items)
    for ov in versions:
        runtime.index_manager.add(collection, "text", ov.object_id, ov.embeddings["text"].vector)
    return [ov.object_id for ov in versions]


def store_media(runtime: ProjectRuntime, collection: str, media: ProcessedMedia, filename: str) -> list[str]:
    """One image/audio file -> one object carrying the hand-written
    feature-vector embedding, plus (only if a caption/transcript was
    generated — see nlp/captioning.py) separate text-chunk objects under the
    same filename, indexed and searchable exactly like a PDF's chunks."""
    metadata: dict = {
        "filename": filename,
        "modality": media.modality,
        "content_type": media.content_type,
        "chunk_index": 0,
    }
    if media.caption:
        metadata["caption"] = media.caption

    embedding = EmbeddingRecord(
        model=media.embedding.model, version=media.embedding.version, dims=media.embedding.dims, vector=media.embedding.vector
    )
    ov = runtime.storage.put(
        collection, modalities={media.modality: filename}, metadata=metadata, embeddings={media.modality: embedding}
    )
    runtime.index_manager.add(collection, media.modality, ov.object_id, embedding.vector)

    object_ids = [ov.object_id]
    if media.caption_chunks:
        object_ids += store_chunks(runtime, collection, media.caption_chunks, filename=filename)
    return object_ids


def create_object(runtime: ProjectRuntime, collection: str, text: str, metadata: dict) -> IngestObjectResponse:
    embedding = encode_as_embedding_record(text)
    ov = runtime.storage.put(collection, modalities={"text": text}, metadata=metadata, embeddings={"text": embedding})
    runtime.index_manager.add(collection, "text", ov.object_id, embedding.vector)
    return IngestObjectResponse(object_id=ov.object_id, version=ov.version)


def ingest_text(runtime: ProjectRuntime, collection: str, text: str) -> IngestFileResponse:
    chunks = runtime.pipeline.process_text(text)
    object_ids = store_chunks(runtime, collection, chunks)
    return IngestFileResponse(object_ids=object_ids, chunks_created=len(object_ids))


def ingest_file_bytes(runtime: ProjectRuntime, collection: str, data: bytes, filename: str) -> IngestFileResponse:
    try:
        result = runtime.pipeline.process_bytes(data, filename=filename)
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    if isinstance(result, ProcessedMedia):
        object_ids = store_media(runtime, collection, result, filename)
    else:
        object_ids = store_chunks(runtime, collection, result, filename=filename)

    # Keep the original bytes so the Files tab can offer "view" for formats
    # like PDF/image/audio where the extracted text alone isn't the useful
    # artifact. Only the upload path does this — the data-lake connector
    # deliberately never copies files, since those already live in the
    # caller's own tree.
    raw_path = _raw_file_path(runtime, collection, filename)
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_bytes(data)

    return IngestFileResponse(object_ids=object_ids, chunks_created=len(object_ids))


def get_raw_file(runtime: ProjectRuntime, collection: str, filename: str) -> tuple[bytes, str]:
    path = _raw_file_path(runtime, collection, filename)
    if not path.is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no stored file for this filename")
    content_type, _ = mimetypes.guess_type(filename)
    return path.read_bytes(), content_type or "application/octet-stream"


def get_object(runtime: ProjectRuntime, object_id: str) -> ObjectResponse:
    ov = runtime.storage.get(object_id)
    if ov is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "object not found")
    return ObjectResponse(
        object_id=ov.object_id, version=ov.version, collection=ov.collection, metadata=ov.metadata, modalities=ov.modalities
    )


def delete_object(runtime: ProjectRuntime, object_id: str) -> None:
    ov = runtime.storage.get(object_id)
    if ov is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "object not found")
    runtime.storage.delete(object_id)
    for field in list(ov.embeddings.keys()):
        runtime.index_manager.remove(ov.collection, field, object_id)


def list_objects(
    runtime: ProjectRuntime,
    collection: str,
    *,
    filename: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[ObjectResponse]:
    """Paginated so browsing a huge collection in the dashboard doesn't
    serialize every chunk of every file into one response — callers page
    through a single file's chunks (or the whole collection) `limit` at a
    time."""
    rows = runtime.storage.scan(collection)
    if filename is not None:
        rows = [ov for ov in rows if str(ov.metadata.get("filename") or UNNAMED_FILENAME) == filename]
    rows.sort(key=lambda ov: (str(ov.metadata.get("filename") or UNNAMED_FILENAME), ov.metadata.get("chunk_index") or 0))
    page = rows[offset : offset + limit]
    return [
        ObjectResponse(
            object_id=ov.object_id, version=ov.version, collection=ov.collection, metadata=ov.metadata, modalities=ov.modalities
        )
        for ov in page
    ]


def list_files(runtime: ProjectRuntime, collection: str) -> list[FileSummary]:
    """Lightweight per-file summary (name + chunk count only, no chunk text)
    for populating the Files tab's file list without pulling every chunk's
    text over the wire up front."""
    counts: dict[str, int] = {}
    for ov in runtime.storage.scan(collection):
        name = str(ov.metadata.get("filename") or UNNAMED_FILENAME)
        counts[name] = counts.get(name, 0) + 1
    return sorted(
        (FileSummary(filename=name, chunk_count=count) for name, count in counts.items()),
        key=lambda f: f.filename,
    )


def delete_file(runtime: ProjectRuntime, collection: str, filename: str) -> DeleteFileResponse:
    deleted = 0
    for ov in runtime.storage.scan(collection):
        name = str(ov.metadata.get("filename") or UNNAMED_FILENAME)
        if name != filename:
            continue
        runtime.storage.delete(ov.object_id)
        for field in list(ov.embeddings.keys()):
            runtime.index_manager.remove(ov.collection, field, ov.object_id)
        deleted += 1
    _raw_file_path(runtime, collection, filename).unlink(missing_ok=True)
    return DeleteFileResponse(deleted=deleted)


def list_collections(runtime: ProjectRuntime) -> list[CollectionInfo]:
    infos = []
    for name in runtime.storage.collections():
        count = len(runtime.storage.scan(name))
        # A collection can hold several embedding fields side by side now
        # (e.g. "text" and "image" for multimodal objects) — aggregate
        # across all of them instead of assuming "text" is the only one.
        fields = sorted(runtime.index_manager.fields(name))
        kinds: set[str] = set()
        total_size = 0
        for field in fields:
            field_stats = runtime.index_manager.stats(name, field)
            if field_stats:
                kinds.add(field_stats.kind)
                total_size += field_stats.size
        infos.append(
            CollectionInfo(
                name=name,
                object_count=count,
                index_kind="+".join(sorted(kinds)) if kinds else None,
                index_size=total_size,
                modalities=fields,
            )
        )
    return infos


def collection_versions(runtime: ProjectRuntime) -> list[VersionHistoryEntry]:
    return [
        VersionHistoryEntry(
            catalog_version=entry["catalog_version"],
            action=entry["action"],
            segment_id=entry["segment_id"],
            timestamp=entry["timestamp"],
        )
        for entry in runtime.storage.catalog.history()
    ]


def run_query(runtime: ProjectRuntime, query_text: str) -> QueryResponse:
    try:
        stmt = parse(query_text)
    except (ParseError, LexError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"NeuroQL parse error: {exc}") from exc

    executor = QueryExecutor(runtime.storage, runtime.index_manager, lambda t: encode_as_embedding_record(t).vector)
    results, plan = executor.execute(stmt)

    items = []
    for r in results:
        explanation = ExplanationResponse(**r.explanation.__dict__) if r.explanation is not None else None
        items.append(
            QueryResultItem(
                object_id=r.object_version.object_id,
                version=r.object_version.version,
                metadata=r.object_version.metadata,
                modalities=r.object_version.modalities,
                score=r.score,
                explanation=explanation,
            )
        )
    return QueryResponse(results=items, strategy=plan.strategy, estimated_candidates=plan.estimated_candidates)

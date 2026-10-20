from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from neurodb_core.index.manager import IndexManager
from neurodb_core.nlp.extraction import SUPPORTED_EXTENSIONS
from neurodb_core.nlp.pipeline import DocumentPipeline, ProcessedChunk, ProcessedMedia
from neurodb_core.storage.records import EmbeddingRecord
from neurodb_core.storage.storage_engine import StorageEngine


@dataclass
class IngestStats:
    files_scanned: int = 0
    files_ingested: int = 0
    chunks_created: int = 0
    errors: list[str] = field(default_factory=list)


class LocalDataLakeConnector:
    """Indexes documents already sitting in a local directory tree (a
    stand-in for an S3/MinIO-backed data lake, and free to run) in place:
    files are read and processed through the NLP pipeline but never copied
    or moved, matching how NeuroDB is meant to extend semantic search over
    an existing data lake without duplicating storage.
    """

    def __init__(
        self,
        storage: StorageEngine,
        index_manager: IndexManager,
        pipeline: DocumentPipeline | None = None,
    ):
        self.storage = storage
        self.index_manager = index_manager
        self.pipeline = pipeline or DocumentPipeline()

    def ingest_directory(self, root: Path | str, *, collection: str, recursive: bool = True) -> IngestStats:
        root = Path(root)
        stats = IngestStats()
        pattern = "**/*" if recursive else "*"
        for path in sorted(root.glob(pattern)):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            stats.files_scanned += 1
            try:
                object_ids = self.ingest_file(path, collection=collection)
            except Exception as exc:  # noqa: BLE001 - captured in stats, ingestion of other files continues
                stats.errors.append(f"{path}: {exc}")
                continue
            stats.files_ingested += 1
            stats.chunks_created += len(object_ids)
        return stats

    def ingest_file(self, path: Path, *, collection: str) -> list[str]:
        result = self.pipeline.process_file(path, source_metadata={"source_path": str(path)})
        if isinstance(result, ProcessedMedia):
            object_ids = self._ingest_media(result, collection=collection, filename=path.name)
        else:
            object_ids = self._ingest_text_chunks(result, collection=collection)
        return object_ids

    def _ingest_text_chunks(self, chunks: list[ProcessedChunk], *, collection: str) -> list[str]:
        items = []
        for chunk in chunks:
            metadata = {
                "source_path": chunk.source_metadata.get("source_path"),
                "filename": chunk.source_metadata.get("filename"),
                "chunk_index": chunk.chunk_index,
                "entities": [e.text for e in chunk.entities],
                "keyphrases": [term for term, _ in chunk.keyphrases],
            }
            if chunk.classification and chunk.classification[0]:
                metadata["classification"] = chunk.classification[0]

            embedding_record = EmbeddingRecord(
                model=chunk.embedding.model,
                version=chunk.embedding.version,
                dims=chunk.embedding.dims,
                vector=chunk.embedding.vector,
            )
            items.append(
                {"modalities": {"text": chunk.text}, "metadata": metadata, "embeddings": {"text": embedding_record}}
            )

        versions = self.storage.put_many(collection, items)
        for ov in versions:
            self.index_manager.add(collection, "text", ov.object_id, ov.embeddings["text"].vector)
        return [ov.object_id for ov in versions]

    def _ingest_media(self, media: ProcessedMedia, *, collection: str, filename: str) -> list[str]:
        metadata = {
            "source_path": media.source_metadata.get("source_path"),
            "filename": filename,
            "modality": media.modality,
            "content_type": media.content_type,
            "chunk_index": 0,
        }
        if media.caption:
            metadata["caption"] = media.caption

        embedding_record = EmbeddingRecord(
            model=media.embedding.model, version=media.embedding.version, dims=media.embedding.dims, vector=media.embedding.vector
        )
        ov = self.storage.put(
            collection,
            modalities={media.modality: filename},
            metadata=metadata,
            embeddings={media.modality: embedding_record},
        )
        self.index_manager.add(collection, media.modality, ov.object_id, embedding_record.vector)

        object_ids = [ov.object_id]
        if media.caption_chunks:
            object_ids += self._ingest_text_chunks(media.caption_chunks, collection=collection)
        return object_ids

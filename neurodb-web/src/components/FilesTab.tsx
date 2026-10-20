"use client";

import { useEffect, useState } from "react";
import { apiFetch, apiFetchBlob, ApiError } from "@/lib/api";
import type { CollectionInfo, DeleteFileResponse, FileSummary, ObjectResponse } from "@/lib/types";

const PAGE_SIZE = 20;

type ChunkPage = {
  items: ObjectResponse[];
  loading: boolean;
  exhausted: boolean;
  error: string | null;
};

function MediaPreview({
  projectId,
  collectionName,
  filename,
  modality,
}: {
  projectId: string;
  collectionName: string;
  filename: string;
  modality: string;
}) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    apiFetchBlob(
      `/api/control/projects/${projectId}/data/collections/${collectionName}/files/raw?filename=${encodeURIComponent(filename)}`
    )
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load preview."));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [projectId, collectionName, filename]);

  if (error) return <p className="text-sm text-danger">{error}</p>;
  if (!url) return <p className="text-sm text-muted">Loading preview…</p>;
  if (modality === "image") {
    // eslint-disable-next-line @next/next/no-img-element -- blob: URL, next/image can't optimize it
    return <img src={url} alt={filename} className="max-h-64 max-w-full rounded-md border border-border object-contain" />;
  }
  if (modality === "audio") return <audio controls src={url} className="w-full" />;
  return null;
}

export function FilesTab({ projectId }: { projectId: string }) {
  const [collections, setCollections] = useState<CollectionInfo[] | null>(null);
  const [collectionName, setCollectionName] = useState<string | null>(null);
  const [files, setFiles] = useState<FileSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [openFile, setOpenFile] = useState<string | null>(null);
  const [openChunk, setOpenChunk] = useState<string | null>(null);
  const [chunkPages, setChunkPages] = useState<Record<string, ChunkPage>>({});
  const [deletingFile, setDeletingFile] = useState<string | null>(null);
  const [viewingFile, setViewingFile] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<CollectionInfo[]>(`/api/control/projects/${projectId}/data/collections`)
      .then((data) => {
        setCollections(data);
        if (data.length > 0) setCollectionName((current) => current ?? data[0].name);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load collections."));
  }, [projectId]);

  function loadFiles(collection: string) {
    setFiles(null);
    setError(null);
    apiFetch<FileSummary[]>(`/api/control/projects/${projectId}/data/collections/${collection}/files`)
      .then(setFiles)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load files."));
  }

  useEffect(() => {
    if (!collectionName) return;
    setOpenFile(null);
    setChunkPages({});
    loadFiles(collectionName);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, collectionName]);

  function loadChunkPage(filename: string, offset: number) {
    if (!collectionName) return;
    setChunkPages((prev) => ({
      ...prev,
      [filename]: {
        items: prev[filename]?.items ?? [],
        exhausted: prev[filename]?.exhausted ?? false,
        error: null,
        loading: true,
      },
    }));
    const params = new URLSearchParams({
      filename,
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    apiFetch<ObjectResponse[]>(
      `/api/control/projects/${projectId}/data/collections/${collectionName}/objects?${params.toString()}`
    )
      .then((page) => {
        setChunkPages((prev) => ({
          ...prev,
          [filename]: {
            items: [...(prev[filename]?.items ?? []), ...page],
            exhausted: page.length < PAGE_SIZE,
            error: null,
            loading: false,
          },
        }));
      })
      .catch((err) => {
        setChunkPages((prev) => ({
          ...prev,
          [filename]: {
            items: prev[filename]?.items ?? [],
            exhausted: prev[filename]?.exhausted ?? false,
            error: err instanceof ApiError ? err.message : "Failed to load chunks.",
            loading: false,
          },
        }));
      });
  }

  function toggleFile(filename: string) {
    if (openFile === filename) {
      setOpenFile(null);
      return;
    }
    setOpenFile(filename);
    if (!chunkPages[filename]) loadChunkPage(filename, 0);
  }

  async function onDeleteFile(filename: string) {
    if (!collectionName) return;
    if (!confirm(`Delete all chunks ingested from "${filename}"? This can't be undone.`)) return;
    setDeletingFile(filename);
    setError(null);
    try {
      await apiFetch<DeleteFileResponse>(
        `/api/control/projects/${projectId}/data/collections/${collectionName}/files?filename=${encodeURIComponent(filename)}`,
        { method: "DELETE" }
      );
      if (openFile === filename) setOpenFile(null);
      setChunkPages((prev) => {
        const next = { ...prev };
        delete next[filename];
        return next;
      });
      loadFiles(collectionName);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to delete file.");
    } finally {
      setDeletingFile(null);
    }
  }

  async function onViewPdf(filename: string) {
    if (!collectionName) return;
    setViewingFile(filename);
    setError(null);
    try {
      const blob = await apiFetchBlob(
        `/api/control/projects/${projectId}/data/collections/${collectionName}/files/raw?filename=${encodeURIComponent(filename)}`
      );
      const url = URL.createObjectURL(blob);
      window.open(url, "_blank");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to open file.");
    } finally {
      setViewingFile(null);
    }
  }

  if (collections !== null && collections.length === 0) {
    return <p className="text-sm text-muted">No collections yet — ingest a document from the Data tab first.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <label className="flex flex-col gap-1.5 text-sm sm:w-64">
        <span className="text-muted">Collection</span>
        <select
          value={collectionName ?? ""}
          onChange={(e) => setCollectionName(e.target.value)}
          className="rounded-md border border-border bg-surface-2 px-3 py-2 outline-none focus:border-accent"
        >
          {(collections ?? []).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      {error && <p className="text-sm text-danger">{error}</p>}

      {files === null ? (
        <p className="text-sm text-muted">Loading…</p>
      ) : files.length === 0 ? (
        <p className="text-sm text-muted">Nothing ingested into this collection yet.</p>
      ) : (
        <div className="flex flex-col gap-3">
          {files.map((f) => {
            const page = chunkPages[f.filename];
            const isOpen = openFile === f.filename;
            return (
              <div key={f.filename} className="rounded-lg border border-border bg-surface">
                <div className="flex items-center justify-between gap-4 px-5 py-3">
                  <button
                    onClick={() => toggleFile(f.filename)}
                    className="flex min-w-0 flex-1 items-center justify-between gap-4 text-left"
                  >
                    <span className="truncate font-mono text-sm">{f.filename}</span>
                    <span className="shrink-0 text-xs text-muted">
                      {f.chunk_count} chunk{f.chunk_count === 1 ? "" : "s"}
                    </span>
                  </button>
                  {f.filename.toLowerCase().endsWith(".pdf") && (
                    <button
                      onClick={() => onViewPdf(f.filename)}
                      disabled={viewingFile === f.filename}
                      className="shrink-0 rounded-md border border-border px-2 py-1 text-xs text-foreground hover:bg-surface-2 disabled:opacity-60"
                    >
                      {viewingFile === f.filename ? "Opening…" : "View PDF"}
                    </button>
                  )}
                  <button
                    onClick={() => onDeleteFile(f.filename)}
                    disabled={deletingFile === f.filename}
                    className="shrink-0 rounded-md border border-danger/40 px-2 py-1 text-xs text-danger hover:bg-danger/10 disabled:opacity-60"
                  >
                    {deletingFile === f.filename ? "Deleting…" : "Delete"}
                  </button>
                </div>
                {isOpen && (
                  <div className="flex flex-col gap-2 border-t border-border p-4">
                    {page?.items.map((chunk) => {
                      const modality = chunk.metadata.modality;
                      const key = chunk.object_id;

                      if (typeof modality === "string" && (modality === "image" || modality === "audio")) {
                        const caption = typeof chunk.metadata.caption === "string" ? chunk.metadata.caption : null;
                        return (
                          <div key={key} className="rounded-md border border-border bg-surface-2 p-3">
                            <p className="mb-2 text-xs uppercase text-muted">{modality} · feature-vector embedding</p>
                            {collectionName && (
                              <MediaPreview
                                projectId={projectId}
                                collectionName={collectionName}
                                filename={f.filename}
                                modality={modality}
                              />
                            )}
                            {caption ? (
                              <p className="mt-2 text-sm">
                                <span className="text-muted">AI description: </span>
                                {caption}
                              </p>
                            ) : (
                              <p className="mt-2 text-xs text-muted">
                                No description generated — set NEURODB_CAPTION_API_KEY on the server to enable
                                text search over what this {modality} shows/says.
                              </p>
                            )}
                          </div>
                        );
                      }

                      const text = typeof chunk.modalities.text === "string" ? chunk.modalities.text : "";
                      const chunkIndex = chunk.metadata.chunk_index;
                      const chunkOpen = openChunk === key;
                      return (
                        <div key={key} className="rounded-md border border-border bg-surface-2 p-3">
                          <button
                            onClick={() => setOpenChunk(chunkOpen ? null : key)}
                            className="flex w-full items-center justify-between gap-4 text-left text-xs text-muted hover:text-foreground"
                          >
                            <span>
                              {typeof chunkIndex === "number" ? `Chunk ${chunkIndex}` : "Chunk"} · {text.length} chars
                            </span>
                            <span className="font-mono">{chunkOpen ? "hide" : "show"}</span>
                          </button>
                          {chunkOpen && <p className="mt-2 whitespace-pre-wrap break-words text-sm">{text}</p>}
                        </div>
                      );
                    })}
                    {page?.error && <p className="text-sm text-danger">{page.error}</p>}
                    {page?.loading && <p className="text-sm text-muted">Loading…</p>}
                    {page && !page.loading && !page.exhausted && (
                      <button
                        onClick={() => loadChunkPage(f.filename, page.items.length)}
                        className="w-fit rounded-md border border-border px-3 py-1.5 text-xs text-foreground hover:bg-surface-2"
                      >
                        Load more ({page.items.length} of {f.chunk_count})
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

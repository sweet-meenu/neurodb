"use client";

import { useEffect, useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { CollectionInfo, IngestFileResponse } from "@/lib/types";

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"
      />
    </svg>
  );
}

export function DataTab({ projectId }: { projectId: string }) {
  const [collections, setCollections] = useState<CollectionInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [collectionName, setCollectionName] = useState("docs");
  const [text, setText] = useState("");
  const [ingesting, setIngesting] = useState(false);
  const [lastResult, setLastResult] = useState<IngestFileResponse | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [fileCollectionName, setFileCollectionName] = useState("docs");
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [lastUpload, setLastUpload] = useState<IngestFileResponse | null>(null);

  async function refresh() {
    try {
      const data = await apiFetch<CollectionInfo[]>(`/api/control/projects/${projectId}/data/collections`);
      setCollections(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load collections.");
    }
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  async function onIngest(e: FormEvent) {
    e.preventDefault();
    setIngesting(true);
    setError(null);
    setLastResult(null);
    try {
      const form = new FormData();
      form.set("collection", collectionName);
      form.set("text", text);
      const res = await apiFetch<IngestFileResponse>(`/api/control/projects/${projectId}/data/ingest/text`, {
        method: "POST",
        formData: form,
      });
      setLastResult(res);
      setText("");
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to ingest document.");
    } finally {
      setIngesting(false);
    }
  }

  async function onUpload(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setUploading(true);
    setUploadError(null);
    setLastUpload(null);
    try {
      const form = new FormData();
      form.set("collection", fileCollectionName);
      form.set("file", file);
      const res = await apiFetch<IngestFileResponse>(`/api/control/projects/${projectId}/data/ingest/file`, {
        method: "POST",
        formData: form,
      });
      setLastUpload(res);
      setFile(null);
      await refresh();
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "Failed to ingest file.");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-border bg-surface p-5">
        <h3 className="font-medium">Upload a file</h3>
        <p className="mt-1 text-sm text-muted">
          Text, PDF, CSV, image, and audio (.wav, .mp3) files each run through their own pipeline — text gets
          chunked and embedded, images/audio get a hand-written feature-vector embedding of their own. .mp3
          additionally needs the server-side Whisper backend enabled to transcribe/decode it.
        </p>
        <form onSubmit={onUpload} className="mt-4 flex flex-col gap-3">
          <label className="flex flex-col gap-1.5 text-sm sm:w-64">
            <span className="text-muted">Collection</span>
            <input
              required
              disabled={uploading}
              value={fileCollectionName}
              onChange={(e) => setFileCollectionName(e.target.value)}
              className="rounded-md border border-border bg-surface-2 px-3 py-2 outline-none focus:border-accent disabled:opacity-60"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-muted">File</span>
            <input
              required
              type="file"
              disabled={uploading}
              accept=".pdf,.txt,.md,.markdown,.html,.htm,.csv,.png,.jpg,.jpeg,.gif,.bmp,.webp,.wav,.mp3"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="rounded-md border border-border bg-surface-2 px-3 py-2 text-sm outline-none file:mr-3 file:rounded file:border-0 file:bg-accent file:px-3 file:py-1.5 file:text-black disabled:opacity-60"
            />
          </label>
          <button
            type="submit"
            disabled={uploading || !file}
            className="flex w-fit items-center gap-2 rounded-md bg-accent px-4 py-2 font-medium text-black hover:bg-accent-strong disabled:opacity-60"
          >
            {uploading && <Spinner />}
            {uploading ? "Uploading & processing…" : "Upload & ingest"}
          </button>
        </form>
        {uploading && (
          <p className="mt-3 flex items-center gap-2 text-sm text-muted">
            <Spinner />
            Extracting text, chunking, and embedding{file ? ` "${file.name}"` : ""} — large files can take a
            while.
          </p>
        )}
        {lastUpload && (
          <p className="mt-3 text-sm text-accent">
            Created {lastUpload.chunks_created} chunk{lastUpload.chunks_created === 1 ? "" : "s"}.
          </p>
        )}
        {uploadError && <p className="mt-3 text-sm text-danger">{uploadError}</p>}
      </div>

      <div className="rounded-lg border border-border bg-surface p-5">
        <h3 className="font-medium">Quick ingest</h3>
        <p className="mt-1 text-sm text-muted">
          Runs the full NLP pipeline — extraction, semantic chunking, NER, keyphrases, embedding — and stores the
          result. For files and larger corpora, use the REST API or the data lake connector.
        </p>
        <form onSubmit={onIngest} className="mt-4 flex flex-col gap-3">
          <label className="flex flex-col gap-1.5 text-sm sm:w-64">
            <span className="text-muted">Collection</span>
            <input
              required
              disabled={ingesting}
              value={collectionName}
              onChange={(e) => setCollectionName(e.target.value)}
              className="rounded-md border border-border bg-surface-2 px-3 py-2 outline-none focus:border-accent disabled:opacity-60"
            />
          </label>
          <label className="flex flex-col gap-1.5 text-sm">
            <span className="text-muted">Text</span>
            <textarea
              required
              rows={5}
              disabled={ingesting}
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Paste a document, note, or ticket to ingest…"
              className="rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-xs outline-none focus:border-accent disabled:opacity-60"
            />
          </label>
          <button
            type="submit"
            disabled={ingesting}
            className="flex w-fit items-center gap-2 rounded-md bg-accent px-4 py-2 font-medium text-black hover:bg-accent-strong disabled:opacity-60"
          >
            {ingesting && <Spinner />}
            {ingesting ? "Processing…" : "Ingest"}
          </button>
        </form>
        {ingesting && (
          <p className="mt-3 flex items-center gap-2 text-sm text-muted">
            <Spinner />
            Chunking, extracting entities/keyphrases, and embedding — this can take a moment for longer text.
          </p>
        )}
        {lastResult && (
          <p className="mt-3 text-sm text-accent">
            Created {lastResult.chunks_created} chunk{lastResult.chunks_created === 1 ? "" : "s"}.
          </p>
        )}
      </div>

      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="rounded-lg border border-border bg-surface">
        <div className="border-b border-border px-5 py-3">
          <h3 className="font-medium">Collections</h3>
        </div>
        {collections === null ? (
          <p className="p-5 text-sm text-muted">Loading…</p>
        ) : collections.length === 0 ? (
          <p className="p-5 text-sm text-muted">No collections yet — ingest a document to create one.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs text-muted">
                <th className="px-5 py-2 font-normal">Name</th>
                <th className="px-5 py-2 font-normal">Objects</th>
                <th className="px-5 py-2 font-normal">Modalities</th>
                <th className="px-5 py-2 font-normal">Index</th>
                <th className="px-5 py-2 font-normal">Index size</th>
              </tr>
            </thead>
            <tbody>
              {collections.map((c) => (
                <tr key={c.name} className="border-t border-border">
                  <td className="px-5 py-3 font-mono">{c.name}</td>
                  <td className="px-5 py-3">{c.object_count}</td>
                  <td className="px-5 py-3">
                    <div className="flex flex-wrap gap-1">
                      {c.modalities.length === 0 ? (
                        <span className="text-muted">—</span>
                      ) : (
                        c.modalities.map((m) => (
                          <span
                            key={m}
                            className="rounded-full border border-border px-2 py-0.5 text-xs uppercase text-muted"
                          >
                            {m}
                          </span>
                        ))
                      )}
                    </div>
                  </td>
                  <td className="px-5 py-3">
                    <span className="rounded-full border border-border px-2 py-0.5 text-xs uppercase text-muted">
                      {c.index_kind ?? "none"}
                    </span>
                  </td>
                  <td className="px-5 py-3">{c.index_size}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

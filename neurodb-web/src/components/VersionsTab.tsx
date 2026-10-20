"use client";

import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { CollectionInfo, VersionHistoryEntry } from "@/lib/types";

export function VersionsTab({ projectId }: { projectId: string }) {
  const [collections, setCollections] = useState<CollectionInfo[]>([]);
  const [selected, setSelected] = useState<string>("");
  const [entries, setEntries] = useState<VersionHistoryEntry[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    apiFetch<CollectionInfo[]>(`/api/control/projects/${projectId}/data/collections`)
      .then((cols) => {
        setCollections(cols);
        if (cols.length > 0) setSelected(cols[0].name);
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load collections."));
  }, [projectId]);

  useEffect(() => {
    if (!selected) return;
    apiFetch<VersionHistoryEntry[]>(`/api/control/projects/${projectId}/data/collections/${selected}/versions`)
      .then(setEntries)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Failed to load version history."));
  }, [projectId, selected]);

  if (collections.length === 0) {
    return <p className="text-sm text-muted">No collections yet — ingest a document first.</p>;
  }

  return (
    <div className="flex flex-col gap-4">
      <label className="flex w-64 flex-col gap-1.5 text-sm">
        <span className="text-muted">Collection</span>
        <select
          value={selected}
          onChange={(e) => setSelected(e.target.value)}
          className="rounded-md border border-border bg-surface-2 px-3 py-2 outline-none focus:border-accent"
        >
          {collections.map((c) => (
            <option key={c.name} value={c.name}>
              {c.name}
            </option>
          ))}
        </select>
      </label>

      {error && <p className="text-sm text-danger">{error}</p>}

      <div className="rounded-lg border border-border bg-surface">
        <div className="border-b border-border px-5 py-3">
          <h3 className="font-medium">Storage checkpoint history</h3>
          <p className="mt-1 text-xs text-muted">
            Every write is a new MVCC version immediately; this is the segment-flush (checkpoint) log used by
            NeuroQL&rsquo;s <code className="font-mono">AS OF VERSION</code> / <code className="font-mono">AS OF TIMESTAMP</code> time-travel queries.
          </p>
        </div>
        {entries === null ? (
          <p className="p-5 text-sm text-muted">Loading…</p>
        ) : entries.length === 0 ? (
          <p className="p-5 text-sm text-muted">No checkpoints yet — writes are still buffered in memory.</p>
        ) : (
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="text-xs text-muted">
                <th className="px-5 py-2 font-normal">Catalog version</th>
                <th className="px-5 py-2 font-normal">Action</th>
                <th className="px-5 py-2 font-normal">Segment</th>
                <th className="px-5 py-2 font-normal">When</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.catalog_version} className="border-t border-border">
                  <td className="px-5 py-3">{e.catalog_version}</td>
                  <td className="px-5 py-3">{e.action}</td>
                  <td className="px-5 py-3 font-mono text-xs">{e.segment_id}</td>
                  <td className="px-5 py-3 text-xs text-muted">{new Date(e.timestamp * 1000).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

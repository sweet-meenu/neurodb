"use client";

import { useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import type { QueryResponse, QueryResultItem } from "@/lib/types";

const PLACEHOLDER = `SELECT *
FROM docs
SEMANTIC SIMILAR TO 'your search text here'
LIMIT 5;`;

export function SqlEditorTab({ projectId }: { projectId: string }) {
  const [query, setQuery] = useState(PLACEHOLDER);
  const [response, setResponse] = useState<QueryResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [expanded, setExpanded] = useState<string | null>(null);

  async function onRun(e: FormEvent) {
    e.preventDefault();
    setRunning(true);
    setError(null);
    try {
      const res = await apiFetch<QueryResponse>(`/api/control/projects/${projectId}/data/query`, {
        method: "POST",
        body: { query },
      });
      setResponse(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Query failed.");
      setResponse(null);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <form onSubmit={onRun} className="rounded-lg border border-border bg-surface">
        <div className="flex items-center justify-between border-b border-border px-4 py-2">
          <span className="text-xs text-muted">NeuroQL</span>
          <button
            type="submit"
            disabled={running}
            className="rounded-md bg-accent px-3 py-1.5 text-sm font-medium text-black hover:bg-accent-strong disabled:opacity-60"
          >
            {running ? "Running…" : "Run query"}
          </button>
        </div>
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={6}
          spellCheck={false}
          className="w-full resize-y bg-transparent px-4 py-3 font-mono text-sm outline-none"
        />
      </form>

      {error && <p className="text-sm text-danger">{error}</p>}

      {response && (
        <div>
          <p className="mb-3 text-xs text-muted">
            Plan: <span className="text-foreground">{response.strategy}</span> · estimated candidates{" "}
            {response.estimated_candidates} · {response.results.length} result
            {response.results.length === 1 ? "" : "s"}
          </p>
          <div className="flex flex-col gap-3">
            {response.results.map((r) => (
              <ResultCard
                key={r.object_id}
                result={r}
                expanded={expanded === r.object_id}
                onToggle={() => setExpanded(expanded === r.object_id ? null : r.object_id)}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function ResultCard({
  result,
  expanded,
  onToggle,
}: {
  result: QueryResultItem;
  expanded: boolean;
  onToggle: () => void;
}) {
  const text = typeof result.modalities.text === "string" ? result.modalities.text : "";
  const filename = typeof result.metadata.filename === "string" ? result.metadata.filename : null;
  return (
    <div className="rounded-lg border border-border bg-surface p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="truncate font-mono text-xs text-muted">{result.object_id}</p>
          {filename && (
            <p className="mt-0.5 truncate text-xs text-accent" title={filename}>
              from {filename}
            </p>
          )}
          <p className="mt-1 whitespace-pre-wrap break-words text-sm">{text || JSON.stringify(result.metadata)}</p>
        </div>
        {result.score !== null && (
          <span className="shrink-0 rounded-full border border-accent/40 px-2 py-0.5 text-xs text-accent">
            {result.score.toFixed(3)}
          </span>
        )}
      </div>
      {result.explanation && (
        <button onClick={onToggle} className="mt-2 text-xs text-muted hover:text-foreground">
          {expanded ? "Hide explanation" : "Why this match?"}
        </button>
      )}
      {expanded && result.explanation && (
        <div className="mt-3 grid grid-cols-1 gap-2 border-t border-border pt-3 text-xs sm:grid-cols-2">
          <div>
            <span className="text-muted">Confidence</span>
            <p>{(result.explanation.confidence * 100).toFixed(1)}%</p>
          </div>
          <div>
            <span className="text-muted">Contributing field</span>
            <p className="font-mono">{result.explanation.contributing_field}</p>
          </div>
          <div>
            <span className="text-muted">Matched terms</span>
            <p>{result.explanation.matched_terms.join(", ") || "—"}</p>
          </div>
          <div>
            <span className="text-muted">Matched entities</span>
            <p>{result.explanation.matched_entities.join(", ") || "—"}</p>
          </div>
        </div>
      )}
    </div>
  );
}

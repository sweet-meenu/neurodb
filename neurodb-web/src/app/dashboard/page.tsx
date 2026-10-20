"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { CopyableField } from "@/components/CopyableField";
import type { Project, ProjectCreated } from "@/lib/types";

export default function DashboardPage() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [justCreated, setJustCreated] = useState<ProjectCreated | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function refresh() {
    try {
      const data = await apiFetch<Project[]>("/api/control/projects");
      setProjects(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load projects.");
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  async function onCreate(e: FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const project = await apiFetch<ProjectCreated>("/api/control/projects", {
        method: "POST",
        body: { name: newName },
      });
      setJustCreated(project);
      setNewName("");
      setCreating(false);
      await refresh();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to create project.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex flex-col gap-8">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          <p className="mt-1 text-sm text-muted">Each project is an isolated, fully managed NeuroDB instance.</p>
        </div>
        <button
          onClick={() => setCreating((v) => !v)}
          className="rounded-md bg-accent px-4 py-2 font-medium text-black hover:bg-accent-strong"
        >
          New project
        </button>
      </div>

      {creating && (
        <form onSubmit={onCreate} className="flex items-end gap-3 rounded-lg border border-border bg-surface p-4">
          <label className="flex flex-1 flex-col gap-1.5 text-sm">
            <span className="text-muted">Project name</span>
            <input
              autoFocus
              required
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="my-first-db"
              className="rounded-md border border-border bg-surface-2 px-3 py-2 outline-none focus:border-accent"
            />
          </label>
          <button
            type="submit"
            disabled={submitting}
            className="rounded-md bg-accent px-4 py-2 font-medium text-black hover:bg-accent-strong disabled:opacity-60"
          >
            {submitting ? "Creating…" : "Create"}
          </button>
        </form>
      )}

      {justCreated && (
        <div className="rounded-lg border border-accent/40 bg-surface p-5">
          <div className="flex items-center justify-between">
            <h2 className="font-medium">
              &ldquo;{justCreated.name}&rdquo; is ready
            </h2>
            <button onClick={() => setJustCreated(null)} className="text-xs text-muted hover:text-foreground">
              Dismiss
            </button>
          </div>
          <p className="mt-1 text-sm text-danger">
            This API key is shown once. Store it now — you won&rsquo;t be able to see it again.
          </p>
          <div className="mt-4 flex flex-col gap-4">
            <CopyableField label="Connection string" value={justCreated.connection_string} />
            <CopyableField label="API key" value={justCreated.api_key} />
          </div>
        </div>
      )}

      {error && <p className="text-sm text-danger">{error}</p>}

      {projects === null ? (
        <p className="text-sm text-muted">Loading projects…</p>
      ) : projects.length === 0 ? (
        <div className="rounded-lg border border-dashed border-border p-10 text-center text-sm text-muted">
          No projects yet. Create your first NeuroDB instance to get a connection string and API key.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <Link
              key={p.id}
              href={`/dashboard/${p.id}`}
              className="rounded-lg border border-border bg-surface p-5 transition-colors hover:border-accent/50"
            >
              <h3 className="font-medium">{p.name}</h3>
              <p className="mt-1 font-mono text-xs text-muted">{p.api_key_prefix}…</p>
              <p className="mt-3 text-xs text-muted">
                Created {new Date(p.created_at * 1000).toLocaleDateString()}
              </p>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

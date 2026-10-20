"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "@/lib/api";
import { CopyableField } from "@/components/CopyableField";
import { DataTab } from "@/components/DataTab";
import { FilesTab } from "@/components/FilesTab";
import { IconArrowLeft, IconDatabase, IconFolder, IconHistory, IconHome, IconTerminal } from "@/components/icons";
import { SqlEditorTab } from "@/components/SqlEditorTab";
import { VersionsTab } from "@/components/VersionsTab";
import type { ConnectionInfo, Project } from "@/lib/types";

const TABS = [
  { name: "Overview", icon: IconHome },
  { name: "Data", icon: IconDatabase },
  { name: "Files", icon: IconFolder },
  { name: "SQL Editor", icon: IconTerminal },
  { name: "Versions", icon: IconHistory },
] as const;
type Tab = (typeof TABS)[number]["name"];

export function ProjectDetail({ projectId }: { projectId: string }) {
  const [project, setProject] = useState<Project | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Overview");
  // Tabs are kept mounted (just hidden) once visited, rather than unmounted
  // on switch, so in-progress work in a tab -- e.g. an upload in Data --
  // isn't discarded when you navigate away and come back.
  const [visited, setVisited] = useState<Set<Tab>>(new Set(["Overview"]));

  function selectTab(name: Tab) {
    setTab(name);
    setVisited((prev) => (prev.has(name) ? prev : new Set(prev).add(name)));
  }

  useEffect(() => {
    apiFetch<Project>(`/api/control/projects/${projectId}`)
      .then(setProject)
      .catch((err) => setError(err instanceof ApiError ? err.message : "Project not found."));
  }, [projectId]);

  if (error) {
    return (
      <div className="flex flex-col gap-4">
        <p className="text-sm text-danger">{error}</p>
        <Link href="/dashboard" className="text-sm text-accent hover:underline">
          Back to projects
        </Link>
      </div>
    );
  }

  return (
    <div className="flex min-h-[calc(100vh-8rem)] gap-8">
      <aside className="w-56 shrink-0">
        <div className="sticky top-8">
          <Link
            href="/dashboard"
            className="flex items-center gap-1.5 text-xs text-muted transition-colors hover:text-foreground"
          >
            <IconArrowLeft />
            Projects
          </Link>
          <h1 className="mt-2 truncate text-lg font-semibold tracking-tight" title={project?.name}>
            {project?.name ?? "…"}
          </h1>

          <nav className="mt-6 flex flex-col gap-0.5">
            {TABS.map(({ name, icon: Icon }) => (
              <button
                key={name}
                onClick={() => selectTab(name)}
                className={`flex items-center gap-2.5 rounded-md px-3 py-2 text-left text-sm transition-colors ${
                  tab === name
                    ? "bg-accent/10 font-medium text-accent"
                    : "text-muted hover:bg-surface hover:text-foreground"
                }`}
              >
                <Icon className={`h-4 w-4 shrink-0 ${tab === name ? "text-accent" : ""}`} />
                {name}
              </button>
            ))}
          </nav>
        </div>
      </aside>

      <div className="min-w-0 flex-1 border-l border-border pl-8">
        {visited.has("Overview") && project && (
          <div className={tab === "Overview" ? "" : "hidden"}>
            <OverviewTab projectId={projectId} project={project} />
          </div>
        )}
        {visited.has("Data") && (
          <div className={tab === "Data" ? "" : "hidden"}>
            <DataTab projectId={projectId} />
          </div>
        )}
        {visited.has("Files") && (
          <div className={tab === "Files" ? "" : "hidden"}>
            <FilesTab projectId={projectId} />
          </div>
        )}
        {visited.has("SQL Editor") && (
          <div className={tab === "SQL Editor" ? "" : "hidden"}>
            <SqlEditorTab projectId={projectId} />
          </div>
        )}
        {visited.has("Versions") && (
          <div className={tab === "Versions" ? "" : "hidden"}>
            <VersionsTab projectId={projectId} />
          </div>
        )}
      </div>
    </div>
  );
}

function OverviewTab({ projectId, project }: { projectId: string; project: Project }) {
  const [rotated, setRotated] = useState<ConnectionInfo | null>(null);
  const [rotating, setRotating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onRotate() {
    if (!confirm("Rotating the API key immediately invalidates the old one. Continue?")) return;
    setRotating(true);
    setError(null);
    try {
      const info = await apiFetch<ConnectionInfo>(`/api/control/projects/${projectId}/rotate-key`, {
        method: "POST",
      });
      setRotated(info);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to rotate API key.");
    } finally {
      setRotating(false);
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-border bg-surface p-5">
        <h3 className="font-medium">Connection</h3>
        <p className="mt-1 text-sm text-muted">
          Use this connection string from your application, or generate a new key below. Keys are only ever shown
          once.
        </p>
        <div className="mt-4 flex flex-col gap-3 text-sm">
          <div>
            <span className="text-muted">Project ID</span>
            <p className="font-mono text-xs">{project.id}</p>
          </div>
          <div>
            <span className="text-muted">API key</span>
            <p className="font-mono text-xs">{project.api_key_prefix}••••••••••••••••••••••••</p>
          </div>
        </div>
        <button
          onClick={onRotate}
          disabled={rotating}
          className="mt-4 rounded-md border border-border px-4 py-2 text-sm text-foreground hover:bg-surface-2 disabled:opacity-60"
        >
          {rotating ? "Rotating…" : "Rotate API key"}
        </button>
        {error && <p className="mt-2 text-sm text-danger">{error}</p>}
      </div>

      {rotated && (
        <div className="rounded-lg border border-accent/40 bg-surface p-5">
          <p className="text-sm text-danger">New key generated — this is the only time it will be shown.</p>
          <div className="mt-4 flex flex-col gap-4">
            <CopyableField label="Connection string" value={rotated.connection_string} />
          </div>
        </div>
      )}
    </div>
  );
}

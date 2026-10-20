"use client";

import { useState } from "react";

export function CopyableField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  return (
    <div className="flex flex-col gap-1.5">
      <span className="text-xs text-muted">{label}</span>
      <div className="flex items-center gap-2">
        <code className="flex-1 truncate rounded-md border border-border bg-surface-2 px-3 py-2 font-mono text-xs text-foreground">
          {value}
        </code>
        <button
          onClick={copy}
          className="shrink-0 rounded-md border border-border px-3 py-2 text-xs text-foreground hover:bg-surface-2"
        >
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
    </div>
  );
}

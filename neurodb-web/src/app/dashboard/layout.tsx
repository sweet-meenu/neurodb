"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";
import { useAuth } from "@/lib/auth-context";

export default function DashboardLayout({ children }: { children: ReactNode }) {
  const { user, loading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!loading && !user) {
      router.replace("/login");
    }
  }, [loading, user, router]);

  if (loading || !user) {
    return (
      <div className="flex flex-1 items-center justify-center text-muted">
        <p className="text-sm">Loading…</p>
      </div>
    );
  }

  return (
    <div className="flex flex-1 flex-col">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <Link href="/dashboard" className="text-lg font-semibold tracking-tight">
          Neuro<span className="text-accent">DB</span>
        </Link>
        <div className="flex items-center gap-4 text-sm">
          <span className="text-muted">{user.email}</span>
          <button
            onClick={() => {
              logout();
              router.push("/");
            }}
            className="rounded-md border border-border px-3 py-1.5 text-foreground hover:bg-surface"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="flex flex-1 flex-col px-6 py-8 sm:px-10">{children}</main>
    </div>
  );
}

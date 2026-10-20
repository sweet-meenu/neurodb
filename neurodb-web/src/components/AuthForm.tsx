"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState, type FormEvent } from "react";
import { ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";

type Mode = "login" | "register";

export function AuthForm({ mode }: { mode: Mode }) {
  const { login, register } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (mode === "login") {
        await login(email, password);
      } else {
        await register(email, password);
      }
      router.push("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  const isLogin = mode === "login";

  return (
    <div className="flex flex-1 items-center justify-center px-6 py-16">
      <div className="w-full max-w-sm">
        <Link href="/" className="mb-8 block text-center text-lg font-semibold tracking-tight">
          Neuro<span className="text-accent">DB</span>
        </Link>
        <div className="rounded-lg border border-border bg-surface p-6">
          <h1 className="text-xl font-semibold">{isLogin ? "Sign in" : "Create your account"}</h1>
          <p className="mt-1 text-sm text-muted">
            {isLogin ? "Welcome back." : "One account, unlimited free NeuroDB projects."}
          </p>

          <form onSubmit={onSubmit} className="mt-6 flex flex-col gap-4">
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-muted">Email</span>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground outline-none focus:border-accent"
                placeholder="you@example.com"
              />
            </label>
            <label className="flex flex-col gap-1.5 text-sm">
              <span className="text-muted">Password</span>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="rounded-md border border-border bg-surface-2 px-3 py-2 text-foreground outline-none focus:border-accent"
                placeholder="At least 8 characters"
              />
            </label>

            {error && <p className="text-sm text-danger">{error}</p>}

            <button
              type="submit"
              disabled={submitting}
              className="mt-2 rounded-md bg-accent px-4 py-2 font-medium text-black hover:bg-accent-strong disabled:opacity-60"
            >
              {submitting ? "Please wait…" : isLogin ? "Sign in" : "Create account"}
            </button>
          </form>
        </div>

        <p className="mt-4 text-center text-sm text-muted">
          {isLogin ? (
            <>
              New to NeuroDB?{" "}
              <Link href="/register" className="text-accent hover:underline">
                Create an account
              </Link>
            </>
          ) : (
            <>
              Already have an account?{" "}
              <Link href="/login" className="text-accent hover:underline">
                Sign in
              </Link>
            </>
          )}
        </p>
      </div>
    </div>
  );
}

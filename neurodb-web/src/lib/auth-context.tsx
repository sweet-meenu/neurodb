"use client";

import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { apiFetch, clearStoredToken, getStoredToken, setStoredToken } from "@/lib/api";
import type { User } from "@/lib/types";

type AuthState = {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => void;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const stored = getStoredToken();
    if (!stored) {
      setLoading(false);
      return;
    }
    setToken(stored);
    apiFetch<User>("/api/control/auth/me", { token: stored })
      .then(setUser)
      .catch(() => {
        clearStoredToken();
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  async function login(email: string, password: string) {
    const res = await apiFetch<{ access_token: string }>("/api/control/auth/login", {
      method: "POST",
      body: { email, password },
      token: null,
    });
    setStoredToken(res.access_token);
    setToken(res.access_token);
    const me = await apiFetch<User>("/api/control/auth/me", { token: res.access_token });
    setUser(me);
  }

  async function register(email: string, password: string) {
    await apiFetch("/api/control/auth/register", {
      method: "POST",
      body: { email, password },
      token: null,
    });
    await login(email, password);
  }

  function logout() {
    clearStoredToken();
    setToken(null);
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, token, loading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

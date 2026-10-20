const API_BASE = process.env.NEXT_PUBLIC_NEURODB_API_URL ?? "http://localhost:8000";
const TOKEN_KEY = "neurodb_token";

export function getStoredToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token: string): void {
  window.localStorage.setItem(TOKEN_KEY, token);
}

export function clearStoredToken(): void {
  window.localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

type FetchOpts = {
  method?: "GET" | "POST" | "DELETE" | "PUT";
  body?: unknown;
  token?: string | null;
  formData?: FormData;
};

export async function apiFetch<T>(path: string, opts: FetchOpts = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = opts.token !== undefined ? opts.token : getStoredToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let body: BodyInit | undefined;
  if (opts.formData) {
    body = opts.formData;
  } else if (opts.body !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.body);
  }

  const res = await fetch(`${API_BASE}${path}`, {
    method: opts.method ?? "GET",
    headers,
    body,
  });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = data.detail ?? message;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, message);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export async function apiFetchBlob(path: string, opts: { token?: string | null } = {}): Promise<Blob> {
  const headers: Record<string, string> = {};
  const token = opts.token !== undefined ? opts.token : getStoredToken();
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${API_BASE}${path}`, { headers });

  if (!res.ok) {
    let message = res.statusText;
    try {
      const data = await res.json();
      message = data.detail ?? message;
    } catch {
      // response wasn't JSON — fall back to statusText
    }
    throw new ApiError(res.status, message);
  }

  return res.blob();
}

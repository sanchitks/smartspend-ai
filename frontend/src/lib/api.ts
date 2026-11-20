// Small fetch wrapper: adds the bearer token, unwraps the API's error envelope, refreshes tokens before expiry.
const BASE = (import.meta.env.VITE_API_URL ?? "http://localhost:8000").replace(/\/$/, "") + "/api/v1";
const TOKEN_KEY = "smartspend.token";
const EXPIRES_KEY = "smartspend.expires";

export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
    public details: { field?: string; issue?: string; message?: string }[] = [],
  ) {
    super(message);
  }
  fieldErrors(): Record<string, string> {
    const out: Record<string, string> = {};
    for (const d of this.details) if (d.field && !out[d.field]) out[d.field] = d.message ?? this.message;
    return out;
  }
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function getToken(): string | null {
  return read(TOKEN_KEY);
}

export function setToken(token: string | null, expiresAt?: string) {
  try {
    if (token) {
      localStorage.setItem(TOKEN_KEY, token);
      if (expiresAt) localStorage.setItem(EXPIRES_KEY, expiresAt);
    } else {
      localStorage.removeItem(TOKEN_KEY);
      localStorage.removeItem(EXPIRES_KEY);
    }
  } catch {
    /* storage unavailable: the session lasts for this tab only */
  }
}

let refreshing: Promise<void> | null = null;

async function maybeRefresh() {
  const token = getToken();
  const expires = read(EXPIRES_KEY);
  if (!token || !expires) return;
  const msLeft = new Date(expires).getTime() - Date.now();
  if (msLeft > 5 * 60_000 || msLeft <= 0) return;
  refreshing ??= fetch(`${BASE}/auth/refresh`, { method: "POST", headers: { Authorization: `Bearer ${token}` } })
    .then(async (r) => {
      if (r.ok) {
        const body = await r.json();
        setToken(body.access_token, body.expires_at);
      }
    })
    .catch(() => undefined)
    .finally(() => {
      refreshing = null;
    });
  await refreshing;
}

type Options = { method?: string; body?: unknown; query?: Record<string, unknown>; raw?: boolean };

export async function api<T>(path: string, opts: Options = {}): Promise<T> {
  if (!path.startsWith("/auth/refresh")) await maybeRefresh();
  const url = new URL(BASE + path);
  for (const [k, v] of Object.entries(opts.query ?? {})) {
    if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, String(v));
  }
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  if (opts.body !== undefined) headers["Content-Type"] = "application/json";
  let res: Response;
  try {
    res = await fetch(url, {
      method: opts.method ?? (opts.body !== undefined ? "POST" : "GET"),
      headers,
      body: opts.body !== undefined ? JSON.stringify(opts.body) : undefined,
    });
  } catch {
    throw new ApiError(0, "NETWORK", "Can't reach SmartSpend right now. Check your connection and try again.");
  }
  if (res.status === 401 && token) {
    setToken(null);
    window.dispatchEvent(new Event("smartspend:signed-out"));
  }
  if (!res.ok) {
    let body: { error?: { code: string; message: string; details?: [] } } = {};
    try {
      body = await res.json();
    } catch {
      /* not JSON */
    }
    const e = body.error;
    throw new ApiError(res.status, e?.code ?? "ERROR", e?.message ?? "Something went wrong. Please try again.", e?.details ?? []);
  }
  if (res.status === 204) return undefined as T;
  if (opts.raw) return (await res.text()) as T;
  return (await res.json()) as T;
}

export function errorMessage(e: unknown): string {
  return e instanceof ApiError ? e.message : "Something went wrong. Please try again.";
}

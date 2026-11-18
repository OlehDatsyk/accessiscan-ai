/**
 * Minimal typed API client. Access tokens are short-lived (30 min) and refreshed with a rotating refresh
 * token. Tokens are kept in localStorage so a reload keeps the session; the production CSP and the absence
 * of any raw-HTML rendering mitigate XSS token theft (see SECURITY.md).
 */

const API_BASE = (import.meta.env.VITE_API_URL ?? "").replace(/\/$/, "");
const ACCESS_KEY = "accessiscan.access";
const REFRESH_KEY = "accessiscan.refresh";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function read(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export const tokens = {
  get access() {
    return read(ACCESS_KEY);
  },
  get refresh() {
    return read(REFRESH_KEY);
  },
  set(access: string, refresh: string) {
    try {
      localStorage.setItem(ACCESS_KEY, access);
      localStorage.setItem(REFRESH_KEY, refresh);
    } catch {
      /* storage unavailable (private mode) - session lasts for this page only */
    }
  },
  clear() {
    try {
      localStorage.removeItem(ACCESS_KEY);
      localStorage.removeItem(REFRESH_KEY);
    } catch {
      /* ignore */
    }
  },
};

let refreshing: Promise<boolean> | null = null;
let onSessionExpired: (() => void) | null = null;
export function setSessionExpiredHandler(fn: () => void) {
  onSessionExpired = fn;
}

async function tryRefresh(): Promise<boolean> {
  const rt = tokens.refresh;
  if (!rt) return false;
  refreshing ??= (async () => {
    try {
      const r = await fetch(`${API_BASE}/api/v1/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: rt }),
      });
      if (!r.ok) return false;
      const data = await r.json();
      tokens.set(data.access_token, data.refresh_token);
      return true;
    } catch {
      return false;
    } finally {
      setTimeout(() => (refreshing = null), 0);
    }
  })();
  return refreshing;
}

async function parseError(r: Response): Promise<string> {
  try {
    const data = await r.json();
    if (typeof data.detail === "string") return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d: { msg?: string }) => d.msg).join("; ");
  } catch {
    /* not JSON */
  }
  if (r.status === 0 || r.status >= 500) return "The server is not responding. Please try again.";
  return `Request failed (${r.status})`;
}

export async function apiRaw(path: string, init: RequestInit = {}, retry = true): Promise<Response> {
  const headers = new Headers(init.headers);
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const at = tokens.access;
  if (at) headers.set("Authorization", `Bearer ${at}`);
  let r: Response;
  try {
    r = await fetch(`${API_BASE}/api/v1${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, "Cannot reach the AccessiScan API. Check your connection and that the backend is running.");
  }
  if (r.status === 401 && retry && tokens.refresh && !path.startsWith("/auth/")) {
    if (await tryRefresh()) return apiRaw(path, init, false);
    tokens.clear();
    onSessionExpired?.();
  }
  if (!r.ok) throw new ApiError(r.status, await parseError(r));
  return r;
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const r = await apiRaw(path, init);
  if (r.status === 204) return undefined as T;
  return (await r.json()) as T;
}

export const post = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) });
export const patch = <T>(path: string, body: unknown) => api<T>(path, { method: "PATCH", body: JSON.stringify(body) });
export const put = <T>(path: string, body: unknown) => api<T>(path, { method: "PUT", body: JSON.stringify(body) });
export const del = <T>(path: string, body?: unknown) =>
  api<T>(path, { method: "DELETE", body: body === undefined ? undefined : JSON.stringify(body) });

export async function downloadReport(id: string, filename: string) {
  const r = await apiRaw(`/reports/${id}/download`);
  const blob = await r.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function qs(params: Record<string, string | number | boolean | string[] | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === "") continue;
    if (Array.isArray(v)) v.forEach((x) => sp.append(k, x));
    else sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : "";
}

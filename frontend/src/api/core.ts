// Shared API core: base URL, bearer-token holder, 401 handling and the JSON
// `http` helper. Every api group imports from here so auth + error behaviour is
// uniform and defined once.
export const BASE = '/api/v1';

let _authToken: string | null = null;
export function setAuthToken(token: string | null): void {
  _authToken = token;
}
export function getAuthToken(): string | null {
  return _authToken;
}

let _onUnauthorized: (() => void) | null = null;
export function setClientUnauthorizedHandler(fn: (() => void) | null): void {
  _onUnauthorized = fn;
}

export async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(_authToken ? { Authorization: `Bearer ${_authToken}` } : {}),
    },
    ...init,
  });
  if (!res.ok) {
    if (res.status === 401 && _onUnauthorized) _onUnauthorized();
    throw new Error(`API ${res.status}: ${path}`);
  }
  return (await res.json()) as T;
}

export function newIdempotencyKey(): string {
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

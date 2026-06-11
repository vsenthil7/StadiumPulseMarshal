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

function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`));
  return m ? decodeURIComponent(m[1]) : null;
}

const _UNSAFE = new Set(['POST', 'PUT', 'PATCH', 'DELETE']);

export async function http<T>(path: string, init?: RequestInit): Promise<T> {
  const method = (init?.method ?? 'GET').toUpperCase();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(_authToken ? { Authorization: `Bearer ${_authToken}` } : {}),
    ...((init?.headers as Record<string, string>) ?? {}),
  };
  // Double-submit CSRF: echo the csrf cookie on state-changing requests. The
  // backend only enforces this when CSRF is enabled and the request isn't
  // bearer-authenticated, so it's harmless otherwise and lets CSRF be default-on
  // for cookie-auth deployments.
  if (_UNSAFE.has(method)) {
    const csrf = readCookie('csrf_token');
    if (csrf) headers['X-CSRF-Token'] = csrf;
  }
  const res = await fetch(`${BASE}${path}`, { ...init, method, headers });
  if (!res.ok) {
    if (res.status === 401 && _onUnauthorized) _onUnauthorized();
    throw new Error(`API ${res.status}: ${path}`);
  }
  return (await res.json()) as T;
}

export function newIdempotencyKey(): string {
  return `idem-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

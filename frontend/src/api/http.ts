/**
 * Resilient HTTP layer.
 *
 * - Parses the backend's standard error envelope into a typed ApiError.
 * - Retries idempotent (GET) requests on transient failures (network / 5xx /
 *   429) with bounded exponential backoff.
 * - Supports cancellation via AbortSignal; aborted requests reject with an
 *   ApiError of kind "aborted" and are never retried.
 */
const BASE = '/api/v1';

export interface ApiErrorShape {
  code: string;
  message: string;
  request_id?: string;
  trace_id?: string;
  details?: Record<string, unknown>;
}

export class ApiError extends Error {
  status: number;
  code: string;
  requestId?: string;
  traceId?: string;
  details?: Record<string, unknown>;
  aborted: boolean;

  constructor(
    status: number,
    envelope: Partial<ApiErrorShape>,
    aborted = false,
  ) {
    super(envelope.message || `API error ${status}`);
    this.name = 'ApiError';
    this.status = status;
    this.code = envelope.code || (aborted ? 'aborted' : 'error');
    this.requestId = envelope.request_id;
    this.traceId = envelope.trace_id;
    this.details = envelope.details;
    this.aborted = aborted;
  }
}

const RETRIABLE_STATUS = new Set([429, 500, 502, 503, 504]);

function sleep(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const t = setTimeout(resolve, ms);
    signal?.addEventListener('abort', () => {
      clearTimeout(t);
      reject(new ApiError(0, { message: 'aborted' }, true));
    });
  });
}

export interface RequestOptions extends RequestInit {
  signal?: AbortSignal;
  retries?: number;
  retryBaseMs?: number;
}

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    signal,
    retries = options.method && options.method !== 'GET' ? 0 : 2,
    retryBaseMs = 200,
    ...init
  } = options;

  let attempt = 0;
  // total tries = retries + 1
  for (;;) {
    try {
      const res = await fetch(`${BASE}${path}`, {
        headers: { 'Content-Type': 'application/json' },
        signal,
        ...init,
      });
      if (res.ok) {
        if (res.status === 204) return undefined as T;
        return (await res.json()) as T;
      }
      // Try to parse the standard error envelope.
      let envelope: Partial<ApiErrorShape> = {};
      try {
        const body = await res.json();
        envelope = body?.error ?? {};
      } catch {
        /* non-JSON error body */
      }
      const err = new ApiError(res.status, envelope);
      if (RETRIABLE_STATUS.has(res.status) && attempt < retries) {
        attempt += 1;
        await sleep(retryBaseMs * 2 ** (attempt - 1), signal);
        continue;
      }
      throw err;
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.aborted) throw e;
        throw e;
      }
      // Network-level failure (TypeError from fetch) — retry if budget remains.
      if (signal?.aborted) {
        throw new ApiError(0, { message: 'aborted' }, true);
      }
      if (attempt < retries) {
        attempt += 1;
        await sleep(retryBaseMs * 2 ** (attempt - 1), signal);
        continue;
      }
      throw new ApiError(0, { message: (e as Error).message, code: 'network' });
    }
  }
}

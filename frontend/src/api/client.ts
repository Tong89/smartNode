/**
 * client.ts — Typed API client for the smartNode backend.
 *
 * Provides a unified HTTP client that handles:
 * - Base URL resolution (localStorage / URL params / protocol detection)
 * - JSON encoding/decoding and envelope unwrapping
 * - HTTP error normalisation with human-readable messages
 * - AbortController-based request timeouts
 * - Optional Bearer token injection from localStorage
 */

import type { Envelope } from '../types/api';

/** Default request timeout in milliseconds. */
const DEFAULT_TIMEOUT_MS = 15_000;

/** Options accepted by the low-level `request` method. */
export interface RequestOptions extends Omit<RequestInit, 'signal'> {
  /** Override the per-request timeout (ms). Pass 0 to disable. */
  timeoutMs?: number;
}

/**
 * Resolve the backend base URL from (in priority order):
 *  1. `?api=<value>` query-string parameter
 *  2. `space_api_base` key in localStorage
 *  3. Fallback to `http://127.0.0.1:5000` when running from `file:` protocol
 *     or from a dev server port other than 5000.
 *  4. Empty string (same origin).
 */
export function resolveApiBase(): string {
  const params = new URLSearchParams(window.location.search);
  const configured = params.get('api') || localStorage.getItem('space_api_base');
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  if (
    window.location.protocol === 'file:' ||
    (window.location.port !== '' && window.location.port !== '5000')
  ) {
    return 'http://127.0.0.1:5000';
  }
  return '';
}

/**
 * Error thrown whenever the server returns a non-2xx status or the request
 * times out. `message` is always a human-readable string.
 */
export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status?: number,
    public readonly isTimeout = false,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

/**
 * Typed API client.  Instantiate once (or use the singleton `apiClient`)
 * and share across the application.
 */
export class ApiClient {
  private _baseUrl: string;
  private _defaultTimeoutMs: number;

  constructor(baseUrl?: string, defaultTimeoutMs = DEFAULT_TIMEOUT_MS) {
    this._baseUrl = baseUrl !== undefined ? baseUrl : resolveApiBase();
    this._defaultTimeoutMs = defaultTimeoutMs;
  }

  /** Current base URL (without trailing slash). */
  get baseUrl(): string {
    return this._baseUrl;
  }

  /** Update the base URL and persist it to localStorage if non-empty. */
  setBaseUrl(value: string): void {
    const normalized = (value || '').trim().replace(/\/$/, '');
    this._baseUrl = normalized === window.location.origin ? '' : normalized;
    if (this._baseUrl) {
      localStorage.setItem('space_api_base', this._baseUrl);
    } else {
      localStorage.removeItem('space_api_base');
    }
  }

  /** Build a fully-qualified URL for the given API path. */
  url(path: string): string {
    return `${this._baseUrl}${path}`;
  }

  /**
   * Execute an HTTP request and return the parsed JSON response.
   *
   * - Injects `Authorization: Bearer <token>` when `smartnode_token` is set
   *   in localStorage and no `Authorization` header was provided.
   * - Unwraps backend envelope `{ code: 0, data: T }` transparently.
   * - Throws `ApiError` on non-2xx responses or timeout.
   */
  async request<T>(path: string, options: RequestOptions = {}): Promise<T> {
    const { timeoutMs = this._defaultTimeoutMs, ...fetchOptions } = options;

    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
      ...((fetchOptions.headers as Record<string, string>) || {}),
    };

    const token = localStorage.getItem('smartnode_token');
    if (token && !headers['Authorization']) {
      headers['Authorization'] = `Bearer ${token}`;
    }

    let abortController: AbortController | undefined;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;

    if (timeoutMs > 0) {
      abortController = new AbortController();
      timeoutId = setTimeout(() => abortController!.abort(), timeoutMs);
    }

    let response: Response;
    try {
      response = await fetch(this.url(path), {
        ...fetchOptions,
        headers,
        signal: abortController?.signal,
      });
    } catch (err) {
      if (abortController?.signal.aborted) {
        throw new ApiError(`请求超时（${timeoutMs} ms）`, undefined, true);
      }
      throw new ApiError((err as Error).message || '网络请求失败');
    } finally {
      if (timeoutId !== undefined) clearTimeout(timeoutId);
    }

    const contentType = response.headers.get('content-type') || '';
    let payload: unknown;
    if (contentType.includes('application/json')) {
      payload = await response.json();
    } else {
      payload = await response.text();
    }

    if (!response.ok) {
      const message =
        typeof payload === 'string'
          ? payload
          : (
              (payload as Record<string, unknown>).message ||
              (payload as Record<string, unknown>).reject_reason ||
              (payload as Record<string, unknown>).error ||
              '请求失败'
            ) as string;
      throw new ApiError(message, response.status);
    }

    // Unwrap envelope `{ code: 0, data: T }` when present.
    if (
      payload !== null &&
      typeof payload === 'object' &&
      (payload as Envelope<T>).code === 0 &&
      'data' in (payload as object)
    ) {
      return (payload as Envelope<T>).data;
    }

    return payload as T;
  }

  /** Convenience GET helper. */
  get<T>(path: string, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, { ...options, method: 'GET' });
  }

  /** Convenience POST helper. */
  post<T>(path: string, body: unknown, options?: RequestOptions): Promise<T> {
    return this.request<T>(path, {
      ...options,
      method: 'POST',
      body: JSON.stringify(body),
    });
  }
}

/** Shared singleton — import and use this throughout the app. */
export const apiClient = new ApiClient();

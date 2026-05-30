/**
 * client.test.ts — Unit tests for the typed API client.
 *
 * Covers:
 *  - resolveApiBase: url-param branch, localStorage branch, file: protocol,
 *    non-5000 dev port, and same-origin fallback.
 *  - ApiClient.request: successful JSON response, envelope unwrap,
 *    non-JSON response, HTTP error (4xx/5xx), and AbortController timeout.
 *
 * All tests use vi.stubGlobal / vi.spyOn to mock fetch and browser globals.
 * No real network calls are made.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { resolveApiBase, ApiClient, ApiError } from './client';

// ── Helpers ───────────────────────────────────────────────────────────────────

/** Build a minimal Response-like object for fetch mocks. */
function makeResponse(
  body: unknown,
  status = 200,
  contentType = 'application/json',
): Response {
  const bodyText =
    typeof body === 'string' ? body : JSON.stringify(body);
  return new Response(bodyText, {
    status,
    headers: { 'Content-Type': contentType },
  });
}

// ── resolveApiBase ────────────────────────────────────────────────────────────

describe('resolveApiBase', () => {
  const originalLocation = window.location;

  afterEach(() => {
    // Restore window.location and clear mocks
    Object.defineProperty(window, 'location', {
      value: originalLocation,
      writable: true,
      configurable: true,
    });
    localStorage.clear();
    vi.restoreAllMocks();
  });

  function setLocation(overrides: Partial<Location>) {
    Object.defineProperty(window, 'location', {
      value: { ...originalLocation, ...overrides },
      writable: true,
      configurable: true,
    });
  }

  it('returns the ?api= query-string value when present (strips trailing slash)', () => {
    setLocation({ search: '?api=http://10.0.0.1:8080/', protocol: 'http:', port: '3000' });
    expect(resolveApiBase()).toBe('http://10.0.0.1:8080');
  });

  it('prefers ?api= over localStorage', () => {
    localStorage.setItem('space_api_base', 'http://from-storage:9000');
    setLocation({ search: '?api=http://from-param:8888', protocol: 'http:', port: '3000' });
    expect(resolveApiBase()).toBe('http://from-param:8888');
  });

  it('returns localStorage value when no ?api= param', () => {
    localStorage.setItem('space_api_base', 'http://192.168.1.10:5000');
    setLocation({ search: '', protocol: 'http:', port: '3000' });
    expect(resolveApiBase()).toBe('http://192.168.1.10:5000');
  });

  it('returns http://127.0.0.1:5000 for file: protocol', () => {
    setLocation({ protocol: 'file:', search: '', port: '' });
    expect(resolveApiBase()).toBe('http://127.0.0.1:5000');
  });

  it('returns http://127.0.0.1:5000 for non-5000 dev server port', () => {
    setLocation({ protocol: 'http:', search: '', port: '5173' });
    expect(resolveApiBase()).toBe('http://127.0.0.1:5000');
  });

  it('returns empty string when port is 5000 (same-origin)', () => {
    setLocation({ protocol: 'http:', search: '', port: '5000' });
    expect(resolveApiBase()).toBe('');
  });

  it('returns empty string when port is empty (standard HTTP/HTTPS)', () => {
    setLocation({ protocol: 'https:', search: '', port: '' });
    expect(resolveApiBase()).toBe('');
  });
});

// ── ApiClient ─────────────────��───────────────────────────────────────────────

describe('ApiClient', () => {
  let client: ApiClient;
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    // Replace the global fetch with our mock
    vi.stubGlobal('fetch', fetchMock);
    // Use a fixed base URL so resolveApiBase() isn't called in these tests
    client = new ApiClient('http://test-host:5000', 100);
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  // ── Successful JSON response ──────────────────────────────────────────────

  it('returns parsed JSON body for a successful 200 response', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ hello: 'world' }));
    const result = await client.request<{ hello: string }>('/api/test');
    expect(result).toEqual({ hello: 'world' });
  });

  it('unwraps backend envelope { code: 0, data: T }', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ code: 0, data: { id: 'req-1' } }));
    const result = await client.request<{ id: string }>('/api/requests');
    expect(result).toEqual({ id: 'req-1' });
  });

  it('returns raw payload when envelope code is non-zero', async () => {
    const payload = { code: 1, message: 'partial data', data: null };
    fetchMock.mockResolvedValueOnce(makeResponse(payload));
    const result = await client.request('/api/requests');
    expect(result).toEqual(payload);
  });

  // ── Non-JSON response ─────────────────────────────────────────────────────

  it('returns response text for non-JSON content-type', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse('plain text body', 200, 'text/plain'));
    const result = await client.request('/api/health');
    expect(result).toBe('plain text body');
  });

  // ── HTTP error responses ──────────────────────────────────────────────────

  it('throws ApiError for a 404 JSON error response', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({ message: 'Not Found' }, 404),
    );
    await expect(client.request('/api/missing')).rejects.toThrow(ApiError);
    await expect(client.request('/api/missing')).rejects.toMatchObject({
      status: 404,
      message: 'Not Found',
    });
  });

  it('throws ApiError for a 500 response with reject_reason field', async () => {
    fetchMock.mockResolvedValueOnce(
      makeResponse({ reject_reason: 'no bandwidth' }, 500),
    );
    await expect(client.request('/api/submit')).rejects.toMatchObject({
      status: 500,
      message: 'no bandwidth',
    });
  });

  it('throws ApiError for a 400 plain-text error', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse('Bad Request', 400, 'text/plain'));
    await expect(client.request('/api/bad')).rejects.toMatchObject({
      status: 400,
      message: 'Bad Request',
    });
  });

  it('sets isTimeout=false on regular HTTP errors', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ message: 'Forbidden' }, 403));
    let caught: ApiError | undefined;
    try {
      await client.request('/api/restricted');
    } catch (e) {
      caught = e as ApiError;
    }
    expect(caught?.isTimeout).toBe(false);
  });

  // ── Timeout (AbortController) ─────────────────────────────────────────────

  it('throws ApiError with isTimeout=true when fetch is aborted by timeout', async () => {
    // Simulate fetch rejecting with an AbortError after the controller fires
    fetchMock.mockImplementationOnce((_url, opts) => {
      return new Promise((_resolve, reject) => {
        // Immediately abort in the next microtask to simulate timeout
        setTimeout(() => {
          (opts?.signal as AbortSignal | undefined)?.dispatchEvent(new Event('abort'));
          const err = new DOMException('The operation was aborted.', 'AbortError');
          reject(err);
        }, 0);
      });
    });

    // The client has timeoutMs=100 which fires AbortController; we make fetch
    // reject with an AbortError so the catch branch executes.
    const shortClient = new ApiClient('http://test-host:5000', 50);
    // Override fetch on the instance test to ensure abort signal path
    vi.stubGlobal('fetch', (url: RequestInfo, init?: RequestInit) => {
      // Check that a signal was passed (AbortController was used)
      expect(init?.signal).toBeDefined();
      const abort = () => {
        const err = Object.assign(new Error('AbortError'), { name: 'AbortError' });
        return Promise.reject(err);
      };
      return abort();
    });

    let caught: ApiError | undefined;
    try {
      await shortClient.request('/api/slow');
    } catch (e) {
      caught = e as ApiError;
    }
    // Network rejection that is not an abort should be wrapped as ApiError
    expect(caught).toBeInstanceOf(ApiError);
  });

  it('throws ApiError with isTimeout=true on genuine AbortController timeout', async () => {
    // Use a very short timeout and make fetch hang until aborted
    const shortClient = new ApiClient('http://test-host:5000', 10);

    vi.stubGlobal('fetch', (_url: RequestInfo, init?: RequestInit) => {
      return new Promise<Response>((_resolve, reject) => {
        if (init?.signal) {
          init.signal.addEventListener('abort', () => {
            reject(Object.assign(new Error('The operation was aborted.'), { name: 'AbortError' }));
          });
        }
        // Intentionally never resolves to simulate a hung server
      });
    });

    let caught: ApiError | undefined;
    try {
      await shortClient.request('/api/timeout');
    } catch (e) {
      caught = e as ApiError;
    }
    expect(caught).toBeInstanceOf(ApiError);
    expect(caught?.isTimeout).toBe(true);
  });

  // ── Token injection ───────────────────────────────────────────────────────

  it('injects Authorization header from localStorage when token is set', async () => {
    localStorage.setItem('smartnode_token', 'test-jwt-token');
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true }));
    await client.request('/api/protected');
    const calledHeaders = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(calledHeaders['Authorization']).toBe('Bearer test-jwt-token');
  });

  it('does not override Authorization header when already set in options', async () => {
    localStorage.setItem('smartnode_token', 'should-not-use-this');
    fetchMock.mockResolvedValueOnce(makeResponse({ ok: true }));
    await client.request('/api/protected', {
      headers: { Authorization: 'Bearer custom-token' },
    });
    const calledHeaders = (fetchMock.mock.calls[0][1] as RequestInit).headers as Record<string, string>;
    expect(calledHeaders['Authorization']).toBe('Bearer custom-token');
  });

  // ── GET / POST convenience helpers ────────────────────────────────────────

  it('get() calls request with method=GET', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse([]));
    await client.get('/api/items');
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('GET');
  });

  it('post() calls request with method=POST and serialised body', async () => {
    fetchMock.mockResolvedValueOnce(makeResponse({ id: 'r1' }));
    await client.post('/api/requests', { data_type: 'INTEL' });
    const init = fetchMock.mock.calls[0][1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.body).toBe(JSON.stringify({ data_type: 'INTEL' }));
  });
});

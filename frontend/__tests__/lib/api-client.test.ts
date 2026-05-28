/**
 * Unit tests for lib/api/client.ts
 *
 * Tests apiRequest() and apiUpload() in full isolation — global.fetch is
 * mocked so no real network calls happen.
 *
 * IMPORTANT: client.ts reads AXIS_AI_URL and AXIS_AI_KEY at MODULE INIT TIME
 * (module-level constants).  We must set process.env BEFORE the dynamic
 * import so the module picks up the test values.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';

// ─── Set env vars BEFORE importing the module ─────────────────────────────
// client.ts caches these as top-level constants on first import.
process.env.AXIS_AI_URL = 'http://api.test:8000';
process.env.AXIS_AI_KEY = 'axai_test_key_12345';

const { ApiError, apiRequest, apiUpload } = await import('@/lib/api/client');

const FAKE_API_URL = 'http://api.test:8000';
const FAKE_API_KEY = 'axai_test_key_12345';

// ─── ApiError class ──────────────────────────────────────────────────────────

describe('ApiError', () => {
  it('stores status and detail', () => {
    const err = new ApiError(404, 'Not found');
    expect(err.status).toBe(404);
    expect(err.detail).toBe('Not found');
    expect(err.name).toBe('ApiError');
    expect(err instanceof Error).toBe(true);
  });

  it('accepts optional custom message', () => {
    const err = new ApiError(500, 'detail msg', 'custom message');
    expect(err.message).toBe('custom message');
  });

  it('uses detail as message when no custom message provided', () => {
    const err = new ApiError(422, 'Validation failed');
    expect(err.message).toBe('Validation failed');
  });
});

// ─── apiRequest ──────────────────────────────────────────────────────────────

describe('apiRequest()', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('makes a GET request with tenant API key when no jwtToken', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'ok' }),
    });

    const result = await apiRequest('/api/v1/health');

    expect(global.fetch).toHaveBeenCalledOnce();
    const [url, options] = (global.fetch as any).mock.calls[0];
    expect(url).toBe(`${FAKE_API_URL}/api/v1/health`);
    expect(options.method).toBe('GET');
    expect(options.headers['Authorization']).toBe(`Bearer ${FAKE_API_KEY}`);
    expect(options.headers['X-Requested-With']).toBe('axis-frontend');
    expect(result).toEqual({ status: 'ok' });
  });

  it('uses Bearer jwtToken when provided (overrides API key)', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ user: 'me' }),
    });

    await apiRequest('/api/v1/auth/me', { jwtToken: 'user-jwt-abc' });

    const [, options] = (global.fetch as any).mock.calls[0];
    expect(options.headers['Authorization']).toBe('Bearer user-jwt-abc');
  });

  it('sends JSON body on POST', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ id: 'new-space' }),
    });

    await apiRequest('/api/v1/spaces', {
      method: 'POST',
      body: { name: 'Test Space' },
    });

    const [, options] = (global.fetch as any).mock.calls[0];
    expect(options.method).toBe('POST');
    expect(options.body).toBe(JSON.stringify({ name: 'Test Space' }));
    expect(options.headers['Content-Type']).toBe('application/json');
  });

  it('returns undefined on 204 No Content', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 204,
      json: async () => { throw new Error('should not parse body'); },
    });

    const result = await apiRequest('/api/v1/spaces/123', { method: 'DELETE' });
    expect(result).toBeUndefined();
  });

  it('throws ApiError with status and detail on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      json: async () => ({ detail: 'Forbidden — insufficient permissions' }),
    });

    await expect(apiRequest('/api/v1/admin/users')).rejects.toThrow(ApiError);
    await expect(apiRequest('/api/v1/admin/users')).rejects.toMatchObject({
      status: 403,
      detail: 'Forbidden — insufficient permissions',
    });
  });

  it('falls back to HTTP status string when error body is not JSON', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 502,
      json: async () => { throw new SyntaxError('Not JSON'); },
    });

    await expect(apiRequest('/api/v1/health')).rejects.toMatchObject({
      status: 502,
      detail: 'HTTP 502',
    });
  });

  it('throws ApiError 504 on request timeout', async () => {
    global.fetch = vi.fn().mockImplementation(
      (_url: string, { signal }: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener('abort', () => {
            const err = Object.assign(new Error('aborted'), { name: 'AbortError' });
            reject(err);
          });
          setTimeout(() => signal.dispatchEvent(new Event('abort')), 0);
        })
    );

    await expect(apiRequest('/api/v1/health', { timeoutMs: 1 })).rejects.toMatchObject({
      status: 504,
      detail: expect.stringContaining('timed out'),
    });
  });

  it('sets cache: no-store on every request', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });

    await apiRequest('/api/v1/health');

    const [, options] = (global.fetch as any).mock.calls[0];
    expect(options.cache).toBe('no-store');
  });

  it('passes custom headers through', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });

    await apiRequest('/api/v1/health', {
      headers: { 'X-Custom-Header': 'hello' },
    });

    const [, options] = (global.fetch as any).mock.calls[0];
    expect(options.headers['X-Custom-Header']).toBe('hello');
  });
});

// ─── apiUpload ───────────────────────────────────────────────────────────────

describe('apiUpload()', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('sends multipart FormData without Content-Type header (browser sets boundary)', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ job_id: 'abc-123' }),
    });

    const formData = new FormData();
    formData.append(
      'file',
      new Blob(['pdf-content'], { type: 'application/pdf' }),
      'test.pdf'
    );

    const result = await apiUpload('/api/v1/ingest/file', formData, 'user-jwt-abc');

    expect(global.fetch).toHaveBeenCalledOnce();
    const [url, options] = (global.fetch as any).mock.calls[0];
    expect(url).toBe(`${FAKE_API_URL}/api/v1/ingest/file`);
    expect(options.method).toBe('POST');
    expect(options.headers['Authorization']).toBe('Bearer user-jwt-abc');
    // Content-Type must NOT be set — fetch sets the multipart boundary automatically
    expect(options.headers['Content-Type']).toBeUndefined();
    expect(result).toEqual({ job_id: 'abc-123' });
  });

  it('uses tenant API key when no jwtToken passed', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({}),
    });

    await apiUpload('/api/v1/ingest/file', new FormData());

    const [, options] = (global.fetch as any).mock.calls[0];
    expect(options.headers['Authorization']).toBe(`Bearer ${FAKE_API_KEY}`);
  });

  it('throws ApiError on non-ok response', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: false,
      status: 413,
      json: async () => ({ detail: 'File too large' }),
    });

    await expect(
      apiUpload('/api/v1/ingest/file', new FormData(), 'jwt')
    ).rejects.toMatchObject({ status: 413, detail: 'File too large' });
  });

  it('throws ApiError 504 on upload timeout', async () => {
    global.fetch = vi.fn().mockImplementation(
      (_url: string, { signal }: { signal: AbortSignal }) =>
        new Promise((_resolve, reject) => {
          signal.addEventListener('abort', () => {
            const err = Object.assign(new Error('aborted'), { name: 'AbortError' });
            reject(err);
          });
          setTimeout(() => signal.dispatchEvent(new Event('abort')), 0);
        })
    );

    await expect(
      apiUpload('/api/v1/ingest/file', new FormData(), 'jwt', 1)
    ).rejects.toMatchObject({ status: 504 });
  });
});

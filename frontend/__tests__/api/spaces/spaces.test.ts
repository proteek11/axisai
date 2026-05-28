/**
 * Unit tests for /api/spaces (GET list + POST create)
 *
 * next/server + next/headers are aliased to stubs in vitest.config.ts.
 * cookies() from our stub is already a vi.fn() — we control it per-test
 * by calling vi.mocked(cookies).mockReturnValue(...).
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { buildCookieStore, mockFetchOk, mockFetchError } from '@/__tests__/helpers/setup';
import { GET, POST } from '@/app/api/spaces/route';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const SPACE_LIST = {
  items: [
    { id: 'sp1', name: 'ML Fundamentals', role: 'creator', item_count: 5 },
    { id: 'sp2', name: 'Python Basics', role: 'creator', item_count: 12 },
  ],
  total: 2,
};

const NEW_SPACE_PAYLOAD = { name: 'New Course Space', description: 'For testing' };
const NEW_SPACE_RESPONSE = { id: 'sp-new', ...NEW_SPACE_PAYLOAD, item_count: 0 };

function makeGetRequest(params: Record<string, string> = {}) {
  const url = new URL('http://localhost:3000/api/spaces');
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  return new NextRequest(url.toString(), { method: 'GET' });
}

function makePostRequest(body: unknown) {
  return new NextRequest('http://localhost:3000/api/spaces', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('GET /api/spaces', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'creator-jwt' }) as any);
  });

  it('returns space list from FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(SPACE_LIST));

    const res = await GET(makeGetRequest());
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.items).toHaveLength(2);
    expect(body.total).toBe(2);
  });

  it('calls FastAPI with correct URL and auth header', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(SPACE_LIST));

    await GET(makeGetRequest());

    const [url, opts] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/spaces');
    expect(opts.headers['Authorization']).toBe('Bearer creator-jwt');
  });

  it('passes limit and offset query params to FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(SPACE_LIST));

    await GET(makeGetRequest({ limit: '10', offset: '20' }));

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('limit=10');
    expect(url).toContain('offset=20');
  });

  it('uses default limit=50 and offset=0 when no params', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(SPACE_LIST));

    await GET(makeGetRequest());

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('limit=50');
    expect(url).toContain('offset=0');
  });

  it('returns error response when FastAPI fails', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(503, 'Service unavailable'));

    const res = await GET(makeGetRequest());
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toBeDefined();
  });

  it('works when no access token cookie is set', async () => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({}) as any);
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(SPACE_LIST));

    await GET(makeGetRequest());
    expect(global.fetch).toHaveBeenCalled();
  });
});

describe('POST /api/spaces', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'creator-jwt' }) as any);
  });

  it('creates a space and returns the new record', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(NEW_SPACE_RESPONSE));

    const res = await POST(makePostRequest(NEW_SPACE_PAYLOAD));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.id).toBe('sp-new');
    expect(body.name).toBe('New Course Space');
  });

  it('forwards the request body to FastAPI as JSON', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(NEW_SPACE_RESPONSE));

    await POST(makePostRequest(NEW_SPACE_PAYLOAD));

    const [, opts] = (global.fetch as any).mock.calls[0];
    expect(opts.method).toBe('POST');
    // body passes through apiRequest's JSON.stringify — verify key content is present
    expect(opts.body).toContain('New Course Space');
  });

  it('returns 422 error when FastAPI validation fails', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(422, 'Field required: name'));

    const res = await POST(makePostRequest({}));
    expect(res.status).toBe(422);
  });

  it('returns 403 when user lacks creator/admin role', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(403, 'Insufficient permissions'));

    const res = await POST(makePostRequest(NEW_SPACE_PAYLOAD));
    expect(res.status).toBe(403);
    const body = await res.json();
    expect(body.error).toBeDefined();
  });
});

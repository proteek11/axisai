/**
 * Unit tests for /api/spaces/[id] (GET, PUT, DELETE)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { buildCookieStore, mockFetchOk, mockFetchError } from '@/__tests__/helpers/setup';
import { GET, PUT, DELETE } from '@/app/api/spaces/[id]/route';

// ─── Fixtures ────────────────────────────────────────────────────────────────

const SPACE = { id: 'sp1', name: 'ML Fundamentals', description: 'Intro to ML', item_count: 5 };
const SPACE_PARAMS = { params: { id: 'sp1' } };

function makeRequest(method: string, body?: unknown) {
  return new NextRequest('http://localhost:3000/api/spaces/sp1', {
    method,
    headers: body ? { 'content-type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
}

// ─── Tests ───────────────────────────────────────────────────────────────────

describe('GET /api/spaces/[id]', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'creator-jwt' }) as any);
  });

  it('returns the space record', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(SPACE));

    const res = await GET(makeRequest('GET'), SPACE_PARAMS);
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.id).toBe('sp1');
    expect(body.name).toBe('ML Fundamentals');
  });

  it('calls FastAPI with the correct space ID in URL', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(SPACE));

    await GET(makeRequest('GET'), SPACE_PARAMS);

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/spaces/sp1');
  });

  it('returns 404 when space not found', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(404, 'Space not found'));

    const res = await GET(makeRequest('GET'), SPACE_PARAMS);
    expect(res.status).toBe(404);
  });
});

describe('PUT /api/spaces/[id]', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'creator-jwt' }) as any);
  });

  const UPDATE_BODY = { name: 'ML Fundamentals — Updated', description: 'Advanced ML' };

  it('updates and returns the space', async () => {
    const updated = { ...SPACE, ...UPDATE_BODY };
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(updated));

    const res = await PUT(makeRequest('PUT', UPDATE_BODY), SPACE_PARAMS);
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.name).toBe('ML Fundamentals — Updated');
  });

  it('sends PUT with the updated body to FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk({ ...SPACE, ...UPDATE_BODY }));

    await PUT(makeRequest('PUT', UPDATE_BODY), SPACE_PARAMS);

    const [url, opts] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/spaces/sp1');
    expect(opts.method).toBe('PUT');
    // body passes through apiRequest's JSON.stringify — verify key content is present
    expect(opts.body).toContain('ML Fundamentals');
  });

  it('returns 403 when requester is not the space owner', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(403, 'Not the space owner'));

    const res = await PUT(makeRequest('PUT', UPDATE_BODY), SPACE_PARAMS);
    expect(res.status).toBe(403);
  });
});

describe('DELETE /api/spaces/[id]', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'creator-jwt' }) as any);
  });

  it('returns { success: true } on successful delete', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });

    const res = await DELETE(makeRequest('DELETE'), SPACE_PARAMS);
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.success).toBe(true);
  });

  it('sends DELETE to the correct FastAPI URL', async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => ({}) });

    await DELETE(makeRequest('DELETE'), SPACE_PARAMS);

    const [url, opts] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/spaces/sp1');
    expect(opts.method).toBe('DELETE');
  });

  it('returns error when FastAPI returns 404', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(404, 'Space not found'));

    const res = await DELETE(makeRequest('DELETE'), SPACE_PARAMS);
    expect(res.status).toBe(404);
  });
});

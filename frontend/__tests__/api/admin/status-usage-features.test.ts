/**
 * Unit tests for admin routes:
 *   GET /api/admin/status
 *   GET /api/admin/usage
 *   GET /api/admin/features
 *   PUT /api/admin/features
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { buildCookieStore, mockFetchOk, mockFetchError } from '@/__tests__/helpers/setup';
import { GET as statusGET } from '@/app/api/admin/status/route';
import { GET as usageGET } from '@/app/api/admin/usage/route';
import { GET as featuresGET, PUT as featuresPUT } from '@/app/api/admin/features/route';

// ─── Status ──────────────────────────────────────────────────────────────────

describe('GET /api/admin/status', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  it('returns system status from FastAPI', async () => {
    const STATUS = { api: 'healthy', db: 'healthy', qdrant: 'healthy', redis: 'healthy', uptime_seconds: 86400 };
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(STATUS));

    const res = await statusGET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.api).toBe('healthy');
    expect(body.db).toBe('healthy');
  });

  it('calls the correct FastAPI endpoint', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk({ api: 'healthy' }));

    await statusGET();

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/admin/status');
  });

  it('returns error when FastAPI is unreachable', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(503, 'Backend unavailable'));

    const res = await statusGET();
    expect(res.status).toBe(503);
    const body = await res.json();
    expect(body.error).toBeDefined();
  });
});

// ─── Usage ───────────────────────────────────────────────────────────────────

describe('GET /api/admin/usage', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  const USAGE_DATA = { period: '7d', total_tokens: 125000, total_requests: 800, by_user: [] };

  it('returns usage data for the default 7d period', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(USAGE_DATA));

    const res = await usageGET(new NextRequest('http://localhost:3000/api/admin/usage'));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.total_tokens).toBe(125000);
  });

  it('passes custom period query param to FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk({ ...USAGE_DATA, period: '30d' }));

    await usageGET(new NextRequest('http://localhost:3000/api/admin/usage?period=30d'));

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('period=30d');
  });

  it('defaults to period=7d when no query param', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(USAGE_DATA));

    await usageGET(new NextRequest('http://localhost:3000/api/admin/usage'));

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('period=7d');
  });

  it('returns 500 on unexpected error', async () => {
    global.fetch = vi.fn().mockRejectedValue(new Error('Redis down'));

    const res = await usageGET(new NextRequest('http://localhost:3000/api/admin/usage'));
    expect(res.status).toBe(500);
  });
});

// ─── Features ────────────────────────────────────────────────────────────────

describe('GET /api/admin/features', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  const FEATURES = { quiz_enabled: true, flashcards_enabled: true, mindmap_enabled: false, chat_enabled: true };

  it('returns feature flags from FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(FEATURES));

    const res = await featuresGET();
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.quiz_enabled).toBe(true);
    expect(body.mindmap_enabled).toBe(false);
  });

  it('returns error when FastAPI errors', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(500, 'DB error'));

    const res = await featuresGET();
    expect(res.status).toBe(500);
    const body = await res.json();
    expect(body.error).toBeDefined();
  });
});

describe('PUT /api/admin/features', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  const FEATURES_AFTER = { quiz_enabled: true, flashcards_enabled: true, mindmap_enabled: true, chat_enabled: true };

  it('updates features and returns the updated config', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(FEATURES_AFTER));

    const req = new NextRequest('http://localhost:3000/api/admin/features', {
      method: 'PUT',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ mindmap_enabled: true }),
    });
    const res = await featuresPUT(req);
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.mindmap_enabled).toBe(true);
  });

  it('sends PUT request with updated flags to FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(FEATURES_AFTER));

    await featuresPUT(
      new NextRequest('http://localhost:3000/api/admin/features', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ mindmap_enabled: true }),
      })
    );

    const [url, opts] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/admin/features');
    expect(opts.method).toBe('PUT');
    // body passes through apiRequest's JSON.stringify — verify key content is present
    expect(opts.body).toContain('mindmap_enabled');
  });

  it('returns 403 when non-admin calls this endpoint', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(403, 'Admin role required'));

    const res = await featuresPUT(
      new NextRequest('http://localhost:3000/api/admin/features', {
        method: 'PUT',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ mindmap_enabled: true }),
      })
    );
    expect(res.status).toBe(403);
  });
});

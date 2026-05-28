/**
 * Unit tests for admin routes:
 *   GET  /api/admin/kb
 *   POST /api/admin/kb
 *   GET  /api/admin/audit
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { buildCookieStore, mockFetchOk, mockFetchError } from '@/__tests__/helpers/setup';
import { GET as kbGET, POST as kbPOST } from '@/app/api/admin/kb/route';
import { GET as auditGET } from '@/app/api/admin/audit/route';

// ─── Knowledge Base ───────────────────────────────────────────────────────────

describe('GET /api/admin/kb', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  const KB_ITEMS = [
    { id: 'kb1', title: 'Refund Policy', content: 'Full refund within 30 days', type: 'policy' },
    { id: 'kb2', title: 'Getting Started', content: 'Welcome to EDZLMS', type: 'guide' },
  ];

  it('returns KB items list', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(KB_ITEMS));

    const res = await kbGET(new NextRequest('http://localhost:3000/api/admin/kb'));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(Array.isArray(body)).toBe(true);
    expect(body).toHaveLength(2);
  });

  it('passes search query and limit to FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(KB_ITEMS));

    await kbGET(new NextRequest('http://localhost:3000/api/admin/kb?q=refund&limit=10'));

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('q=refund');
    expect(url).toContain('limit=10');
  });

  it('uses default limit=50 and empty query when no params', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk([]));

    await kbGET(new NextRequest('http://localhost:3000/api/admin/kb'));

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('limit=50');
  });

  it('returns error on FastAPI failure', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(500, 'Qdrant unavailable'));

    const res = await kbGET(new NextRequest('http://localhost:3000/api/admin/kb'));
    expect(res.status).toBe(500);
  });
});

describe('POST /api/admin/kb', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  const KB_NEW_BODY = { title: 'Payment FAQ', content: 'Q: How do I pay? A: Credit card or UPI.', type: 'faq' };
  const KB_NEW_RESPONSE = { id: 'kb3', ...KB_NEW_BODY, chunk_count: 2 };

  it('creates a KB item and returns the response', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(KB_NEW_RESPONSE));

    const res = await kbPOST(
      new NextRequest('http://localhost:3000/api/admin/kb', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(KB_NEW_BODY),
      })
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.id).toBe('kb3');
    expect(body.title).toBe('Payment FAQ');
  });

  it('forwards KB content to FastAPI as JSON', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(KB_NEW_RESPONSE));

    await kbPOST(
      new NextRequest('http://localhost:3000/api/admin/kb', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify(KB_NEW_BODY),
      })
    );

    const [url, opts] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/kb');
    expect(opts.method).toBe('POST');
    // body passes through apiRequest's JSON.stringify — verify key content is present
    expect(opts.body).toContain('Payment FAQ');
  });

  it('returns 422 on validation failure', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(422, 'Content is required'));

    const res = await kbPOST(
      new NextRequest('http://localhost:3000/api/admin/kb', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ title: 'Incomplete' }),
      })
    );
    expect(res.status).toBe(422);
  });
});

// ─── Audit Log ───────────────────────────────────────────────────────────────

describe('GET /api/admin/audit', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(buildCookieStore({ axis_access: 'admin-jwt' }) as any);
  });

  const AUDIT_ENTRIES = [
    { id: 'a1', action: 'user.create', actor: 'admin@edzlms.com', ts: '2026-05-09T10:00:00Z' },
    { id: 'a2', action: 'space.delete', actor: 'creator@edzlms.com', ts: '2026-05-09T09:00:00Z' },
    { id: 'a3', action: 'feature.update', actor: 'admin@edzlms.com', ts: '2026-05-09T08:00:00Z' },
  ];

  it('returns audit log entries', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(AUDIT_ENTRIES));

    const res = await auditGET(new NextRequest('http://localhost:3000/api/admin/audit'));
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body).toHaveLength(3);
    expect(body[0].action).toBe('user.create');
  });

  it('passes limit and offset to FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk([]));

    await auditGET(new NextRequest('http://localhost:3000/api/admin/audit?limit=50&offset=100'));

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('limit=50');
    expect(url).toContain('offset=100');
  });

  it('uses default limit=100 and offset=0', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk([]));

    await auditGET(new NextRequest('http://localhost:3000/api/admin/audit'));

    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('limit=100');
    expect(url).toContain('offset=0');
  });

  it('returns 403 when non-admin calls this endpoint', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(403, 'Admin only'));

    const res = await auditGET(new NextRequest('http://localhost:3000/api/admin/audit'));
    expect(res.status).toBe(403);
  });
});

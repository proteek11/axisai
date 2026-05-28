/**
 * Unit tests for POST /api/content/ingest
 *
 * Handles two content types:
 *  1. JSON body  → URL / structured ingest  → apiRequest('/api/v1/ingest')
 *  2. Multipart  → File upload              → apiUpload('/api/v1/ingest/file')
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { NextRequest } from 'next/server';
import { cookies } from 'next/headers';
import { buildCookieStore, mockFetchOk, mockFetchError } from '@/__tests__/helpers/setup';
import { POST } from '@/app/api/content/ingest/route';

const CREATOR_TOKEN = 'creator-jwt-xyz';

const INGEST_JOB = {
  job_id: 'job-abc-123',
  status: 'queued',
  content_type: 'youtube',
  created_at: '2026-05-09T10:00:00Z',
};

function makeJsonIngestRequest(body: unknown) {
  return new NextRequest('http://localhost:3000/api/content/ingest', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
}

// ─── JSON / URL ingest ────────────────────────────────────────────────────────

describe('POST /api/content/ingest — JSON (URL / structured)', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(
      buildCookieStore({ axis_access: CREATOR_TOKEN }) as any
    );
  });

  it('ingests a YouTube URL and returns a job record', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(INGEST_JOB));

    const res = await POST(
      makeJsonIngestRequest({
        space_id: 'sp1',
        content_type: 'youtube',
        source_url: 'https://www.youtube.com/watch?v=dQw4w9WgXcQ',
        outputs: ['summary', 'quiz'],
      })
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.job_id).toBe('job-abc-123');
    expect(body.status).toBe('queued');
  });

  it('routes JSON ingest to /api/v1/ingest (not /ingest/file)', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(INGEST_JOB));

    await POST(
      makeJsonIngestRequest({ space_id: 'sp1', content_type: 'youtube', source_url: 'https://...' })
    );

    const [url, opts] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/ingest');
    expect(url).not.toContain('/ingest/file');
    expect(opts.method).toBe('POST');
  });

  it('ingests a Moodle page URL', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk({ ...INGEST_JOB, content_type: 'page' }));

    const res = await POST(
      makeJsonIngestRequest({
        space_id: 'sp1',
        content_type: 'page',
        source_url: 'https://moodle.example.com/mod/page/view.php?id=42',
        outputs: ['summary'],
      })
    );
    const body = await res.json();

    expect(res.status).toBe(200);
    expect(body.content_type).toBe('page');
  });

  it('sends auth token to FastAPI', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk(INGEST_JOB));

    await POST(makeJsonIngestRequest({ space_id: 'sp1', content_type: 'youtube', source_url: 'x' }));

    const [, opts] = (global.fetch as any).mock.calls[0];
    expect(opts.headers['Authorization']).toBe(`Bearer ${CREATOR_TOKEN}`);
  });

  it('returns 400 when FastAPI rejects the content type', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(400, 'Unsupported content_type: podcast'));

    const res = await POST(
      makeJsonIngestRequest({ space_id: 'sp1', content_type: 'podcast', source_url: '...' })
    );
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.error).toBeDefined();
  });

  it('returns 403 when learner tries to ingest (FastAPI enforcement)', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(403, 'Creator role required'));

    const res = await POST(
      makeJsonIngestRequest({ space_id: 'sp1', content_type: 'youtube', source_url: '...' })
    );
    expect(res.status).toBe(403);
  });
});

// ─── Multipart / file upload ──────────────────────────────────────────────────

describe('POST /api/content/ingest — Multipart (file upload)', () => {
  beforeEach(() => {
    vi.mocked(cookies).mockReturnValue(
      buildCookieStore({ axis_access: CREATOR_TOKEN }) as any
    );
  });

  /**
   * Build a request that looks multipart to the route handler.
   * The real req.formData() is mocked on the instance so we don't need a
   * truly parseable multipart body — the route just forwards it to apiUpload.
   */
  function makeFileIngestRequest() {
    const req = new NextRequest('http://localhost:3000/api/content/ingest', {
      method: 'POST',
      headers: { 'content-type': 'multipart/form-data; boundary=----testboundary' },
    });

    // Mock formData() so req.formData() doesn't try to parse an empty body
    const mockFormData = new FormData();
    mockFormData.append(
      'file',
      new Blob(['fake pdf content'], { type: 'application/pdf' }),
      'lecture.pdf'
    );
    mockFormData.append('space_id', 'sp1');
    (req as any).formData = vi.fn().mockResolvedValue(mockFormData);

    return req;
  }

  it('routes multipart to /api/v1/ingest/file', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchOk({ ...INGEST_JOB, content_type: 'pdf' }));

    const res = await POST(makeFileIngestRequest());
    const body = await res.json();

    expect(res.status).toBe(200);
    const [url] = (global.fetch as any).mock.calls[0];
    expect(url).toContain('/api/v1/ingest/file');
  });

  it('returns 413 when file is too large', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(413, 'File size exceeds 50 MB limit'));

    const res = await POST(makeFileIngestRequest());
    expect(res.status).toBe(413);
  });

  it('returns 415 for unsupported MIME type', async () => {
    global.fetch = vi.fn().mockResolvedValue(mockFetchError(415, 'Unsupported file type: .exe'));

    const res = await POST(makeFileIngestRequest());
    expect(res.status).toBe(415);
  });
});

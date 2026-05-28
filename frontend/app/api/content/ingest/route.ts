import { NextRequest, NextResponse } from 'next/server';
import { apiRequest, apiUpload } from '@/lib/api/client';
import { cookies } from 'next/headers';

/**
 * POST /api/content/ingest
 *
 * Unified ingest handler for file uploads and URL-based ingest.
 *
 * File uploads (multipart):
 *   - If formData contains `space_id`, routes to the JWT-authenticated
 *     POST /api/v1/spaces/{space_id}/upload endpoint (standalone frontend flow).
 *   - If no `space_id`, falls back to the legacy Moodle ingest endpoint
 *     POST /api/v1/ingest/file (requires tenant API key).
 *
 * URL/JSON ingest:
 *   - If body contains `space_id`, routes to POST /api/v1/spaces/{space_id}/upload-url
 *     (YouTube, Vimeo, Vimeo showcase — all handled by the same endpoint).
 *   - Otherwise uses /api/v1/ingest (tenant API key, Moodle flow).
 */
export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const contentType = req.headers.get('content-type') || '';

  try {
    if (contentType.includes('multipart/form-data')) {
      const formData = await req.formData();
      const spaceId = formData.get('space_id') as string | null;

      if (spaceId) {
        // ── Standalone frontend path — file upload ──────────────────────────
        // Remove space_id from formData (FastAPI gets it from the URL path).
        formData.delete('space_id');
        const data = await apiUpload(
          `/api/v1/spaces/${spaceId}/upload`,
          formData,
          accessToken,
        );
        return NextResponse.json(data);
      }

      // ── Legacy Moodle path ──────────────────────────────────────────────
      const data = await apiUpload('/api/v1/ingest/file', formData, accessToken);
      return NextResponse.json(data);

    } else {
      // ── URL / structured ingest ──────────────────────────────────────────
      const body = await req.json();
      const { space_id: spaceId, ...rest } = body;

      if (spaceId) {
        // Space URL ingest — YouTube, Vimeo, Vimeo showcase
        // Backend: POST /api/v1/spaces/{space_id}/upload-url
        const data = await apiRequest(`/api/v1/spaces/${spaceId}/upload-url`, {
          method: 'POST',
          body: rest,   // { source_url, content_type, title, generate_outputs, language }
          jwtToken: accessToken,
        });
        return NextResponse.json(data);
      }

      // Legacy Moodle flow — no space_id
      const data = await apiRequest('/api/v1/ingest', {
        method: 'POST',
        body: body,
        jwtToken: accessToken,
      });
      return NextResponse.json(data);
    }
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

/**
 * POST /api/library/scorm
 * Upload a SCORM .zip file to the library.
 * Proxies directly to the FastAPI /api/v1/scorm/upload endpoint as multipart/form-data.
 * Returns the created content_item_id so the library can refresh.
 */
export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  try {
    // Forward the multipart body directly — don't re-parse
    const formData = await req.formData();

    const response = await fetch(`${AXIS_AI_URL}/api/v1/scorm/upload`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'X-Requested-With': 'axis-frontend',
        // NOTE: do NOT set Content-Type — fetch sets it automatically with the boundary
      },
      body: formData,
    });

    const data = await response.json();

    if (!response.ok) {
      return NextResponse.json(
        { error: data.detail ?? 'SCORM upload failed' },
        { status: response.status }
      );
    }

    return NextResponse.json(data);
  } catch (err) {
    console.error('[library/scorm] upload error', err);
    return NextResponse.json({ error: 'Upload failed' }, { status: 500 });
  }
}

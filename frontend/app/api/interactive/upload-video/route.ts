/**
 * POST /api/interactive/upload-video
 * Proxies multipart video file uploads to FastAPI backend.
 * Returns: { content_item_id, title, source_url, file_size_mb }
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

export async function POST(req: NextRequest) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  // Stream the multipart body directly to the backend — do NOT parse it
  const contentType = req.headers.get('content-type') ?? '';
  if (!contentType.includes('multipart/form-data')) {
    return NextResponse.json({ error: 'Expected multipart/form-data' }, { status: 400 });
  }

  const res = await fetch(`${BACKEND}/api/v1/interactive/upload-video`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      // Forward the content-type INCLUDING the boundary — critical for multipart
      'content-type': contentType,
    },
    // @ts-ignore — body is a ReadableStream from NextRequest
    body: req.body,
    // @ts-ignore
    duplex: 'half',
  });

  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

// App Router does not parse the body by default — no config needed

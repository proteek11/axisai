/**
 * File-serving proxy — streams locally uploaded files (PDF, PPTX, video)
 * from the FastAPI backend to the browser.
 *
 * GET /api/files/{contentId}
 *
 * The FastAPI backend stores uploaded files as file:///path URIs in source_url.
 * These aren't browser-routable, so we proxy them through Next.js with auth.
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
const AXIS_AI_KEY = process.env.AXIS_AI_KEY || '';

export async function GET(
  _req: NextRequest,
  { params }: { params: { contentId: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const authHeader = accessToken
    ? `Bearer ${accessToken}`
    : `Bearer ${AXIS_AI_KEY}`;

  let response: Response;
  try {
    response = await fetch(
      `${AXIS_AI_URL}/api/v1/library/files/${params.contentId}`,
      {
        headers: {
          Authorization: authHeader,
          'X-Requested-With': 'axis-frontend',
        },
        cache: 'no-store',
      },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  if (!response.ok) {
    return NextResponse.json({ error: 'File not found' }, { status: response.status });
  }

  const contentType =
    response.headers.get('content-type') || 'application/octet-stream';
  const body = await response.arrayBuffer();

  return new NextResponse(body, {
    status: 200,
    headers: {
      'Content-Type': contentType,
      'Content-Disposition':
        response.headers.get('content-disposition') || 'inline',
      'Cache-Control': 'private, max-age=3600',
    },
  });
}

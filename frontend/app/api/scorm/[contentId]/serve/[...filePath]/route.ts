import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
const AXIS_AI_KEY = process.env.AXIS_AI_KEY || '';

/**
 * GET /api/scorm/[contentId]/serve/[...filePath]
 *
 * Proxy for SCORM static assets (HTML, JS, CSS, images, etc.).
 * SCORM packages are stored on the backend server behind JWT auth.
 * This proxy adds the auth header so the iframe src stays same-origin
 * and the access token is never exposed in the URL.
 *
 * Content-Type is preserved from the backend response so the browser
 * can load HTML, execute JS, and render images correctly inside the iframe.
 */
export async function GET(
  req: NextRequest,
  { params }: { params: { contentId: string; filePath: string[] } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);
  const spaceId = searchParams.get('spaceId') ?? '';

  // Reconstruct the file path from segments
  const filePath = params.filePath.join('/');

  const authHeader = accessToken ? `Bearer ${accessToken}` : `Bearer ${AXIS_AI_KEY}`;

  const backendUrl = `${AXIS_AI_URL}/api/v1/scorm/${params.contentId}/serve/${filePath}?space_id=${spaceId}`;

  try {
    const response = await fetch(backendUrl, {
      headers: {
        Authorization: authHeader,
        'X-Requested-With': 'axis-frontend',
      },
    });

    if (!response.ok) {
      return new NextResponse(`File not found: ${filePath}`, { status: response.status });
    }

    // Stream the response body through, preserving Content-Type
    const contentType = response.headers.get('Content-Type') ?? 'application/octet-stream';
    const body = await response.arrayBuffer();

    return new NextResponse(body, {
      status: 200,
      headers: {
        'Content-Type': contentType,
        // Allow SCORM content to run JavaScript in the iframe
        'Content-Security-Policy': "default-src * 'unsafe-inline' 'unsafe-eval' data: blob:;",
        // Cache static SCORM assets briefly (they don't change mid-session)
        'Cache-Control': 'private, max-age=300',
      },
    });
  } catch (err) {
    console.error('[scorm-serve]', err);
    return new NextResponse('Internal error', { status: 500 });
  }
}

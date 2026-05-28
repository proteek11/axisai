/**
 * GET /api/cover-images/[filename]
 * Proxies cover image requests from the Next.js domain to the FastAPI backend.
 * This avoids needing NEXT_PUBLIC_API_URL in browser env.
 */
import { NextRequest, NextResponse } from 'next/server';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export const dynamic = 'force-dynamic';

export async function GET(
  _req: NextRequest,
  { params }: { params: { filename: string } }
) {
  const { filename } = params;
  try {
    const upstream = await fetch(
      `${AXIS_AI_URL}/api/v1/spaces/cover-images/${filename}`,
      { cache: 'no-store' }
    );
    if (!upstream.ok) {
      return new NextResponse(null, { status: upstream.status });
    }
    const blob = await upstream.blob();
    return new NextResponse(blob, {
      status: 200,
      headers: {
        'Content-Type': upstream.headers.get('Content-Type') || 'image/jpeg',
        'Cache-Control': 'public, max-age=86400',
      },
    });
  } catch {
    return new NextResponse(null, { status: 502 });
  }
}

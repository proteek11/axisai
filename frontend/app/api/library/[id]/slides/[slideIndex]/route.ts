import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.AXIS_AI_URL || 'https://axisai.edzlms.com';

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string; slideIndex: string } }
) {
  const cookieStore = await cookies();
  const token = cookieStore.get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  // Check if this is a thumbnail request
  const { searchParams } = new URL(req.url);
  const isThumb = searchParams.get('thumb') === '1';

  const backendUrl = isThumb
    ? `${BACKEND}/api/v1/library/${params.id}/slides/${params.slideIndex}/thumb`
    : `${BACKEND}/api/v1/library/${params.id}/slides/${params.slideIndex}`;

  const res = await fetch(backendUrl, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!res.ok) {
    return NextResponse.json({ error: 'Slide not found' }, { status: res.status });
  }

  const contentType = res.headers.get('content-type') ?? 'image/png';
  const buffer = await res.arrayBuffer();

  return new NextResponse(buffer, {
    status: 200,
    headers: {
      'Content-Type': contentType,
      'Cache-Control': 'private, max-age=3600',
    },
  });
}

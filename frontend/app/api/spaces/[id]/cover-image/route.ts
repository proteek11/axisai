/**
 * POST /api/spaces/[id]/cover-image
 * Proxies a multipart image upload to the backend cover image endpoint.
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  // Forward the raw FormData directly to the backend — do not parse it
  const formData = await req.formData();

  const upstream = await fetch(
    `${AXIS_AI_URL}/api/v1/spaces/${params.id}/cover-image`,
    {
      method: 'POST',
      headers: { Authorization: `Bearer ${accessToken}` },
      body: formData,
    },
  );

  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

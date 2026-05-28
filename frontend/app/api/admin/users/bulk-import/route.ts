/**
 * POST /api/admin/users/bulk-import
 * Forwards a CSV multipart upload to the FastAPI bulk import endpoint.
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) {
    return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  }

  // Forward the raw multipart FormData directly to the backend
  const formData = await req.formData();

  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/auth/users/bulk-import`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${accessToken}` },
    body: formData,
  });

  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

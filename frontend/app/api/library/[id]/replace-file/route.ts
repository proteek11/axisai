/**
 * Replace an uploaded file for a library content item.
 * POST /api/library/{id}/replace-file
 * Body: multipart/form-data — file, generate_outputs (optional JSON list)
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
const AXIS_AI_KEY = process.env.AXIS_AI_KEY || '';

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string } },
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const authHeader = accessToken
    ? `Bearer ${accessToken}`
    : `Bearer ${AXIS_AI_KEY}`;

  const formData = await req.formData();

  let response: Response;
  try {
    response = await fetch(
      `${AXIS_AI_URL}/api/v1/library/${params.id}/replace-file`,
      {
        method: 'POST',
        headers: {
          Authorization: authHeader,
          'X-Requested-With': 'axis-frontend',
          // Do NOT set Content-Type — let fetch set multipart boundary
        },
        body: formData,
        cache: 'no-store',
      },
    );
  } catch {
    return NextResponse.json({ error: 'Backend unreachable' }, { status: 502 });
  }

  if (!response.ok) {
    let detail = `HTTP ${response.status}`;
    try {
      const json = await response.json();
      detail = json.detail || json.error || detail;
    } catch {}
    return NextResponse.json({ error: detail }, { status: response.status });
  }

  return NextResponse.json(await response.json());
}

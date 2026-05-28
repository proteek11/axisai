/**
 * POST /api/course-builder/analyze
 * Forwards a multipart PDF upload to the FastAPI backend for lesson plan analysis.
 * Streams the file directly — does NOT buffer or re-encode.
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  // Forward raw FormData (multipart) directly to FastAPI
  const formData = await req.formData();

  try {
    const resp = await fetch(`${AXIS_AI_URL}/api/v1/course-builder/analyze`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
      },
      body: formData,
    });

    const data = await resp.json();
    return NextResponse.json(data, { status: resp.status });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

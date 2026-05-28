import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.AXIS_AI_URL ?? 'http://localhost:8000';

export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  if (!accessToken) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  try {
    // Parse the incoming multipart/form-data
    const incomingForm = await req.formData();
    const file = incomingForm.get('file') as File | null;

    if (!file || typeof file === 'string') {
      return NextResponse.json({ error: 'No file provided' }, { status: 400 });
    }

    // Re-build a fresh FormData so fetch can set the correct boundary header
    const outgoingForm = new FormData();
    outgoingForm.append('file', file, file.name);

    const res = await fetch(`${BACKEND}/api/v1/auth/me/avatar`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        // Do NOT set Content-Type — let fetch set it with the correct multipart boundary
      },
      body: outgoingForm,
    });

    let data: unknown;
    try {
      data = await res.json();
    } catch {
      data = { detail: `HTTP ${res.status}` };
    }

    if (!res.ok) {
      const detail =
        typeof data === 'object' && data !== null && 'detail' in data
          ? (data as Record<string, unknown>).detail
          : 'Upload failed';
      return NextResponse.json(
        { error: typeof detail === 'string' ? detail : JSON.stringify(detail) },
        { status: res.status }
      );
    }

    return NextResponse.json(data);
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : 'Internal server error';
    console.error('[avatar upload error]', err);
    return NextResponse.json({ error: message }, { status: 500 });
  }
}

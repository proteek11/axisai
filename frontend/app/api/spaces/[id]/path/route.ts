import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.AXIS_AI_URL ?? 'http://localhost:8000';

/** PUT /api/spaces/[id]/path — bulk reorder + section labels */
export async function PUT(
  req: NextRequest,
  { params }: { params: { id: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) {
    return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });
  }

  try {
    const body = await req.json();
    const res = await fetch(`${BACKEND}/api/v1/spaces/${params.id}/path`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${accessToken}`,
      },
      body: JSON.stringify(body),
    });

    if (res.status === 204) return new NextResponse(null, { status: 204 });

    // For any non-204 response, forward the error detail
    const data = await res.json().catch(() => ({}));
    return NextResponse.json(
      { error: (data as any).detail ?? 'Reorder failed' },
      { status: res.status }
    );
  } catch (err) {
    console.error('[path reorder]', err);
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.AXIS_AI_URL ?? 'http://localhost:8000';

export async function POST(
  req: NextRequest,
  { params }: { params: { id: string; contentId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });

  try {
    const body = await req.json();
    const res = await fetch(
      `${BACKEND}/api/v1/spaces/${params.id}/content/${params.contentId}/flashcard-review`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
        body: body,
      }
    );
    if (res.status === 204) return new NextResponse(null, { status: 204 });
    const data = await res.json();
    return NextResponse.json({ error: data.detail ?? 'Failed' }, { status: res.status });
  } catch {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

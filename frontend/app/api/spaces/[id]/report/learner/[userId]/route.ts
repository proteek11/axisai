import { cookies } from 'next/headers';
import { NextRequest, NextResponse } from 'next/server';

const BACKEND = process.env.AXIS_AI_URL ?? 'http://localhost:8000';

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string; userId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  if (!accessToken) return NextResponse.json({ error: 'Not authenticated' }, { status: 401 });

  try {
    const res = await fetch(
      `${BACKEND}/api/v1/spaces/${params.id}/report/learners/${params.userId}`,
      { headers: { Authorization: `Bearer ${accessToken}` }, cache: 'no-store' }
    );
    const data = await res.json();
    if (!res.ok) return NextResponse.json({ error: data.detail ?? 'Failed' }, { status: res.status });
    return NextResponse.json(data);
  } catch {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}

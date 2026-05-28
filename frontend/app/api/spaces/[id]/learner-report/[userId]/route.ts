import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export async function GET(
  req: NextRequest,
  { params }: { params: { id: string; userId: string } },
) {
  const cookieStore = cookies();
  const token = cookieStore.get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthenticated' }, { status: 401 });

  const res = await fetch(
    `${AXIS_AI_URL}/api/v1/spaces/${params.id}/report/learners/${params.userId}`,
    {
      headers: { Authorization: `Bearer ${token}`, 'X-Requested-With': 'axis-frontend' },
      cache: 'no-store',
    },
  );
  const data = await res.json().catch(() => ({}));
  if (!res.ok) return NextResponse.json(data, { status: res.status });
  return NextResponse.json(data);
}

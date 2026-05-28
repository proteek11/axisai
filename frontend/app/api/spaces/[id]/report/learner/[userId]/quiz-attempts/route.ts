import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.NEXT_PUBLIC_API_URL ?? 'https://axisai.edzlms.com';

export async function GET(
  _req: NextRequest,
  { params }: { params: { id: string; userId: string } },
) {
  const token = cookies().get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const res = await fetch(
    `${BACKEND}/api/v1/spaces/${params.id}/report/learner/${params.userId}/quiz-attempts`,
    { headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' } },
  );
  const data = await res.json().catch(() => ({}));
  return NextResponse.json(data, { status: res.status });
}

import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.AXIS_AI_URL || 'https://axisai.edzlms.com';

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const cookieStore = await cookies();
  const token = cookieStore.get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });

  const body = await req.json();
  const res = await fetch(`${BACKEND}/api/v1/library/${params.id}/pdf-respond`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json(), { status: res.status });
}

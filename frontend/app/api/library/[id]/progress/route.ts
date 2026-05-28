import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const BACKEND = process.env.AXIS_AI_URL || process.env.NEXT_PUBLIC_API_URL || 'https://axisai.edzlms.com';

async function getToken() {
  return cookies().get('axis_access')?.value;
}

export async function GET(_: NextRequest, { params }: { params: { id: string } }) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const res = await fetch(`${BACKEND}/api/v1/library/${params.id}/progress`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  });
  return NextResponse.json(await res.json().catch(() => ({})), { status: res.status });
}

export async function POST(req: NextRequest, { params }: { params: { id: string } }) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const body = await req.json();
  const res = await fetch(`${BACKEND}/api/v1/library/${params.id}/progress`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  return NextResponse.json(await res.json().catch(() => ({})), { status: res.status });
}

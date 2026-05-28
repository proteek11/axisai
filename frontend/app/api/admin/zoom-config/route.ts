import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
async function getToken() { return cookies().get('axis_access')?.value; }

export async function GET() {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/admin/zoom-config`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const body = await req.json();
  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/admin/zoom-config`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

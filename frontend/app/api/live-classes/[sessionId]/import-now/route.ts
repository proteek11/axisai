import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
async function getToken() { return cookies().get('axis_access')?.value; }

export async function POST(req: NextRequest, { params }: { params: { sessionId: string } }) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/live-classes/${params.sessionId}/import-now`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

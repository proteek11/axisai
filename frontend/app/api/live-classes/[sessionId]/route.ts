/**
 * GET    /api/live-classes/[sessionId]  → get session detail
 * PATCH  /api/live-classes/[sessionId]  → update session
 * DELETE /api/live-classes/[sessionId]  → cancel session
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

async function getToken() {
  const cookieStore = cookies();
  return cookieStore.get('axis_access')?.value;
}

export async function GET(req: NextRequest, { params }: { params: { sessionId: string } }) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/live-classes/${params.sessionId}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

export async function PATCH(req: NextRequest, { params }: { params: { sessionId: string } }) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const body = await req.json();
  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/live-classes/${params.sessionId}`, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

export async function DELETE(req: NextRequest, { params }: { params: { sessionId: string } }) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/live-classes/${params.sessionId}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (upstream.status === 204) return new NextResponse(null, { status: 204 });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

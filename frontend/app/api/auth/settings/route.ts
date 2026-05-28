/**
 * GET  /api/auth/settings  — public: returns google_auth_enabled
 * PUT  /api/auth/settings  — admin only: update auth settings
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';
export const dynamic = 'force-dynamic';

export async function GET() {
  const r = await fetch(`${AXIS_AI_URL}/api/v1/auth/settings/auth/public`, { cache: 'no-store' });
  const data = await r.json().catch(() => ({ google_auth_enabled: false }));
  return NextResponse.json(data);
}

export async function PUT(req: NextRequest) {
  const cookieStore = cookies();
  const token = cookieStore.get('axis_access')?.value;
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const body = await req.json();
  const r = await fetch(`${AXIS_AI_URL}/api/v1/auth/settings/auth`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
    body: JSON.stringify(body),
  });
  const data = await r.json().catch(() => ({}));
  return NextResponse.json(data, { status: r.status });
}

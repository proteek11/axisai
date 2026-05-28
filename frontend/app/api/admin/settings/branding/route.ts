/**
 * GET  /api/admin/settings/branding  → fetch current branding
 * PUT  /api/admin/settings/branding  → save branding (admin)
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

async function getToken() {
  const cookieStore = cookies();
  return cookieStore.get('axis_access')?.value;
}

export async function GET() {
  const accessToken = await getToken();
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/auth/settings/branding`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

export async function PUT(req: NextRequest) {
  const accessToken = await getToken();
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const body = await req.json();
  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/auth/settings/branding`, {
    method: 'PUT',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

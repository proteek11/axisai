/**
 * GET  /api/admin/settings/email  → fetch SMTP config + trigger templates
 * PUT  /api/admin/settings/email  → save email settings
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

async function getToken() {
  const cookieStore = cookies();
  return cookieStore.get('axis_access')?.value;
}

export async function GET() {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/admin/settings/email`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

export async function PUT(req: NextRequest) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const body = await req.json();
  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/admin/settings/email`, {
    method: 'PUT',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

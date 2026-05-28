/**
 * POST /api/admin/settings/email/test        → test SMTP connection (no email sent)
 * POST /api/admin/settings/email/test?send=1 → send a real test email
 */
import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

async function getToken() {
  const cookieStore = cookies();
  return cookieStore.get('axis_access')?.value;
}

export async function POST(req: NextRequest) {
  const token = await getToken();
  if (!token) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const body = await req.json();
  const send = req.nextUrl.searchParams.get('send') === '1';
  const endpoint = send ? 'send-test' : 'test';

  const upstream = await fetch(`${AXIS_AI_URL}/api/v1/admin/settings/email/${endpoint}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await upstream.json().catch(() => ({}));
  return NextResponse.json(data, { status: upstream.status });
}

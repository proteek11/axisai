/**
 * POST /api/auth/lti-exchange
 * Exchanges a one-time token (OTT) issued by the LTI launch handler for
 * proper axis_access + axis_refresh cookies.
 * Called by the /lti/complete server page — never exposed to the browser directly.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest, ApiError } from '@/lib/api/client';

interface OTTResponse {
  access_token: string;
  refresh_token: string;
}

export async function POST(request: NextRequest) {
  const body = await request.json().catch(() => ({}));
  const { ott } = body;

  if (!ott) {
    return NextResponse.json({ detail: 'Missing ott' }, { status: 400 });
  }

  try {
    const data = await apiRequest<OTTResponse>('/api/v1/auth/lti-exchange', {
      method: 'POST',
      body: { ott },
    });

    const res = NextResponse.json({ ok: true });

    // Set access token (readable by JS for API calls)
    res.cookies.set('axis_access', data.access_token, {
      httpOnly: false,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',   // lax (not strict) — needed for cross-site LTI redirects
      maxAge: 900,
      path: '/',
    });

    // Set refresh token (HttpOnly — not readable by JS)
    res.cookies.set('axis_refresh', data.refresh_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'lax',
      maxAge: 7 * 24 * 60 * 60,
      path: '/',
    });

    return res;
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ detail: err.message }, { status: err.status });
    }
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 });
  }
}

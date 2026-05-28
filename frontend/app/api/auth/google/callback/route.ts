/**
 * GET /api/auth/google/callback
 * Handles Google's redirect after user approves OAuth.
 * Exchanges code with FastAPI backend, sets cookies, redirects to dashboard.
 */
import { NextRequest, NextResponse } from 'next/server';

const AXIS_AI_URL = process.env.AXIS_AI_URL || 'http://localhost:8000';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const code = searchParams.get('code');
  const error = searchParams.get('error');

  if (error || !code) {
    return NextResponse.redirect(
      new URL(`/login?error=google_cancelled`, req.url)
    );
  }

  const redirectUri = process.env.GOOGLE_REDIRECT_URI ||
    `${process.env.NEXT_PUBLIC_APP_URL}/api/auth/google/callback`;

  try {
    const r = await fetch(`${AXIS_AI_URL}/api/v1/auth/google/callback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code, redirect_uri: redirectUri }),
    });

    if (!r.ok) {
      const err = await r.json().catch(() => ({}));
      const msg = encodeURIComponent(err.detail || 'Google login failed');
      return NextResponse.redirect(new URL(`/login?error=${msg}`, req.url));
    }

    const data = await r.json();
    const { access_token, refresh_token, user } = data;

    const isProd = process.env.NODE_ENV === 'production';
    const response = NextResponse.redirect(new URL('/dashboard', req.url));

    response.cookies.set('axis_access', access_token, {
      httpOnly: false, secure: isProd, sameSite: 'strict', maxAge: 900, path: '/',
    });
    response.cookies.set('axis_refresh', refresh_token, {
      httpOnly: true, secure: isProd, sameSite: 'strict', maxAge: 7 * 24 * 60 * 60, path: '/',
    });

    // Store user in a readable cookie for the client store bootstrap
    response.cookies.set('axis_user', JSON.stringify(user), {
      httpOnly: false, secure: isProd, sameSite: 'strict', maxAge: 900, path: '/',
    });

    return response;
  } catch {
    return NextResponse.redirect(new URL('/login?error=google_failed', req.url));
  }
}

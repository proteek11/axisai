/**
 * POST /api/auth/refresh
 * Reads the HttpOnly refresh token cookie and exchanges it for a new access token.
 * Called by middleware.ts — receives the forwarded cookie header, not a request body.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest, ApiError } from '@/lib/api/client';

interface RefreshResponse {
  access_token: string;
  refresh_token?: string | null; // Populated on token rotation
}

export async function POST(request: NextRequest) {
  const refreshToken = request.cookies.get('axis_refresh')?.value;

  if (!refreshToken) {
    return NextResponse.json({ detail: 'No refresh token' }, { status: 401 });
  }

  try {
    const data = await apiRequest<RefreshResponse>('/api/v1/auth/refresh', {
      method: 'POST',
      body: { refresh_token: refreshToken },
    });

    const { access_token, refresh_token: new_refresh_token } = data;

    // Fetch current user profile with the fresh token
    let user = null;
    try {
      user = await apiRequest('/api/v1/auth/me', { jwtToken: access_token });
    } catch {
      // Non-fatal — caller can re-fetch me separately
    }

    const res = NextResponse.json({ access_token, user });

    res.cookies.set('axis_access', access_token, {
      httpOnly: false,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 900, // 15 minutes
      path: '/',
    });

    // Token rotation: if the backend issued a new refresh token, replace the old cookie.
    // Without this, the rotated (now-invalidated) token would be re-sent next time,
    // causing an immediate 401 and forcing the user to re-login.
    if (new_refresh_token) {
      res.cookies.set('axis_refresh', new_refresh_token, {
        httpOnly: true,
        secure: process.env.NODE_ENV === 'production',
        sameSite: 'strict',
        maxAge: 7 * 24 * 60 * 60, // 7 days
        path: '/',
      });
    }

    return res;
  } catch (err) {
    if (err instanceof ApiError && err.status === 401) {
      // Refresh token expired or revoked — clear both cookies
      const res = NextResponse.json({ detail: 'Session expired' }, { status: 401 });
      res.cookies.delete('axis_refresh');
      res.cookies.delete('axis_access');
      return res;
    }
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 });
  }
}

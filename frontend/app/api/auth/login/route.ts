/**
 * POST /api/auth/login
 * Proxies login to FastAPI, receives access+refresh tokens,
 * sets the refresh token as an HttpOnly cookie, returns access token + user to client.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest, ApiError } from '@/lib/api/client';

interface LoginResponse {
  access_token: string;
  refresh_token: string;
  user: {
    id: string;
    email: string;
    full_name: string;
    role: string;
  };
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    // Validate required fields before forwarding — never log the password
    if (!body?.email || !body?.password) {
      return NextResponse.json({ detail: 'Email and password are required' }, { status: 400 });
    }

    const data = await apiRequest<LoginResponse>('/api/v1/auth/login', {
      method: 'POST',
      body: { email: body.email, password: body.password }, // explicit — no extra fields forwarded
    });

    const { access_token, refresh_token, user } = data;

    const res = NextResponse.json({ access_token, user });

    // Set refresh token as HttpOnly cookie — browser cannot read this
    res.cookies.set('axis_refresh', refresh_token, {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 7 * 24 * 60 * 60, // 7 days
      path: '/',
    });

    // Set access token as readable cookie so middleware can check expiry
    res.cookies.set('axis_access', access_token, {
      httpOnly: false,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      maxAge: 900, // 15 minutes
      path: '/',
    });

    return res;
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ detail: err.detail }, { status: err.status });
    }
    return NextResponse.json({ detail: 'Internal server error' }, { status: 500 });
  }
}

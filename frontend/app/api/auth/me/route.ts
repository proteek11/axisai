import { NextRequest, NextResponse } from 'next/server';
import { apiRequest, ApiError } from '@/lib/api/client';

export async function GET(request: NextRequest) {
  const accessToken =
    request.cookies.get('axis_access')?.value ||
    request.headers.get('authorization')?.replace('Bearer ', '');

  if (!accessToken) {
    return NextResponse.json({ detail: 'Unauthenticated' }, { status: 401 });
  }

  try {
    const user = await apiRequest<object>('/api/v1/auth/me', {
      jwtToken: accessToken,
    });
    return NextResponse.json({ user, access_token: accessToken });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ detail: err.detail }, { status: err.status });
    }
    return NextResponse.json({ detail: 'Internal error' }, { status: 500 });
  }
}

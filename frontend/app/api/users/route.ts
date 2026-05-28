/**
 * GET /api/users
 * Returns learner-role users accessible to the current user (creator or admin).
 * Proxies to /api/v1/auth/learners — no admin privilege required.
 */
import { NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET() {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;

  try {
    const data = await apiRequest('/api/v1/auth/learners', {
      method: 'GET',
      jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed to fetch learners' },
      { status: err.status || 500 },
    );
  }
}

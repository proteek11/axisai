/**
 * POST /api/course-builder/generate
 * Create Learning Space + kick off all chapter generation jobs.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const body = await req.json();

  try {
    const data = await apiRequest('/api/v1/course-builder/generate', {
      method: 'POST',
      body,
      jwtToken: accessToken,
      timeoutMs: 60_000, // generation can take a moment
    });
    return NextResponse.json(data, { status: 201 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

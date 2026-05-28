/**
 * GET /api/course-builder/youtube?query=...
 * Proxy to FastAPI YouTube search endpoint.
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const query = req.nextUrl.searchParams.get('query') || '';
  if (!query.trim()) {
    return NextResponse.json([], { status: 200 });
  }

  try {
    const data = await apiRequest(
      `/api/v1/course-builder/youtube?query=${encodeURIComponent(query)}&max_results=5`,
      { method: 'GET', jwtToken: accessToken },
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

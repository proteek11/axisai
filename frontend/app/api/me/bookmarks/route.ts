/**
 * Bookmarks proxy — GET/POST /api/me/bookmarks
 * L-06: Learner bookmarks
 */
import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

async function getToken() {
  const cookieStore = cookies();
  return cookieStore.get('axis_access')?.value;
}

export async function GET(req: NextRequest) {
  const accessToken = await getToken();
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });

  const contentId = req.nextUrl.searchParams.get('content_item_id');
  const url = contentId
    ? `/api/v1/me/bookmarks?content_item_id=${contentId}`
    : '/api/v1/me/bookmarks';

  try {
    const data = await apiRequest(url, { jwtToken: accessToken });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

export async function POST(req: NextRequest) {
  const accessToken = await getToken();
  if (!accessToken) return NextResponse.json({ error: 'Unauthorised' }, { status: 401 });
  const body = await req.json();
  try {
    const data = await apiRequest('/api/v1/me/bookmarks', {
      method: 'POST', body, jwtToken: accessToken,
    });
    return NextResponse.json(data, { status: 201 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const { searchParams } = new URL(req.url);

  const params = new URLSearchParams();
  for (const key of ['search', 'content_type', 'experience_mode', 'visibility', 'page', 'page_size']) {
    const val = searchParams.get(key);
    if (val) params.set(key, val);
  }
  if (!params.has('page')) params.set('page', '1');
  if (!params.has('page_size')) params.set('page_size', '30');

  try {
    const data = await apiRequest(
      `/api/v1/library?${params.toString()}`,
      { method: 'GET', jwtToken: accessToken }
    );
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

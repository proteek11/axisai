import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function POST(req: NextRequest) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const body = await req.json();

  try {
    const data = await apiRequest('/api/v1/library/upload-url', {
      method: 'POST',
      body,
      jwtToken: accessToken,
    });
    return NextResponse.json(data, { status: 202 });
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: err.status || 500 });
  }
}

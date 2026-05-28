import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET(req: NextRequest, { params }: { params: { path: string[] } }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const path = params.path.join('/');
  const search = req.nextUrl.search;
  try {
    const data = await apiRequest(`/api/v1/reports/${path}${search}`, {
      method: 'GET',
      jwtToken: accessToken,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed' },
      { status: err.status || 500 },
    );
  }
}

export async function POST(req: NextRequest, { params }: { params: { path: string[] } }) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const path = params.path.join('/');
  const body = await req.json();
  try {
    const data = await apiRequest(`/api/v1/reports/${path}`, {
      method: 'POST',
      jwtToken: accessToken,
      body,
    });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json(
      { error: err.message || 'Failed' },
      { status: err.status || 500 },
    );
  }
}

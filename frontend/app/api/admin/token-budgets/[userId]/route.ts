import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { apiRequest } from '@/lib/api/client';

export async function GET(
  _req: NextRequest,
  { params }: { params: { userId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const data = await apiRequest(`/api/v1/admin/token-budgets/${params.userId}`, {
    method: 'GET',
    jwtToken: accessToken,
  });
  return NextResponse.json(data);
}

export async function PUT(
  req: NextRequest,
  { params }: { params: { userId: string } }
) {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const body = await req.json();
  const data = await apiRequest(`/api/v1/admin/token-budgets/${params.userId}`, {
    method: 'PUT',
    body: body,
    jwtToken: accessToken,
  });
  return NextResponse.json(data);
}

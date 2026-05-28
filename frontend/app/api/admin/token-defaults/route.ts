import { NextRequest, NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { apiRequest } from '@/lib/api/client';

export async function GET() {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const data = await apiRequest('/api/v1/admin/token-defaults', {
    method: 'GET',
    jwtToken: accessToken,
  });
  return NextResponse.json(data);
}

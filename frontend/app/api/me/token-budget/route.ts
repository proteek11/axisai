import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { apiRequest } from '@/lib/api/client';

export async function GET() {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const data = await apiRequest('/api/v1/me/token-budget', {
    method: 'GET',
    jwtToken: accessToken,
  });
  return NextResponse.json(data);
}

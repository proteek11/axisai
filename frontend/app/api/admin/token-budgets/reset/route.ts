import { NextResponse } from 'next/server';
import { cookies } from 'next/headers';
import { apiRequest } from '@/lib/api/client';

export async function POST() {
  const cookieStore = cookies();
  const accessToken = cookieStore.get('axis_access')?.value;
  const data = await apiRequest('/api/v1/admin/token-budgets/reset', {
    method: 'POST',
    jwtToken: accessToken,
  });
  return NextResponse.json(data);
}

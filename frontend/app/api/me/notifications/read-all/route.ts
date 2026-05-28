import { NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function POST() {
  const cookieStore = cookies();
  const token = cookieStore.get('axis_access')?.value;
  try {
    const data = await apiRequest('/api/v1/me/notifications/read-all', { method: 'POST', jwtToken: token });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ error: err.message }, { status: 500 });
  }
}

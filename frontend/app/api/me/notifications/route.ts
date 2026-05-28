import { NextRequest, NextResponse } from 'next/server';
import { apiRequest } from '@/lib/api/client';
import { cookies } from 'next/headers';

export async function GET() {
  const cookieStore = cookies();
  const token = cookieStore.get('axis_access')?.value;
  try {
    const data = await apiRequest('/api/v1/me/notifications', { method: 'GET', jwtToken: token });
    return NextResponse.json(data);
  } catch (err: any) {
    return NextResponse.json({ notifications: [], unread_count: 0 });
  }
}
